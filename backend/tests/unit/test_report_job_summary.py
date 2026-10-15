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


# ── 주 대상 라벨은 kind 가 아니라 등록 관계로(2026-10-15 데굴님 승인) ───────────────────

def _self_label(relation_to_user) -> str:
    subj = {"kind": "self", "label": "박여사"}
    if relation_to_user != "ABSENT":
        subj["relation_to_user"] = relation_to_user
    s = job_summary(_row({"product_code": "RPT_FULL", "subjects": [subj]}))
    return s.subjects[0].relation_label


def test_primary_subject_label_follows_registered_relation() -> None:
    """어머니 총운을 만들면 '박여사(본인)'이 아니라 '박여사(어머니)'."""
    assert _self_label("mother") == "어머니"
    assert _self_label("self") == "본인"


def test_primary_subject_unset_relation_is_not_assumed_self() -> None:
    assert _self_label("") == "관계 미설정"


def test_legacy_job_without_relation_field_keeps_self_label() -> None:
    assert _self_label("ABSENT") == "본인"
    assert _self_label(None) == "본인"


def test_companion_stored_relation_key_is_translated_not_leaked() -> None:
    """등록 관계 키가 그대로 저장된 잡 — 테마 어휘로 번역해 라벨링, 번역 불가(other)는 등록 한글.
    영문 키('mother')가 목록에 그대로 뜨던 결함(2026-10-15 실측)의 반례."""
    s = job_summary(_row({
        "product_code": "RPT_FOCUS", "topic": "relationship",
        "period": {"start": "2026-10", "end": "2031-12"},
        "subjects": [{"kind": "self", "label": "데굴", "relation_to_user": "self"},
                     {"kind": "companion", "label": "박여사", "relation_type": "mother"},
                     {"kind": "companion", "label": "김철수", "relation_type": "husband"},
                     {"kind": "companion", "label": "누군가", "relation_type": "other"}],
    }))
    labels = [x.relation_label for x in s.subjects]
    assert labels == ["본인", "부모·자녀", "배우자(기혼)", "기타"]
    assert not any(lbl.isascii() for lbl in labels)
