"""위험 노출 어댑터 validation lease (감수 62차 — artifact/운영 lease 분리).

Git reviewed artifact는 **불변**(검증 정책·required shapes·표본 정의)이고,
시간·실측 모델 버전 등 운영 상태는 본 모듈의 lease가 담당한다:

- lease = var/risk_state/validation_lease.json (HMAC 서명): 실제
  `reported_model_version`(paired generateContent 응답 **최상위**
  modelVersion — countTokens는 미제공)·validated_at·validation_expires_at
  (Preview 7일)·표본 결과 요약.
- 만료·모델 버전 변경·서명 불일치 = **UNVALIDATED**(tombstone 미적용 —
  재검증(lease 갱신)으로 복귀). undercount 사고(SUSPENDED)와 구분.
- 기동 시 만료뿐 아니라 `minimum_validation_runway`(잔여 12h) 미만이면
  부적격 — 만료 임박 artifact로 서버를 시작하는 문제 방지.
- 주간 lease 재검증은 스크립트 재실행으로 lease만 갱신한다(artifact·
  manifest 커밋 불필요 — identity 불변).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from saju_engines import risk_engine_config

__all__ = ["LEASE_STATUS_EXPIRED", "LEASE_STATUS_EXPIRING",
           "LEASE_STATUS_IDENTITY_MISMATCH", "LEASE_STATUS_INVALIDATED",
           "LEASE_STATUS_MISSING", "LEASE_STATUS_SIGNATURE_INVALID",
           "LEASE_STATUS_VALID", "LEASE_TTL_DAYS", "MIN_RUNWAY_HOURS",
           "invalidate_lease", "lease_path", "lease_status",
           "load_valid_lease", "write_lease"]

_logger = logging.getLogger("saju_api.risk")

LEASE_TTL_DAYS = 7  # Preview 모델 — 백엔드 버전 변동 대비 짧은 유효기간
MIN_RUNWAY_HOURS = 12  # 기동 시 최소 잔여 유효기간(만료 임박 기동 방지)

# lease 진단 상태 — 운영 대응이 상태별로 다르므로 단일 INVALID로 합치지
# 않는다(health 노출 시 "RISK_TOKEN_COUNTER_" + 값):
#   MISSING            배포 산출물·볼륨 마운트 확인
#   SIGNATURE_INVALID  변조·배포 이상 조사(또는 .env.risk 미로드)
#   INVALIDATED        invalidate_lease 호출됨 — modelVersion 변경 조사
#   IDENTITY_MISMATCH  모델·사전 변경 → manifest 재감수 필요
#   EXPIRED            재검증 실행
#   EXPIRING           만료 임박(runway 미달) — 만료 전 재검증
LEASE_STATUS_VALID = "VALID"
LEASE_STATUS_MISSING = "VALIDATION_MISSING"
LEASE_STATUS_SIGNATURE_INVALID = "LEASE_SIGNATURE_INVALID"
LEASE_STATUS_INVALIDATED = "LEASE_INVALIDATED"
LEASE_STATUS_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
LEASE_STATUS_EXPIRED = "LEASE_EXPIRED"
LEASE_STATUS_EXPIRING = "LEASE_EXPIRING"

_STATE_DIR = Path(__file__).resolve().parents[4] / "var" / "risk_state"


def lease_path(model_id: str) -> Path:
    return _STATE_DIR / f"validation_lease__{model_id}.json"


def _sign(body: dict) -> str:
    """lease 본문 HMAC 서명 — 감사 키(RISK_AUDIT_HMAC_KEY) 사용."""
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return hmac.new(risk_engine_config.RISK_AUDIT_HMAC_KEY,
                    canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def write_lease(
    *,
    model_id: str,
    identity_hash: str,
    reported_model_version: str,
    samples_summary: dict,
    validated_at: datetime | None = None,
) -> Path:
    """재검증 성공 시 lease 기록 — artifact는 불변, 시간·실측만 여기에."""
    at = validated_at or datetime.now(UTC)
    body = {
        "model_id": model_id,
        "identity_hash": identity_hash,
        "reported_model_version": reported_model_version,
        "validated_at": at.isoformat(),
        "validation_expires_at": (
            at + timedelta(days=LEASE_TTL_DAYS)).isoformat(),
        "samples_summary": samples_summary,
        "lease_id": hashlib.sha256(
            f"{model_id}|{identity_hash}|{at.isoformat()}".encode()
        ).hexdigest()[:16],
    }
    record = {"body": body, "hmac": _sign(body)}
    path = lease_path(model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1,
                               sort_keys=True), encoding="utf-8")
    return path


def load_valid_lease(model_id: str, identity_hash: str,
                     *, require_runway: bool = True) -> dict | None:
    """유효한 lease 반환 — 부재·서명 불일치·identity 불일치·만료·runway
    미달이면 None(호출측이 UNVALIDATED 처리). 사유는 로그로 남긴다."""
    path = lease_path(model_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        body = record["body"]
    except (OSError, ValueError, KeyError, TypeError):
        _logger.warning("risk_validation_lease 부재/손상 model=%s", model_id)
        return None
    if not hmac.compare_digest(_sign(body), str(record.get("hmac", ""))):
        _logger.error("risk_validation_lease 서명 불일치 model=%s", model_id)
        return None
    if body.get("identity_hash") != identity_hash:
        _logger.warning(
            "risk_validation_lease identity 불일치 model=%s (%s != %s)",
            model_id, body.get("identity_hash"), identity_hash)
        return None
    try:
        expires = datetime.fromisoformat(body["validation_expires_at"])
    except (KeyError, ValueError):
        return None
    now = datetime.now(UTC)
    if expires <= now:
        _logger.warning("risk_validation_lease 만료 model=%s expires=%s",
                        model_id, expires.isoformat())
        return None
    if require_runway and expires - now < timedelta(hours=MIN_RUNWAY_HOURS):
        _logger.warning(
            "risk_validation_lease runway 부족 model=%s 잔여=%s(<%dh)",
            model_id, expires - now, MIN_RUNWAY_HOURS)
        return None
    return body


def lease_status(model_id: str,
                 identity_hash: str | None = None) -> dict:
    """lease 진단 상태(읽기 전용 — health·운영 관측 전용).

    게이트 판정에는 쓰지 않는다: 자격 판정은 load_valid_lease가 그대로
    담당하고(시그니처·동작 불변), 본 함수는 **왜 무효인지**만 해소한다.
    두 결함이 동시에 성립하면 복구를 막는 근본 원인을 우선 보고한다:
    MISSING > INVALIDATED > SIGNATURE_INVALID > IDENTITY_MISMATCH >
    EXPIRED > EXPIRING > VALID.

    INVALIDATED를 SIGNATURE_INVALID보다 먼저 보는 이유: invalidate_lease
    가 hmac을 제거하므로 서명을 먼저 검사하면 의도적 무효화가 변조와
    구분되지 않고 상태가 도달 불가가 된다.

    Args:
        model_id: 대상 모델 ID.
        identity_hash: 현재 등록 adapter의 identity hash. None이면
            identity 대조를 건너뛴다(adapter 미등록 — artifact 결함 등).

    Returns:
        status(위 상태값) · expires_at(ISO 문자열, 읽기 불가 시 None) ·
        model_version · lease_id.
    """
    unknown: dict = {"status": LEASE_STATUS_MISSING, "expires_at": None,
                     "model_version": None, "lease_id": None}
    path = lease_path(model_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        body = record["body"]
        if not isinstance(body, dict):
            raise TypeError("body 타입 불일치")
    except (OSError, ValueError, KeyError, TypeError):
        return unknown

    expires_raw = body.get("validation_expires_at")
    try:
        expires = datetime.fromisoformat(str(expires_raw))
    except (TypeError, ValueError):
        expires = None
    out: dict = {
        "status": LEASE_STATUS_VALID,
        "expires_at": str(expires_raw) if expires is not None else None,
        "model_version": (str(body["reported_model_version"])
                          if body.get("reported_model_version") else None),
        "lease_id": (str(body["lease_id"])
                     if body.get("lease_id") else None),
    }

    if record.get("invalidated"):
        out["status"] = LEASE_STATUS_INVALIDATED
        return out
    if not hmac.compare_digest(_sign(body), str(record.get("hmac", ""))):
        out["status"] = LEASE_STATUS_SIGNATURE_INVALID
        return out
    if identity_hash is not None and body.get(
            "identity_hash") != identity_hash:
        out["status"] = LEASE_STATUS_IDENTITY_MISMATCH
        return out
    if expires is None:
        # 서명은 유효하나 만료 시각을 읽을 수 없다 = 자격 판정 불가.
        out["status"] = LEASE_STATUS_MISSING
        return out
    now = datetime.now(UTC)
    if expires <= now:
        out["status"] = LEASE_STATUS_EXPIRED
    elif expires - now < timedelta(hours=MIN_RUNWAY_HOURS):
        out["status"] = LEASE_STATUS_EXPIRING
    return out


def invalidate_lease(model_id: str, reason: str) -> None:
    """현행 lease 무효화(P0⑧ — modelVersion 변경 등) → UNVALIDATED 전환.

    tombstone(ledger)에는 기록하지 않는다 — 사고(SUSPENDED)가 아니라
    검증 실효이며 재검증으로 복귀한다. 파일은 사유 표기로 교체 보존.
    """
    path = lease_path(model_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    record["invalidated"] = {
        "reason": reason,
        "at": datetime.now(UTC).isoformat(),
    }
    record.pop("hmac", None)  # 서명 제거 — 이후 load는 반드시 실패(무효)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1,
                                   sort_keys=True), encoding="utf-8")
    except OSError:
        _logger.exception("risk_validation_lease 무효화 기록 실패 model=%s",
                          model_id)
    _logger.error("risk_validation_lease 무효화 model=%s reason=%s",
                  model_id, reason)
