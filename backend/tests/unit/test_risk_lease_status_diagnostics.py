"""lease 진단 상태(lease_status) — 7상태 + 우선순위 고정.

배경(2026-08-04): `/health` 가 `RISK_BOOTSTRAP_LEASE_INVALID` 하나로
만료·서명 오류·identity 불일치를 합쳐 보고해 운영 대응(재검증 / 변조
조사 / manifest 재감수 / 배포 확인)을 구분할 수 없었다. 상태별 대응이
다르므로 각 상태를 개별 회귀로 고정한다.

게이트 판정(load_valid_lease)은 변경 대상이 아니다 — 본 테스트는 진단
전용 함수만 검증한다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from saju_api.services import risk_validation_lease as lease_mod
from saju_api.services.risk_validation_lease import (
    LEASE_STATUS_EXPIRED,
    LEASE_STATUS_EXPIRING,
    LEASE_STATUS_IDENTITY_MISMATCH,
    LEASE_STATUS_INVALIDATED,
    LEASE_STATUS_MISSING,
    LEASE_STATUS_SIGNATURE_INVALID,
    LEASE_STATUS_VALID,
    invalidate_lease,
    lease_path,
    lease_status,
    write_lease,
)

_MODEL = "m-lease-test"
_IDENTITY = "a1b2c3d4e5f60718"


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """lease 저장소를 임시 디렉터리로 격리(운영 var/ 미접촉)."""
    monkeypatch.setattr(lease_mod, "_STATE_DIR", tmp_path)
    return tmp_path


def _write(*, hours_left: float = 24 * 7,
           identity: str = _IDENTITY) -> None:
    """잔여 유효기간을 지정해 서명이 유효한 lease를 기록한다."""
    validated_at = (datetime.now(UTC) + timedelta(hours=hours_left)
                    - timedelta(days=lease_mod.LEASE_TTL_DAYS))
    write_lease(model_id=_MODEL, identity_hash=identity,
                reported_model_version="mv-1",
                samples_summary={"native_samples": 39, "undercount": 0},
                validated_at=validated_at)


# ── 7상태 ────────────────────────────────────────────────────────────────


def test_status_valid(state_dir) -> None:
    _write()
    out = lease_status(_MODEL, _IDENTITY)
    assert out["status"] == LEASE_STATUS_VALID
    assert out["model_version"] == "mv-1"
    assert out["expires_at"] is not None


def test_status_expired(state_dir) -> None:
    _write(hours_left=-1)
    assert lease_status(_MODEL, _IDENTITY)["status"] == LEASE_STATUS_EXPIRED


def test_status_expiring_within_runway(state_dir) -> None:
    """서명·identity·유효기간이 모두 정상인 lease에만 적용된다."""
    _write(hours_left=lease_mod.MIN_RUNWAY_HOURS - 1)
    assert lease_status(_MODEL, _IDENTITY)["status"] == LEASE_STATUS_EXPIRING


def test_status_signature_invalid(state_dir) -> None:
    _write()
    path = lease_path(_MODEL)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["hmac"] = "0" * 64  # 본문 변조와 동일한 관측 결과
    path.write_text(json.dumps(record, ensure_ascii=False),
                    encoding="utf-8")
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_SIGNATURE_INVALID)


def test_status_identity_mismatch(state_dir) -> None:
    _write(identity="ffffffffffffffff")
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_IDENTITY_MISMATCH)


def test_status_missing_when_absent(state_dir) -> None:
    out = lease_status(_MODEL, _IDENTITY)
    assert out["status"] == LEASE_STATUS_MISSING
    assert out["expires_at"] is None  # 읽을 수 없으면 명시적 null


def test_status_missing_when_corrupt(state_dir) -> None:
    path = lease_path(_MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    out = lease_status(_MODEL, _IDENTITY)
    assert out["status"] == LEASE_STATUS_MISSING
    assert out["expires_at"] is None


def test_status_invalidated(state_dir) -> None:
    _write()
    invalidate_lease(_MODEL, "MODEL_VERSION_MISMATCH:x!=y")
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_INVALIDATED)


# ── 우선순위(복수 결함 동시 성립) ────────────────────────────────────────


def test_invalidated_wins_over_signature(state_dir) -> None:
    """invalidate_lease는 hmac을 제거한다 — 서명을 먼저 보면 의도적
    무효화가 변조와 구분되지 않고 INVALIDATED가 도달 불가가 된다."""
    _write()
    invalidate_lease(_MODEL, "reason")
    record = json.loads(lease_path(_MODEL).read_text(encoding="utf-8"))
    assert "hmac" not in record  # 서명 부재 = 서명 검사만 하면 오분류
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_INVALIDATED)


def test_signature_wins_over_identity_and_expiry(state_dir) -> None:
    _write(hours_left=-1, identity="ffffffffffffffff")
    path = lease_path(_MODEL)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["hmac"] = "0" * 64
    path.write_text(json.dumps(record, ensure_ascii=False),
                    encoding="utf-8")
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_SIGNATURE_INVALID)


def test_identity_wins_over_expiry(state_dir) -> None:
    """만료와 identity 불일치가 동시에 있으면 복구를 막는 근본 원인
    (identity — manifest 재감수 필요)을 보고한다."""
    _write(hours_left=-1, identity="ffffffffffffffff")
    assert (lease_status(_MODEL, _IDENTITY)["status"]
            == LEASE_STATUS_IDENTITY_MISMATCH)


def test_identity_check_skipped_when_adapter_unknown(state_dir) -> None:
    """adapter 미등록(identity None)이면 없는 identity로 MISMATCH를
    단정하지 않고 나머지 상태를 그대로 보고한다."""
    _write(hours_left=-1, identity="ffffffffffffffff")
    assert lease_status(_MODEL, None)["status"] == LEASE_STATUS_EXPIRED


# ── 게이트 동작 불변(진단 추가가 자격 판정을 바꾸지 않는다) ──────────────


def test_load_valid_lease_unchanged(state_dir) -> None:
    _write()
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is not None
    assert lease_mod.load_valid_lease(_MODEL, "ffffffffffffffff") is None
    _write(hours_left=-1)
    assert lease_mod.load_valid_lease(_MODEL, _IDENTITY) is None
