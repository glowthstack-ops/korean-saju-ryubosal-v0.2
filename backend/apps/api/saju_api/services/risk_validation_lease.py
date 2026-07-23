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

__all__ = ["LEASE_TTL_DAYS", "MIN_RUNWAY_HOURS", "invalidate_lease",
           "lease_path", "load_valid_lease", "write_lease"]

_logger = logging.getLogger("saju_api.risk")

LEASE_TTL_DAYS = 7  # Preview 모델 — 백엔드 버전 변동 대비 짧은 유효기간
MIN_RUNWAY_HOURS = 12  # 기동 시 최소 잔여 유효기간(만료 임박 기동 방지)

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
