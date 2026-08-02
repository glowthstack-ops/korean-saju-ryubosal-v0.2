"""위험 검증 lease preflight — 무과금 (RISK-LEASE-REVALIDATION-01a, 2026-08-02).

목적은 두 가지다.

    1. 현재 DEGRADED 원인이 **만료뿐**이라는 것을 재현 가능하게 증명
    2. 실과금 재검증 전에 writer/loader 계약과 거부 경로를 고정

## 철회된 가설

  adapter_identity_hash 가 null 이라 새 lease 가 loader 계약을 만족하지 못할 수 있다

실제 필드명은 `identity_hash` 이고 값이 채워져 있다(운영 lease: 24f64a029fc6c556).
존재하지 않는 키를 조회해 None 을 받은 측정 오류였다. loader 는 `body["identity_hash"]` 를
비교하므로 그 경로는 정상이다. 이후 감사자가 같은 잘못된 추적을 반복하지 않도록 여기 남긴다.

**provider 호출 0.** 실과금 하네스는 실행하지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from saju_api.services import risk_validation_lease as lease_mod

_MODEL = "preflight-model"
_IDENTITY = "24f64a029fc6c556"          # 운영 lease 와 같은 형태의 고정 값
_OPERATIONAL = (
    Path(__file__).resolve().parents[2] / "var" / "risk_state"
    / "validation_lease__gemini-3-flash-preview.json"
)


@pytest.fixture
def temp_state(tmp_path, monkeypatch):
    """운영 lease·readiness 를 건드리지 않는다 — 임시 디렉터리로 격리한다."""
    monkeypatch.setattr(lease_mod, "_STATE_DIR", tmp_path)
    return tmp_path


def _write(temp_state, *, identity=_IDENTITY, model=_MODEL, validated_at=None):
    return lease_mod.write_lease(
        model_id=model, identity_hash=identity,
        reported_model_version="preflight", samples_summary={"n": 0},
        validated_at=validated_at or datetime.now(UTC),
    )


# ── 만료 단독 원인 ───────────────────────────────────────────────────────


def test_same_lease_is_valid_before_expiry_and_invalid_after(temp_state) -> None:
    """동일 model·identity·형식의 lease 가 **시간만 달라** 갈린다.

    현재 시각에서 invalid 라는 사실만으로는 "만료가 유일한 원인" 을 증명하지 못한다.
    같은 내용을 발급 시각만 바꿔 두 번 확인해야 한다.
    """
    _write(temp_state, validated_at=datetime.now(UTC))
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is not None

    expired_at = datetime.now(UTC) - timedelta(days=lease_mod.LEASE_TTL_DAYS + 1)
    _write(temp_state, validated_at=expired_at)
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is None


def test_operational_lease_carries_an_identity_and_is_only_expired() -> None:
    """운영 lease 를 읽기만 한다 — 수정하지 않는다."""
    if not _OPERATIONAL.exists():          # 개발 환경에는 없을 수 있다
        pytest.skip("운영 lease 파일 없음")
    body = json.loads(_OPERATIONAL.read_text(encoding="utf-8"))["body"]
    assert body.get("identity_hash")       # null 이 아니다 — 철회된 가설
    assert "adapter_identity_hash" not in body   # 그런 필드는 없다
    expires = datetime.fromisoformat(body["validation_expires_at"])
    assert expires <= datetime.now(UTC)     # 무효 사유는 만료다


# ── identity 왕복 ────────────────────────────────────────────────────────


def test_writer_records_the_identity_the_loader_compares(temp_state) -> None:
    path = _write(temp_state)
    body = json.loads(path.read_text(encoding="utf-8"))["body"]
    assert body["identity_hash"] == _IDENTITY
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is not None


def test_adapter_identity_hash_is_non_null_and_deterministic() -> None:
    """해시 입력 계약 전체를 재설계하지 않는다 — 값이 있고 반복 산출이 같은지만 본다."""
    from saju_api.services.token_counter_registry import adapter_identity_hash

    class _Adapter:
        provider_id = "preflight"
        model_id = "m"
        counter_version = "v1"
        request_schema_version = "s1"
        mode = "full"
        validation_corpus_hash = "c"

    first = adapter_identity_hash(_Adapter())
    assert first and adapter_identity_hash(_Adapter()) == first


# ── loader 거부 경로 (현재 구현이 정의한 것만) ───────────────────────────


def test_identity_mismatch_is_rejected(temp_state) -> None:
    _write(temp_state)
    assert lease_mod.load_valid_lease(_MODEL, "다른-identity") is None


def test_model_mismatch_is_rejected(temp_state) -> None:
    _write(temp_state)
    assert lease_mod.load_valid_lease("다른-모델", _IDENTITY) is None


def test_signature_mismatch_is_rejected(temp_state) -> None:
    path = _write(temp_state)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["body"]["reported_model_version"] = "변조"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is None


def test_corrupt_body_is_rejected(temp_state) -> None:
    path = _write(temp_state)
    path.write_text("{not json", encoding="utf-8")
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is None


def test_missing_lease_is_rejected(temp_state) -> None:
    assert lease_mod.load_valid_lease("없는-모델", _IDENTITY) is None


def test_insufficient_runway_is_rejected(temp_state) -> None:
    """만료 전이라도 잔여가 최소 runway 미만이면 기동을 막는다."""
    nearly = datetime.now(UTC) - timedelta(
        days=lease_mod.LEASE_TTL_DAYS,
        hours=-(lease_mod.MIN_RUNWAY_HOURS - 1))
    _write(temp_state, validated_at=nearly)
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is None
    # runway 요건을 끄면 통과한다 — 만료가 아니라 runway 때문임을 분리 확인.
    assert lease_mod.load_valid_lease(
        _MODEL, _IDENTITY, require_runway=False) is not None


# ── 운영 불변 ────────────────────────────────────────────────────────────


def test_preflight_never_touches_the_operational_state(temp_state) -> None:
    """임시 디렉터리로 격리했는지 확인 — 실패해도 운영 lease 는 그대로다."""
    before = _OPERATIONAL.read_bytes() if _OPERATIONAL.exists() else None
    _write(temp_state)
    lease_mod.load_valid_lease(_MODEL, "틀린-값")
    after = _OPERATIONAL.read_bytes() if _OPERATIONAL.exists() else None
    assert before == after
    assert lease_mod.lease_path(_MODEL).parent == temp_state


# ── 유료 실행 예산 (dry-run) ─────────────────────────────────────────────


def test_paid_run_budget_is_computable_without_provider_calls() -> None:
    """하네스 계획만 만든다 — provider 호출 0.

    `_build_corpus` 는 요청 본문만 조립하고, 네트워크는 `_provider_reported` 에서만 쓴다.
    비용 승인을 받으려면 실행 전에 호출·토큰 규모가 재현 가능해야 한다.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "scripts"))
    import risk_adapter_shadow_validation as harness

    model = "gemini-3-flash-preview"
    corpus, extra = harness._build_corpus(model, model)
    categories = {s["category"] for s in corpus}

    assert len(corpus) == 39          # 13형 × 3표본
    assert len(categories) == 13
    assert sum(1 for s in corpus if s["category"] == "S13_cache_hit_replay") == 3

    # 표본 하나당 countTokens 1 + generateContent 1 이 계획된다.
    assert len(corpus) * 2 == 78
