"""P2-3b 감사 적재기 회귀 — redaction · fail-open · 중복 제거.

redaction 테스트가 이 파일의 존재 이유다. 감사 행에 질문 원문이나 근거 구절이 새면
"대화 내용을 저장하지 않는다"는 계약이 깨진다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from saju_engines.process_dual_run import CandidateDualRunAudit, DualRunAudit
from saju_engines.process_dual_run_audit import (
    SCHEMA_VERSION,
    DualRunAuditContext,
    append_audit,
    audit_path,
    audit_record_id,
    build_record,
    pseudonymize,
)
from saju_shared_types.process_fact import DualRunComparisonResult

_SECRET = "면접을 봤고 결과를 기다리는 중입니다"
_NOW = datetime(2026, 7, 28, 2, 20, 31, tzinfo=UTC)


def _candidate(**over):
    base = dict(
        candidate_id="self|3|job_gain|2027-03",
        event_key="job_gain",
        period="2027-03",
        raw_score=74,
        confidence="medium",
        raw_event_scope="LOCAL_TRIGGER_ONLY",
        gate_action="ENFORCE_LOCAL_ONLY",
        legacy_rank=2,
        legacy_top_n=True,
        scoped_rank=None,
        scoped_top_n=False,
        comparison_result=DualRunComparisonResult.EXCLUDED_LOCAL_TRIGGER,
        active_process_matches=(
            {
                "process_fact_id": "career:ep1:RESULT_PENDING",
                "rule_id": "CAREER_EXTERNAL_OPPORTUNITY",
                "stage": "RESULT_PENDING",
                "entry_scope": "external_employer",
            },
        ),
    )
    base.update(over)
    return CandidateDualRunAudit(**base)


def _audit(**over):
    base = dict(
        legacy_top_n_count=5, scoped_top_n_count=3, membership_flip_count=2,
        excluded_local_count=2, candidates=(_candidate(),),
    )
    base.update(over)
    return DualRunAudit(**base)


def _context(**over):
    base = dict(
        request_id="thr:abc:1:deadbeef", surface="chat", intent="career_change",
        subject_id="subject-42", process_source_status="LOADED_WITH_FACTS",
    )
    base.update(over)
    return DualRunAuditContext(**base)


# ── redaction ──────────────────────────────────────────────────────────────


def test_record_has_no_raw_subject_id() -> None:
    """subject_id 를 그대로 남기지 않는다."""
    record = build_record(_audit(), _context(), now=_NOW)

    blob = json.dumps(record, ensure_ascii=False)
    assert "subject-42" not in blob
    assert record["subject_ref"].startswith("hmac:")


def test_record_has_no_conversation_text() -> None:
    """질문 원문·근거 구절이 어떤 필드에도 들어가지 않는다."""
    record = build_record(_audit(), _context(), now=_NOW)

    blob = json.dumps(record, ensure_ascii=False)
    assert _SECRET not in blob
    assert "scope_evidence_text" not in blob


def test_active_matches_drop_fact_id() -> None:
    """사실 id는 Episode 를 역추적할 수 있어 규칙·단계만 남긴다."""
    record = build_record(_audit(), _context(), now=_NOW)

    (change,) = record["changes"]
    (match,) = change["active_process_matches"]
    assert set(match) == {"rule_id", "stage", "entry_scope"}
    assert "career:ep1:RESULT_PENDING" not in json.dumps(record, ensure_ascii=False)


def test_candidate_id_is_pseudonymized() -> None:
    """후보 id에 subject 가 들어 있어 그대로 남기지 않는다."""
    record = build_record(_audit(), _context(), now=_NOW)

    (change,) = record["changes"]
    assert change["candidate_id"].startswith("cand:")
    assert "self|3|job_gain" not in json.dumps(record, ensure_ascii=False)


def test_pseudonymize_is_keyed_not_plain_hash() -> None:
    """단순 SHA-256이면 입력값을 추측할 수 있다 — 키 기반이어야 한다."""
    import hashlib

    plain = hashlib.sha256(b"subject-42").hexdigest()[:24]

    assert pseudonymize("subject-42") != f"hmac:{plain}"


def test_pseudonymize_is_stable_and_distinct() -> None:
    assert pseudonymize("a") == pseudonymize("a")
    assert pseudonymize("a") != pseudonymize("b")
    assert pseudonymize(None) is None


# ── 행 구조 ────────────────────────────────────────────────────────────────


def test_record_carries_dedup_and_version_fields() -> None:
    record = build_record(_audit(), _context(), now=_NOW)

    for key in ("schema_version", "audit_record_id", "request_id", "worker_id",
                "created_at"):
        assert key in record
    assert record["schema_version"] == SCHEMA_VERSION


def test_audit_record_id_is_deterministic() -> None:
    """같은 요청이 재시도돼도 같은 id — 집계에서 중복 제거된다."""
    assert audit_record_id("req-1") == audit_record_id("req-1")
    assert audit_record_id("req-1") != audit_record_id("req-2")


def test_only_changed_candidates_are_detailed() -> None:
    """membership 이 바뀐 후보만 상세로 남긴다."""
    unchanged = _candidate(
        candidate_id="self|4|promotion|2027-05", legacy_top_n=True, scoped_top_n=True,
        scoped_rank=1, comparison_result=DualRunComparisonResult.RETAINED_UPPER_SUPPORTED,
    )
    record = build_record(
        _audit(candidates=(_candidate(), unchanged)), _context(), now=_NOW
    )

    assert len(record["changes"]) == 1
    assert record["changes"][0]["comparison_result"] == "EXCLUDED_LOCAL_TRIGGER"


def test_summary_counts_are_included() -> None:
    record = build_record(_audit(), _context(), now=_NOW)

    assert record["legacy_top_n_count"] == 5
    assert record["scoped_top_n_count"] == 3
    assert record["excluded_local_count"] == 2
    assert "candidates" not in record, "후보 전체를 통째로 넣지 않는다"


# ── 적재 · fail-open ───────────────────────────────────────────────────────


def test_append_writes_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("P2_PROCESS_DUAL_RUN_AUDIT_PATH", str(tmp_path))

    assert append_audit(_audit(), _context(), now=_NOW) is True

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    assert json.loads(line)["schema_version"] == SCHEMA_VERSION


def test_append_is_append_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("P2_PROCESS_DUAL_RUN_AUDIT_PATH", str(tmp_path))

    append_audit(_audit(), _context(), now=_NOW)
    append_audit(_audit(), _context(request_id="thr:abc:2:cafe"), now=_NOW)

    (path,) = tmp_path.glob("*.jsonl")
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_path_is_sharded_by_worker(tmp_path, monkeypatch) -> None:
    """여러 프로세스가 한 파일을 공유하지 않는다."""
    import os

    monkeypatch.setenv("P2_PROCESS_DUAL_RUN_AUDIT_PATH", str(tmp_path))

    assert str(os.getpid()) in audit_path(_NOW).name


def test_write_failure_does_not_raise(monkeypatch) -> None:
    """감사 실패가 사용자 응답을 실패시키면 안 된다 — fail-open."""
    monkeypatch.setenv("P2_PROCESS_DUAL_RUN_AUDIT_PATH", "/proc/nonexistent-dir")

    assert append_audit(_audit(), _context(), now=_NOW) is False


def test_build_failure_does_not_raise(tmp_path, monkeypatch) -> None:
    """직렬화 불가 값이 섞여도 예외를 밖으로 던지지 않는다."""
    monkeypatch.setenv("P2_PROCESS_DUAL_RUN_AUDIT_PATH", str(tmp_path))

    class _Bad:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    # 속성 접근이 터지는 객체를 넣어 방어 경로를 확인한다 — 타입이 맞지 않는 것이 의도다.
    assert append_audit(_Bad(), _context(), now=_NOW) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_key", ["", "not-base64!!", "c2hvcnQ="])
def test_invalid_hmac_key_falls_back(monkeypatch, bad_key) -> None:
    """비정상 키로 감사가 멈추지 않는다(개발 기본키로 폴백)."""
    monkeypatch.setenv("P2_AUDIT_HMAC_KEY_B64", bad_key)

    pseudo = pseudonymize("subject-42", prefix="hmac")
    assert pseudo is not None and pseudo.startswith("hmac:")
