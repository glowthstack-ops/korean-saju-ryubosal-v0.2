"""리포트 잡 실행기 × LLM 서비스 중단 — 보류(부분 보존)·재개 컨텍스트 (2026-10-06).

저장소는 가짜 객체로 대체해 DB 없이 전이만 검증한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from saju_api.services import report_job_runner as runner
from saju_api.services.llm_client import LLMServiceSuspended
from saju_engines.report_job_store import SUSPENDED_MARKER
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec, SectionResult

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1990-05-05", birth_time="12:00",
    birth_place_name="서울", gender="male",
)
_SPEC = ReportSpec(
    product_code="RPT_FOCUS",
    subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
    topic="career", period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
)


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def mark_running(self, job_id: str) -> None:
        self.calls.append(("running", job_id))

    def update_progress(self, *a: Any) -> None:
        pass

    def complete(self, job_id: str, result: dict, n: int) -> None:
        self.calls.append(("complete", (job_id, n)))

    def suspend(self, job_id: str, payload: dict, sections_done: int) -> None:
        self.calls.append(("suspend", (job_id, payload, sections_done)))

    def fail(self, job_id: str, error: str) -> None:
        self.calls.append(("fail", (job_id, error)))


def _sec(sid: str, passed: bool = True) -> SectionResult:
    return SectionResult(section_id=sid, title=sid, text="본문", passed=passed, attempts=1)


def test_suspension_mid_report_preserves_passed_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    """생성 중 중단 → suspend(부분 보존 payload) 호출, fail 아님, 재실행 컨텍스트 포함."""
    store = _FakeStore()

    def _generate(*_a: Any, section_sink=None, prior_sections=None, **_k: Any):
        # 섹션 두 개 확정(하나는 실패) 후 서비스 중단.
        section_sink(_sec("C-01"))
        section_sink(_sec("C-02", passed=False))
        section_sink(_sec("C-03"))
        raise LLMServiceSuspended("suspended")

    monkeypatch.setattr(runner.report_service, "generate_report", _generate)
    runner.run_report_job(
        "job1", _BIRTH, _SPEC, date(2026, 6, 1), "길동", "owner", "subj", None, store=store,
    )
    kinds = [k for k, _ in store.calls]
    assert kinds == ["running", "suspend"]
    _, (job_id, payload, done) = store.calls[1]
    assert job_id == "job1" and done == 2
    assert [s["section_id"] for s in payload["partial_sections"]] == ["C-01", "C-03"]
    assert payload["resume"] == {"subject_id": "subj", "today": "2026-06-01", "display_name": "길동"}


def test_prior_sections_flow_into_generate_and_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    """재개 실행 — prior 가 generate_report 로 전달되고, 다시 중단되면 prior 도 보존에 포함."""
    store = _FakeStore()
    seen: dict[str, Any] = {}

    def _generate(*_a: Any, section_sink=None, prior_sections=None, **_k: Any):
        seen["prior"] = prior_sections
        section_sink(_sec("C-04"))
        raise LLMServiceSuspended("again")

    monkeypatch.setattr(runner.report_service, "generate_report", _generate)
    prior = {"C-01": _sec("C-01"), "C-02": _sec("C-02", passed=False)}
    runner.run_report_job(
        "job2", _BIRTH, _SPEC, None, "길동", "owner", "subj", None,
        prior_sections=prior, store=store,
    )
    assert seen["prior"] is prior
    _, (_, payload, done) = store.calls[1]
    assert sorted(s["section_id"] for s in payload["partial_sections"]) == ["C-01", "C-04"]
    assert done == 2 and payload["resume"]["today"] is None


def test_runtime_error_still_fails_job(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()

    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("LLM 모의 실패")

    monkeypatch.setattr(runner.report_service, "generate_report", _boom)
    runner.run_report_job("job3", _BIRTH, _SPEC, None, "길동", "owner", "subj", None, store=store)
    assert store.calls[1] == ("fail", ("job3", "LLM 모의 실패"))


def test_resume_suspended_job_rebuilds_prior_from_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """클레임된 보류 레코드 → payload 의 통과 섹션만 prior 로 복원해 실행기에 넘긴다."""

    class _Rec:
        job_id = "job4"
        owner_id = "owner"
        spec = _SPEC.model_dump(mode="json")
        result = {
            "resume": {"subject_id": "subj", "today": "2026-06-01", "display_name": "길동"},
            "partial_sections": [
                _sec("C-01").model_dump(mode="json"),
                _sec("C-02", passed=False).model_dump(mode="json"),
                {"broken": True},
            ],
        }
        error = SUSPENDED_MARKER

    class _SubjRec:
        owner_id = "owner"
        birth = _BIRTH
        label = "길동"

    class _Subjects:
        def get(self, sid: str):
            return _SubjRec() if sid == "subj" else None

    captured: dict[str, Any] = {}

    def _run(job_id, birth, spec, today, display_name, owner_id, subject_id, partner_birth,
             *, prior_sections=None, store=None):
        captured.update(job_id=job_id, today=today, prior=prior_sections, subject_id=subject_id)

    monkeypatch.setattr(runner, "run_report_job", _run)
    out = runner.resume_suspended_job(_Rec(), _Subjects(), _FakeStore())
    assert out == {"job_id": "job4", "resumed": True, "reused_sections": 1}
    assert captured["today"] == date(2026, 6, 1) and list(captured["prior"]) == ["C-01"]


def test_resume_suspended_job_fails_when_subject_missing() -> None:
    class _Rec:
        job_id = "job5"
        owner_id = "owner"
        spec = _SPEC.model_dump(mode="json")
        result = {"resume": {"subject_id": "gone"}, "partial_sections": []}
        error = SUSPENDED_MARKER

    class _Subjects:
        def get(self, sid: str):
            return None

    store = _FakeStore()
    out = runner.resume_suspended_job(_Rec(), _Subjects(), store)
    assert out["resumed"] is False and out["reason"] == "subject_missing"
    assert store.calls[0][0] == "fail"
