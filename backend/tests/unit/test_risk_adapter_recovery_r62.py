"""위험 어댑터 복구(감수 62차) — 캐시 경로 조건부·lease·UNVALIDATED 검증.

전면 EXPOSE 테스트 게이트 1(정규화 shape digest 안정성) 포함.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

import saju_api.services.token_counter_registry as reg
from saju_api.services import risk_validation_lease as lease_mod
from saju_api.services.risk_llm_pipeline import request_shape_digest
from saju_api.services.token_counter_registry import (
    ProviderRequest,
    TokenCounterAdapter,
    adapter_identity_hash,
    record_cache_observation,
    register_adapter,
)


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    """suspension·lease 저장소를 임시 디렉터리로 격리."""
    monkeypatch.setattr(reg, "_SUSPENSION_FILE",
                        tmp_path / "adapter_suspensions.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE",
                        tmp_path / "adapter_suspensions.lock")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER",
                        tmp_path / "adapter_suspensions_ledger.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "exposure_disabled.marker")
    monkeypatch.setattr(lease_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(reg, "_REGISTRY", {})
    monkeypatch.setattr(reg, "_VALIDATION", {})
    # 캐시 보호창·관측 지표도 프로세스 전역이라 테스트 간 누수된다.
    monkeypatch.setattr(reg, "_CACHE_OBSERVED_UNTIL", {})
    monkeypatch.setattr(reg, "_CACHE_PROTECTION_METRICS", {})
    return tmp_path


def _adapter(model_id: str = "m-test", *, cache_ok: bool = False,
             overhead: tuple[tuple[str, int], ...] = ()) -> TokenCounterAdapter:
    return TokenCounterAdapter(
        model_id=model_id, mode="PROVIDER_EXACT", counter=len,
        provider_id="gemini", counter_version="r-test",
        validation_corpus_hash="c" * 64, cache_path_validated=cache_ok,
        framing_overhead_by_shape=overhead)


# ── 캐시 경로 조건부(유일한 게이트 완화 — 검증 identity 한정) ────────────


def test_cache_observation_validated_identity_no_suspend(
        isolated_state) -> None:
    register_adapter(_adapter(cache_ok=True))
    record_cache_observation("m-test", cached_input=5000)
    assert reg._VALIDATION["m-test"] != "SUSPENDED"
    assert not (isolated_state / "adapter_suspensions_ledger.jsonl").exists()


def test_cache_observation_unvalidated_identity_no_tombstone(
        isolated_state) -> None:
    """RISK-CACHE-SUSPEND-01(2026-08-04 완화): 미검증 캐시 경로 적중은
    identity 손상이 아니라 미검증 capability의 발현이다 — 전역 tombstone
    금지, 휘발성 보호창만 연다(응답 폐기는 호출부가 계속 수행)."""
    register_adapter(_adapter(cache_ok=False))
    record_cache_observation("m-test", cached_input=5000)
    assert reg._VALIDATION["m-test"] != "SUSPENDED"
    assert not (isolated_state / "adapter_suspensions_ledger.jsonl").exists()
    assert not (isolated_state / "adapter_suspensions.json").exists()
    assert reg.cache_path_state("m-test") == "CACHE_PATH_OBSERVED_UNVALIDATED"


def test_cache_observation_opens_volatile_bypass_window(
        isolated_state, monkeypatch) -> None:
    """보호창이 열린 동안 주입용 counter 해소가 BYPASS(None) 되고,
    창이 닫히면 identity 무효화 없이 그대로 복귀한다."""
    adapter = _adapter(cache_ok=False)
    register_adapter(adapter)
    reg.set_validation_state("m-test", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "m-test",
             "providerId": "gemini", "counterVersion": "r-test",
             "providerRequestSchemaVersion": "1",
             "countMode": "PROVIDER_EXACT",
             "validationPolicyHash": reg.adapter_validation_policy_hash(),
             "validationCorpusHash": "c" * 64}
    assert reg.resolve_expose_counter("m-test", [entry]) is not None
    record_cache_observation("m-test", cached_input=42)
    assert reg.resolve_expose_counter("m-test", [entry]) is None
    # 창 만료 = 재검증·재등록 없이 복귀(tombstone과의 결정적 차이)
    monkeypatch.setitem(reg._CACHE_OBSERVED_UNTIL, "m-test", 0.0)
    assert reg.resolve_expose_counter("m-test", [entry]) is not None
    assert reg.cache_path_state("m-test") == "CACHE_PATH_NOT_OBSERVED"


def test_cache_protection_metrics_separate_entry_and_extension(
        isolated_state) -> None:
    """진입과 연장을 분리해 센다 — 적중이 반복되면 창이 매번 재시작되어
    사실상 무기한 BYPASS가 될 수 있으므로 연장 누적이 보여야 한다."""
    register_adapter(_adapter(cache_ok=False))
    record_cache_observation("m-test", cached_input=10)   # 진입
    record_cache_observation("m-test", cached_input=10)   # 연장
    record_cache_observation("m-test", cached_input=10)   # 연장
    m = reg.cache_protection_metrics("m-test")
    assert (m["entries"], m["extensions"]) == (1, 2)
    assert m["last_observed"] is not None
    assert reg.cache_protection_expires_at("m-test") is not None
    # 창이 닫힌 뒤의 적중은 다시 '진입'이다.
    reg._CACHE_OBSERVED_UNTIL.pop("m-test", None)
    assert reg.cache_protection_expires_at("m-test") is None
    record_cache_observation("m-test", cached_input=10)
    assert reg.cache_protection_metrics("m-test")["entries"] == 2


def test_cache_protection_counts_discarded_requests(isolated_state) -> None:
    """보호창 때문에 주입이 BYPASS된 요청 수를 센다."""
    register_adapter(_adapter(cache_ok=False))
    reg.set_validation_state("m-test", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "m-test",
             "providerId": "gemini", "counterVersion": "r-test",
             "providerRequestSchemaVersion": "1",
             "countMode": "PROVIDER_EXACT",
             "validationPolicyHash": reg.adapter_validation_policy_hash(),
             "validationCorpusHash": "c" * 64}
    record_cache_observation("m-test", cached_input=5)
    assert reg.resolve_expose_counter("m-test", [entry]) is None
    assert reg.resolve_expose_counter("m-test", [entry]) is None
    assert reg.cache_protection_metrics("m-test")["discarded"] == 2


def test_register_adapter_clears_cache_window(isolated_state) -> None:
    """휘발성 상태는 재등록(기동·재검증 반영)으로 해제된다."""
    register_adapter(_adapter(cache_ok=False))
    record_cache_observation("m-test", cached_input=7)
    assert reg._cache_observed_active("m-test")
    register_adapter(_adapter(cache_ok=False))
    assert not reg._cache_observed_active("m-test")


def test_undercount_still_suspends_even_with_cache_validated(
        isolated_state, monkeypatch) -> None:
    """undercount 검사는 캐시 검증 여부와 무관하게 존속(P0 불변식)."""
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_AUDIT_HMAC_KEY", b"k" * 48)
    register_adapter(_adapter(cache_ok=True))
    reg.record_count_observation("m-test", counted=100, reported=150)
    assert reg._VALIDATION["m-test"] == "SUSPENDED"


# ── tombstone 지속 + 새 identity 해소 ───────────────────────────────────


def test_tombstone_persists_new_identity_clears(
        isolated_state, monkeypatch) -> None:
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_AUDIT_HMAC_KEY", b"k" * 48)
    old = _adapter()
    register_adapter(old)
    # tombstone 유발은 **실제 계수 계약 위반**(undercount)으로 한다 —
    # 캐시 적중은 2026-08-04부터 tombstone 사유가 아니다.
    reg.record_count_observation("m-test", counted=100, reported=150)
    suspended, ok = reg._is_globally_suspended(adapter_identity_hash(old))
    assert suspended and ok
    # state 파일 삭제로도 부활 불가(ledger tombstone)
    (isolated_state / "adapter_suspensions.json").unlink()
    suspended, ok = reg._is_globally_suspended(adapter_identity_hash(old))
    assert suspended and ok
    # 새 counter_version → 새 identity — tombstone 미적용
    new = TokenCounterAdapter(
        model_id="m-test", mode="PROVIDER_EXACT", counter=len,
        provider_id="gemini", counter_version="r-test-2",
        validation_corpus_hash="d" * 64, cache_path_validated=True)
    suspended, ok = reg._is_globally_suspended(adapter_identity_hash(new))
    assert not suspended and ok


# ── validation lease ────────────────────────────────────────────────────


def test_lease_roundtrip_and_expiry(isolated_state, monkeypatch) -> None:
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_AUDIT_HMAC_KEY", b"k" * 48)
    a = _adapter()
    identity = adapter_identity_hash(a)
    lease_mod.write_lease(
        model_id="m-test", identity_hash=identity,
        reported_model_version="m-test-001",
        samples_summary={"native_samples": 39})
    body = lease_mod.load_valid_lease("m-test", identity)
    assert body is not None
    assert body["reported_model_version"] == "m-test-001"
    # identity 불일치 → None
    assert lease_mod.load_valid_lease("m-test", "0" * 16) is None
    # 만료 lease → None
    lease_mod.write_lease(
        model_id="m-test", identity_hash=identity,
        reported_model_version="m-test-001", samples_summary={},
        validated_at=datetime.now(UTC) - timedelta(days=8))
    assert lease_mod.load_valid_lease("m-test", identity) is None


def test_lease_runway_requirement(isolated_state, monkeypatch) -> None:
    """만료 임박(runway<12h) lease는 기동 부적격 — require_runway=False로만
    통과(런타임 대조 용도)."""
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_AUDIT_HMAC_KEY", b"k" * 48)
    a = _adapter()
    identity = adapter_identity_hash(a)
    lease_mod.write_lease(
        model_id="m-test", identity_hash=identity,
        reported_model_version="v", samples_summary={},
        validated_at=datetime.now(UTC)
        - timedelta(days=lease_mod.LEASE_TTL_DAYS) + timedelta(hours=2))
    assert lease_mod.load_valid_lease("m-test", identity) is None
    assert lease_mod.load_valid_lease(
        "m-test", identity, require_runway=False) is not None


def test_lease_tamper_and_invalidate(isolated_state, monkeypatch) -> None:
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_AUDIT_HMAC_KEY", b"k" * 48)
    a = _adapter()
    identity = adapter_identity_hash(a)
    path = lease_mod.write_lease(
        model_id="m-test", identity_hash=identity,
        reported_model_version="v1", samples_summary={})
    record = json.loads(path.read_text("utf-8"))
    record["body"]["reported_model_version"] = "v2"  # 위조
    path.write_text(json.dumps(record), encoding="utf-8")
    assert lease_mod.load_valid_lease("m-test", identity) is None
    # invalidate — 서명 제거로 이후 load 실패(UNVALIDATED 경로)
    lease_mod.write_lease(model_id="m-test", identity_hash=identity,
                          reported_model_version="v1", samples_summary={})
    lease_mod.invalidate_lease("m-test", "MODEL_VERSION_MISMATCH:test")
    assert lease_mod.load_valid_lease("m-test", identity) is None


# ── UNVALIDATED 상태(사고 아님 — tombstone 미적용) ──────────────────────


def test_unvalidated_state_registered_and_blocks_expose(
        isolated_state) -> None:
    register_adapter(_adapter())
    reg.set_validation_state("m-test", "UNVALIDATED")
    assert reg.resolve_validated_counter("m-test") is None  # EXPOSE 불가
    # tombstone 없음 — 재검증(VALIDATED 파생)으로 복귀 가능
    assert not (isolated_state
                / "adapter_suspensions_ledger.jsonl").exists()


# ── shape별 프레이밍 오버헤드 ───────────────────────────────────────────


def test_framing_overhead_lookup() -> None:
    a = _adapter(overhead=(("shape-a", 2), ("shape-b", 0)))
    assert a.framing_overhead_for("shape-a") == 2
    assert a.framing_overhead_for("shape-b") == 0
    assert a.framing_overhead_for("unknown") == 0


# ── 테스트 게이트 1: 정규화 shape digest 안정성 ─────────────────────────


def test_gate1_shape_digest_stable_under_dynamic_input() -> None:
    """동적 사용자 입력·명식·기간이 바뀌어도 digest 동일, 구조 변경 시 상이."""
    schema = json.dumps({"type": "object", "properties": {
        "main_answer": {"type": "string"}}})

    def _req(question: str) -> ProviderRequest:
        return ProviderRequest(
            system_messages=("시스템 지시",),
            user_messages=(question,), output_schema=schema)

    d1 = request_shape_digest("INITIAL", _req("2026년 이직 시기 알려줘"))
    d2 = request_shape_digest(
        "INITIAL", _req("1988년생 갑자일주, 2027년 하반기 계약 위험은?"))
    assert d1 == d2  # 동적 본문 변경 → digest 불변
    d3 = request_shape_digest("REVISION_1", _req("같은 질문"))
    assert d3 != d1  # attempt 구조 변경 → digest 변경
    d4 = request_shape_digest("INITIAL", ProviderRequest(
        system_messages=("시스템 지시",), user_messages=("q",)))
    assert d4 != d1  # output schema 존재 여부 → digest 변경
