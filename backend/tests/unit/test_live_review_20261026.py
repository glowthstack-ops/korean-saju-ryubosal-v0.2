"""2026-10-26 연애운 서술층 실답 감수 후속 교정 회귀.

① 결혼 시기·형태 프레임: 늦춤 신호가 없으면 **미성립 줄**을 낸다(종전엔 줄 자체가 빠져 LLM이
'늦게 하는 게 좋은 사주?' 질문 프레임에 동조). ② 女 무재 '재성 미투출' 문장은 인연 결 줄에만
본문이 있고 프레임 줄은 참조로 축약(중복 제거). ③ [혼기 경향] 축 라벨은 한글 기둥명.
④ 방위 지침 ⑩ — 블록에 없는 방향 추가 금지. ⑤ 토픽 요약 '○○ 중심'은 상위 사건 키 복수.
⑥ 시드 미등록 출생지 + 좌표 없음 → chat 422(종전 500).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import saju_engines.structural_context as sc
from saju_api.location import LocationResolveError, resolve
from saju_api.main import app
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import build_birth_summary
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.sinsal_direction import SINSAL_DIRECTION_INSTRUCTION
from saju_engines.topic_builder import _lead_event_keys
from saju_shared_types.birth_input import BirthInput

_FRAME = "결혼 시기·형태 프레임"


def _mr(y: int, m: int, d: int, hm: str, gender: str, place: str = "서울"):
    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name=place, gender=gender,
    ))
    return r, analyze_marriage_resource(r, build_birth_summary(r).useful_gods, age=None)


def test_frame_absent_line_when_no_late_signal() -> None:
    """남 1985-08-20 14:00(실답 명식): 늦춤 신호 0 → 미성립 줄 필수·'늦게가 좋다' 단정 차단."""
    _, mr = _mr(1985, 8, 20, "14:00", "male", place="부산")
    assert mr.late_marriage_notes == []  # 반례 전제 — 이 명식엔 늦춤 신호가 없다
    frame = [ln for ln in sc.marriage_resource_lines(mr) if ln.startswith(_FRAME)]
    assert len(frame) == 1
    assert "늦춤 쪽 구조 신호" in frame[0] and "없음" in frame[0]
    assert "단정하지 말고" in frame[0]


def test_frame_present_line_has_no_absent_marker_and_no_duplicate_wealth_text() -> None:
    """女 1990-05-15 10:30: 무재·비겁 과다 → 신호 줄만(미성립 문구 없음), 무재 본문은 한 줄에만."""
    _, mr = _mr(1990, 5, 15, "10:30", "female")
    assert mr.wealth_absent and mr.late_marriage_notes
    lines = sc.marriage_resource_lines(mr)
    frame = [ln for ln in lines if ln.startswith(_FRAME)]
    assert len(frame) == 1 and "늦춤 쪽 구조 신호" not in frame[0]
    assert "재성 미투출(인연 결 줄 참조)" in frame[0]
    # 본문 문장("붙잡아 유지하려는 욕구")은 인연 결 줄 한 곳에만.
    assert sum("붙잡아 유지하려는 욕구" in ln for ln in lines) == 1


def test_age_prior_positions_are_korean(monkeypatch) -> None:
    """[혼기 경향] 축 라벨 year·month·hour → 연주·월주·시주."""
    monkeypatch.setattr(sc, "active_marriage_aux", lambda *a, **k: {"mt6_age_prior": True})
    r, _ = _mr(1990, 5, 15, "10:30", "female")
    text = " ".join(sc.marriage_age_prior_lines(r))
    assert "연주" in text or "월주" in text or "시주" in text
    for en in ("year", "month", "day", "hour"):
        assert en not in text


def test_direction_instruction_forbids_unlisted_direction() -> None:
    assert "⑩" in SINSAL_DIRECTION_INSTRUCTION
    assert "블록에 없는 방향" in SINSAL_DIRECTION_INSTRUCTION


class _Sig:
    def __init__(self, key: str | None, w: float) -> None:
        self.event_key, self.weight = key, w


def test_lead_event_keys_distinct_top3_by_weight() -> None:
    sigs = [_Sig("a", 0.2), _Sig("b", 0.5), _Sig("a", 0.4), _Sig("c", 0.3), _Sig("d", 0.1)]
    assert _lead_event_keys(sigs, "연애") == "b·a·c"
    assert _lead_event_keys([_Sig(None, 0.3)], "연애") == "연애"
    assert _lead_event_keys(sigs, "연애", limit=1) == "b"


def test_unseeded_place_raises_typed_error() -> None:
    with pytest.raises(LocationResolveError):
        resolve("대구", None, None, None)


def test_chat_unseeded_place_returns_422_not_500() -> None:
    client = TestClient(app)
    res = client.post("/api/v2/chat", json={
        "birth": {"birth_date": "1996-02-03", "birth_time": "22:10",
                  "birth_place_name": "대구", "gender": "female"},
        "question": "올해 연애운", "dry_run": True,
    })
    assert res.status_code == 422, res.text
    assert "대구" in res.json()["detail"]


def test_findings_sorted_by_raw_sum_not_capped_score() -> None:
    """⑦ 정렬은 원합 — 포화(100) 동률이어도 원합 큰 시기가 앞, 동률은 period_key 순.

    2026-10-26 175명식 측정: 현행 점수 정렬은 M01 67.6%·M07 90.4% 행이 100 으로 포화해
    Top-3 절단이 이른 달 우선으로 퇴화(명식 100%). 표시 상한 100 은 유지한다.
    """
    from saju_engines.topic_builder import _sort_findings_by_raw
    from saju_shared_types.topic_context import Finding

    def f(pk: str) -> Finding:
        return Finding(key=f"x@{pk}", summary=pk, score=100, period_key=pk)

    pairs = [(1.2, f("2026-01")), (2.7, f("2026-05")), (1.2, f("2025-12")), (0.4, f("2026-03"))]
    assert [x.period_key for x in _sort_findings_by_raw(pairs)] == [
        "2026-05", "2025-12", "2026-01", "2026-03",
    ]
    # 반례: 점수(전부 100) 정렬이었다면 period_key 순으로 '2025-12' 가 1위였을 것.
    by_score = sorted((x for _, x in pairs), key=lambda x: (-x.score, x.period_key or ""))
    assert by_score[0].period_key == "2025-12"


def test_topic_future_floor_applied_before_truncation() -> None:
    """⑧ future_floor 를 PeriodSpec.start 로 올려 빌더 절단(findings[:5]) 앞에서 지난 달 제외.

    女 1990-05-15 10:30, 오늘 2026-10-26, 연애 질문: 종전엔 상위 5 가 올해 지난 달로 채워져
    후처리 뒤 참고 줄이 1개만 남았다. 교정 후 미래 줄 ≥2 · 월 키는 전부 floor 이상.
    """
    from saju_api.services import chat_service
    from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

    b = BirthInput(
        calendar_type="solar", birth_date=date(1990, 5, 15), birth_time="10:30",
        birth_place_name="서울", gender="female",
    )
    love = IntentJson(
        intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.RELATIONSHIP,
        constraints=Constraints(),
    )
    today = date(2026, 10, 26)
    lines = chat_service._topic_module_context(b, love, today, "2026-10")
    entries = [ln for ln in lines if ln.startswith("- ")]
    assert len(entries) >= 2, lines
    month_keys = [ln[2:9] for ln in entries if ln[6] == "-"]
    assert month_keys and all(k >= "2026-10" for k in month_keys)
    # 반례: floor 없이 같은 기간이면 지난 달(2026-01~09)이 상위 슬롯을 차지한다.
    raw_lines = chat_service._topic_module_context(b, love, today)
    no_floor = [ln for ln in raw_lines if ln.startswith("- ")]
    past = [ln for ln in no_floor if ln[6] == "-" and ln[2:9] < "2026-10"]
    assert past, no_floor


def test_in_period_same_year_range_keeps_month_keys() -> None:
    """⑨ end 가 연 단위('2027')여도 그 해의 월 키는 기간 안 — "내년" 범위에서 월 행 0개 결함."""
    from saju_engines.topic_builder import _in_period
    from saju_shared_types.topic_context import PeriodSpec

    same_year = PeriodSpec(start="2027", end="2027", granularity="year")
    assert _in_period("2027-03", same_year) and _in_period("2027", same_year)
    assert not _in_period("2026-12", same_year) and not _in_period("2028-01", same_year)
    # future_floor 월 정밀 start: 지난 달만 제외, 연 키·floor 이후 월 키는 유지.
    floored = PeriodSpec(start="2026-10", end="2031", granularity="year")
    assert _in_period("2026", floored) and _in_period("2026-12", floored)
    assert not _in_period("2026-09", floored)
    assert _in_period("2031-12", floored) and not _in_period("2032", floored)
