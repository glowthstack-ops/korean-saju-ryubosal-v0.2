"""P2-3b dual-run 감사 적재기 — redacted JSONL (2026-07-28 데굴님 확정).

`_process_log`(uvicorn 로그)를 판단 자료의 SSOT로 쓰지 않는다. 로그는 다중 worker 출력이
섞이고, 포맷 변경에 취약하며, 스택트레이스와 감사 행이 뒤섞이고, 로테이션 때 일부가
사라진다 — 요청 단위 중복·누락을 검증할 수 없다. 집계는 이 구조화된 행을 읽는다.

**저장하지 않는 것**(계약): 질문 원문 · `scope_evidence_text` · 대화 내용 · 사용자 이름 ·
생년월일·출생지 · LLM 프롬프트 · Episode 본문. `subject_id`는 그대로 쓰지 않고 서버
비밀키 기반 HMAC으로 치환한다(단순 SHA-256은 입력값을 추측할 수 있다).

**fail-open**: 감사 기록 실패가 사용자 응답을 실패시키지 않는다. 어떤 예외가 나도
호출자는 legacy 결과를 그대로 반환하며, 후보 scope·`SOURCE_UNAVAILABLE` 판정은 감사
실패의 영향을 받지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .process_dual_run import DualRunAudit

_logger = logging.getLogger(__name__)

#: 스키마 버전 — 행 구조가 바뀌면 올린다(집계 스크립트가 분기한다).
SCHEMA_VERSION = 1

#: 적재 경로. 컨테이너 임시 경로를 쓰지 않는다 — 재기동 때 사라지는 JSONL은 판단
#: 자료로 쓸 수 없다. 기본값은 호스트에서 보존되는 `backend/var/audit/…`.
_DEFAULT_DIR = Path(__file__).resolve().parents[3] / "var" / "audit" / "p2_process_dual_run"

#: 요청·주체 식별자를 가리는 키. 운영 키는 `P2_AUDIT_HMAC_KEY_B64`(base64, 32바이트
#: 이상)로 주입한다 — 소스·로그에 값을 남기지 않는다. 미설정 시 개발용 기본키다.
_DEV_KEY = b"dev-only-p2-audit-rotate-before-canary"


def _audit_key() -> bytes:
    """감사용 HMAC 키 — 미설정·비정상이면 개발 기본키."""
    raw = (os.environ.get("P2_AUDIT_HMAC_KEY_B64") or "").strip()
    if not raw:
        return _DEV_KEY
    import base64

    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:  # noqa: BLE001 — 비정상 인코딩은 기본키로 폴백
        return _DEV_KEY
    return key if len(key) >= 32 else _DEV_KEY


def pseudonymize(value: str | None, *, prefix: str = "hmac") -> str | None:
    """식별자를 키 기반 HMAC으로 치환한다.

    Args:
        value: 원본 식별자(`subject_id` 등).
        prefix: 결과 접두사.

    Returns:
        `prefix:<hex 24>` 형태. 입력이 비면 None.
    """
    if not value:
        return None
    digest = hmac.new(_audit_key(), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}:{digest[:24]}"


def audit_record_id(request_id: str) -> str:
    """요청당 결정적 감사 ID — 재시도로 같은 행이 두 번 적재돼도 집계에서 제거된다."""
    material = f"{request_id}p2-process-dual-run-v1"
    return hmac.new(_audit_key(), material.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


@dataclass(frozen=True)
class DualRunAuditContext:
    """행에 함께 남길 요청 맥락 — **원문·프로필은 받지 않는다.**"""

    request_id: str
    surface: str = "chat"
    intent: str = ""
    subject_id: str | None = None
    process_source_status: str = ""


def build_record(
    audit: DualRunAudit, context: DualRunAuditContext, *, now: datetime | None = None
) -> dict:
    """감사 행 1건을 만든다(순수 함수 — 파일을 건드리지 않는다).

    후보 전체를 남기지 않는다. **membership이 바뀐 후보만** `changes`에 넣는다 —
    변화 없는 후보까지 적재하면 행이 수십 배로 커지면서 분석 가치는 늘지 않는다.

    Args:
        audit: 비교 결과.
        context: 요청 맥락(식별자는 치환된다).
        now: 생성 시각(테스트 주입용).

    Returns:
        JSON 직렬화 가능한 dict.
    """
    stamp = (now or datetime.now(UTC)).isoformat()
    changed = [
        c
        for c in audit.candidates
        if c.legacy_top_n != c.scoped_top_n
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_record_id": audit_record_id(context.request_id),
        "created_at": stamp,
        "request_id": context.request_id,
        "worker_id": os.getpid(),
        "surface": context.surface,
        "intent": context.intent,
        "subject_ref": pseudonymize(context.subject_id),
        "process_source_status": context.process_source_status,
        **{k: v for k, v in audit.summary().items()},
        "changes": [
            {
                "candidate_id": pseudonymize(c.candidate_id, prefix="cand"),
                "event_key": c.event_key,
                "period_key": c.period,
                "legacy_rank": c.legacy_rank,
                "scoped_rank": c.scoped_rank,
                "raw_event_scope": c.raw_event_scope,
                "gate_action": c.gate_action,
                "comparison_result": c.comparison_result.value,
                # 규칙 id·단계·범위만 남긴다. 근거 구절(scope_evidence_text)은 금지.
                "active_process_matches": [
                    {k: v for k, v in m.items() if k != "process_fact_id"}
                    for m in c.active_process_matches
                ],
            }
            for c in changed
        ],
    }


def audit_dir() -> Path:
    """적재 디렉터리 — `P2_PROCESS_DUAL_RUN_AUDIT_PATH`로 덮어쓸 수 있다."""
    raw = (os.environ.get("P2_PROCESS_DUAL_RUN_AUDIT_PATH") or "").strip()
    return Path(raw) if raw else _DEFAULT_DIR


def audit_path(now: datetime | None = None) -> Path:
    """오늘자·이 워커의 파일 경로.

    하나의 파일을 여러 프로세스가 공유하지 않는다 — 멀티 워커에서 행이 섞이거나
    잘린다. 날짜 + pid로 나눈다.
    """
    stamp = (now or datetime.now(UTC)).astimezone().strftime("%Y-%m-%d")
    return audit_dir() / f"p2-dual-run-{stamp}-{os.getpid()}.jsonl"


def append_audit(
    audit: DualRunAudit, context: DualRunAuditContext, *, now: datetime | None = None
) -> bool:
    """감사 행을 append한다. **어떤 실패도 밖으로 던지지 않는다.**

    Args:
        audit: 비교 결과.
        context: 요청 맥락.
        now: 생성 시각(테스트 주입용).

    Returns:
        기록 성공 여부. 실패해도 호출자는 legacy 결과를 그대로 반환해야 한다.
    """
    try:
        record = build_record(audit, context, now=now)
        path = audit_path(now)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001 — 감사 실패가 사용자 응답을 깨지 않는다
        _logger.exception("p2_dual_run_audit_write_failed")
        return False


__all__ = [
    "SCHEMA_VERSION",
    "DualRunAuditContext",
    "append_audit",
    "audit_dir",
    "audit_path",
    "audit_record_id",
    "build_record",
    "pseudonymize",
]
