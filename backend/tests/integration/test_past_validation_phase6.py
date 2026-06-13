"""Phase 6 Past Validation 검증 (T6.1~T6.4 — docs/02 E7·docs/01 신뢰 형성 플로우)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saju_api.main import app
from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines.cases_store import CaseRow, CasesStore
from saju_engines.past_validation import calibrate_confidence, generate_past_candidates
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.past_validation import PastFeedbackItem

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
client = TestClient(app)

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


@pytest.fixture(scope="module")
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def result(scorer):
    """과거 2000~2020 후보(역방향 — Phase 2 재사용)."""
    return generate_past_candidates(_BIRTH, scorer, calculate, 2000, 2020)


# ── T6.1 — 역방향 후보 생성(콜드리딩 방지 규칙) ───────────────────


def test_candidates_cover_range_with_strict_rules(result) -> None:
    """기간 내 연도만 + 연도당 ≤2건 + score≥70 + evidence path 필수."""
    assert result.candidates, "20년 구간에서 강한 신호가 있어야 함"
    per_year: dict[str, int] = {}
    for c in result.candidates:
        year = int(c.year_range[:4])
        assert 2000 <= year <= 2020
        assert c.score >= 70  # 엄격 임계
        assert c.evidence_path  # 근거 없는 후보 금지
        per_year[c.year_range] = per_year.get(c.year_range, 0) + 1
    assert max(per_year.values()) <= 2  # 연도당 후보 2개 이하(docs/07 리스크 3)


def test_candidates_have_readable_paths(result) -> None:
    """모든 후보에 사람용 근거 경로 — '2009 입학 ← 정관 활성' 형태의 원천."""
    assert all(c.readable for c in result.candidates)


def test_candidates_deterministic(scorer) -> None:
    """동일 입력 → 동일 후보(결정론)."""
    a = generate_past_candidates(_BIRTH, scorer, calculate, 2010, 2015)
    b = generate_past_candidates(_BIRTH, scorer, calculate, 2010, 2015)
    assert a.model_dump() == b.model_dump()


# ── T6.3 — Confidence Calibration ────────────────────────────────


def test_calibration_levels() -> None:
    """맞춘 비율 → 표현 강도 3단계(미래 예측 보수화)."""
    def fb(matched_flags: list[bool]) -> list[PastFeedbackItem]:
        return [
            PastFeedbackItem(
                year_range="2010", event_key=EventKey.CAREER_CHANGE, matched=m,
            )
            for m in matched_flags
        ]

    good = calibrate_confidence(fb([True, True, True, False]))
    assert good.expression_level == "normal" and good.calibrated_confidence == 0.75

    partial = calibrate_confidence(fb([True, False, False]))
    assert partial.expression_level == "conservative"

    poor = calibrate_confidence(fb([False, False, False, True]))
    assert poor.expression_level == "conservative" or poor.calibrated_confidence == 0.25
    none_yet = calibrate_confidence([])
    assert none_yet.expression_level == "conservative" and none_yet.total == 0

    very_poor = calibrate_confidence(fb([False, False, False, False]))
    assert very_poor.expression_level == "very_conservative"


# ── T6.2 — cases.jsonl 적재(docs/05 스키마) ──────────────────────


def test_cases_store_roundtrip(tmp_path: Path) -> None:
    """append → load 왕복 + docs/05 camelCase 키 직렬화."""
    store = CasesStore(tmp_path / "cases.jsonl")
    store.append(CaseRow(
        case_id="case_001",
        signals=["甲己合", "정관", "기신"],
        predicted_event="career_change",
        actual_event="unwanted_relocation",
        time="2026-06",
        matched=True,
        notes="정관합이 이동/배치 변경으로 발현",
    ))
    rows = store.load()
    assert len(rows) == 1 and rows[0].predicted_event == "career_change"
    raw = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert '"caseId"' in raw and '"predictedEvent"' in raw  # docs/05 키 그대로
    assert store.next_case_id() == "case_002"


# ── T6.4 — API(온보딩 연동) ──────────────────────────────────────


def test_api_candidates_endpoint() -> None:
    """POST /api/v2/past-validation — 후보 + 근거 경로."""
    res = client.post("/api/v2/past-validation", json={
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22",
            "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
            "reference_date": "2026-06-11",
        },
        "start_year": 2010, "end_year": 2015,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["candidates"]
    assert all(c["evidence_path"] for c in body["candidates"])


def test_api_feedback_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /feedback — cases.jsonl 적재 + 신뢰도 반환."""
    import saju_api.routers.past_validation as pv_router
    from saju_engines import cases_store as cs

    monkeypatch.setattr(cs, "_DEFAULT_PATH", tmp_path / "cases.jsonl")
    monkeypatch.setattr(pv_router, "CasesStore", lambda: cs.CasesStore(tmp_path / "c.jsonl"))

    res = client.post("/api/v2/past-validation/feedback", json={
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22",
            "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
        },
        "feedback": [
            {"year_range": "2010", "event_key": "career_change", "matched": True},
            {"year_range": "2014", "event_key": "relocation", "matched": False,
             "actual_event": "유학"},
        ],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2 and body["matched"] == 1
    assert body["expression_level"] in ("normal", "conservative", "very_conservative")
    # 적재 확인.
    saved = cs.CasesStore(tmp_path / "c.jsonl").load()
    assert len(saved) == 2 and saved[1].actual_event == "유학"
