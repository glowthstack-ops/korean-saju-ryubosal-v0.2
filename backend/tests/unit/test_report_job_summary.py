"""내 풀이 내역 요약 — 연도·대상·관계 선택값 표시 (2026-10-08 데굴님 지시)."""

from __future__ import annotations

from datetime import datetime

from saju_api.routers.report import job_summary


def _row(spec: dict, created="2026-10-08T01:02:03+00:00") -> dict:
    return {"job_id": "j1", "status": "completed", "spec": spec,
            "sections_done": 13, "sections_total": 13, "created_at": created}


def test_year_report_summary_has_period_and_self_relation() -> None:
    s = job_summary(_row({
        "product_code": "RPT_YEAR", "topic": None, "period": {"start": "2027-01", "end": "2027-12"},
        "subjects": [{"kind": "self", "label": "데굴", "relation_type": None}],
    }))
    assert s.period_start == "2027-01" and s.period_end == "2027-12"
    assert s.subjects[0].relation_label == "본인" and s.subject_labels == ["데굴"]
    assert s.created_at == "2026-10-08T01:02:03+00:00"


def test_companion_relation_label_and_datetime_created_at() -> None:
    s = job_summary(_row({
        "product_code": "RPT_FOCUS", "topic": "relationship",
        "period": {"start": "2026-10", "end": "2028-09"},
        "subjects": [{"kind": "self", "label": "데굴"},
                     {"kind": "companion", "label": "민수", "relation_type": "romance"},
                     {"kind": "companion", "label": "팀장", "relation_type": None}],
    }, created=datetime(2026, 10, 8, 1, 2, 3)))
    labels = [x.relation_label for x in s.subjects]
    assert labels == ["본인", "연인", "동반자"]
    assert s.created_at == "2026-10-08T01:02:03"


def test_legacy_spec_without_period_or_subjects() -> None:
    s = job_summary(_row({"product_code": "RPT_FULL"}, created=None))
    assert s.period_start is None and s.subjects == [] and s.created_at is None
