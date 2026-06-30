"""MT3 방합 배우자궁 게이트 '얇은 태깅' 테스트 (MARRIAGE_TIMING_ENHANCEMENT §8, A안).

핵심 검증: ① 방합이 일지(배우자궁) 포함 → MT3 태그(점수 무변경) ② 일지 미포함 → 미발동 ③ 점수
가산 0·event_key 불변(commitment 승급 없음) ④ partnerElement·충 분기 태그 ⑤ flag OFF 결과 불변.
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_directional_tag import apply_mt3_directional_tags
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2
from saju_shared_types.ganji_calendar import GanjiRef, RelationHit, RelationType

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _result(date: str = "1990-06-08", gender: str = "female"):  # 1990-06-08 = 甲(木) 일간
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date, birth_time="10:00",
        birth_place_name="서울", gender=gender,
    ))


def _dir_hit(element: str, *, day: bool = True) -> RelationHit:
    """방합 기여 hit — day=True면 일지(배우자궁)가 방합 구성에 참여."""
    pos = "day" if day else "month"
    return RelationHit(
        relation_id=f"rel_directional_{element}",
        type=RelationType.DIRECTIONAL_CONTRIB,
        luck_ref=GanjiRef(side="luck", position="year", branch="申"),
        natal_refs=[GanjiRef(side="natal", position=pos, branch="丑")],
        element=element,
    )


def _clash_day() -> RelationHit:
    return RelationHit(
        relation_id="rel_branch_clash_未_丑",
        type=RelationType.BRANCH_CLASH,
        luck_ref=GanjiRef(side="luck", position="year", branch="未"),
        natal_refs=[GanjiRef(side="natal", position="day", branch="丑")],
    )


def _cand(key: EventKeyV2, score: int = 40) -> EventCandidateV2:
    return EventCandidateV2(event_key=key, period="2026", score=score)


def test_directional_on_day_tags_without_score_change() -> None:
    """방합이 일지 포함 → MT3_DIRECTIONAL_DAY_BRANCH 태그, 점수·event_key 불변."""
    r = _result()
    cand = _cand(EventKeyV2.NEW_RELATIONSHIP, 40)
    out = apply_mt3_directional_tags([cand], [_dir_hit("水")], r, "female")
    assert "MT3_DIRECTIONAL_DAY_BRANCH" in out[0].reason_codes
    assert out[0].score == 40  # 점수 가산 0
    assert out[0].event_key is EventKeyV2.NEW_RELATIONSHIP  # 승급 없음


def test_directional_not_on_day_no_tag() -> None:
    """방합이 일지 미포함(월지만) → MT3 미발동."""
    r = _result()
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.NEW_RELATIONSHIP)], [_dir_hit("水", day=False)], r, "female",
    )
    assert not any(t.startswith("MT3") for t in out[0].reason_codes)


def test_partner_element_tag() -> None:
    """방합 결과 오행 = 배우자성(甲 여명 관살=金) → partnerElement 태그."""
    r = _result()  # 甲 일간 → 관살 = 金
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.NEW_RELATIONSHIP)], [_dir_hit("金")], r, "female",
    )
    assert "MT3_DIRECTIONAL_PARTNER_ELEMENT" in out[0].reason_codes


def test_non_partner_element_no_partner_tag() -> None:
    """방합 결과 오행이 배우자성이 아니면 partnerElement 태그 없음(기본 태그는 있음)."""
    r = _result()  # 甲 일간, 水는 인성(관살 아님)
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.NEW_RELATIONSHIP)], [_dir_hit("水")], r, "female",
    )
    assert "MT3_DIRECTIONAL_DAY_BRANCH" in out[0].reason_codes
    assert "MT3_DIRECTIONAL_PARTNER_ELEMENT" not in out[0].reason_codes


def test_clash_branch_tag() -> None:
    """방합 + 일지 충 동반 → MT3_DIRECTIONAL_CLASHED 분기 태그(점수 감점 아님)."""
    r = _result()
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.MARRIAGE_SIGNAL, 50)], [_dir_hit("水"), _clash_day()], r, "female",
    )
    assert "MT3_DIRECTIONAL_CLASHED" in out[0].reason_codes
    assert out[0].score == 50  # 분기 태그만, 감점 없음


def test_non_relationship_candidate_untouched() -> None:
    """관계 외 후보(career)는 태그를 받지 않는다."""
    r = _result()
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.CAREER_CHANGE)], [_dir_hit("金")], r, "female",
    )
    assert not any(t.startswith("MT3") for t in out[0].reason_codes)


def test_no_directional_unchanged() -> None:
    """방합 hit이 없으면 후보 불변."""
    r = _result()
    out = apply_mt3_directional_tags(
        [_cand(EventKeyV2.NEW_RELATIONSHIP, 40)], [_clash_day()], r, "female",
    )
    assert out[0].score == 40 and not any(t.startswith("MT3") for t in out[0].reason_codes)


# ── 엔진 통합 (feature flag) ─────────────────────────────────────────


def test_engine_flag_off_is_inert() -> None:
    """feature OFF(기본) — MT3 태그 없음·결과 불변(relation_palace 기존 보강은 그대로)."""
    r = _result("1985-03-15")  # 일지 丑 → 亥子丑 방합 가능
    years = list(range(2018, 2025))
    off = EventEngineV2(_DICTS).score_years(r, years)
    on = EventEngineV2(_DICTS, enable_mt3_directional=True).score_years(r, years)
    assert not any(any(t.startswith("MT3") for t in c.reason_codes) for c in off)
    assert len(on) == len(off)  # 태깅만 — 후보 개수 불변
    # 점수도 불변(MT3는 점수 무가산) — 정렬·개수 동일성으로 확인.
    assert [c.score for c in on] == [c.score for c in off]
    assert any(any(t.startswith("MT3") for t in c.reason_codes) for c in on)


def test_engine_flag_on_tags_directional_year() -> None:
    """feature ON — 일지 丑에 亥/子년이 와서 亥子丑 방합 → 관계 후보에 MT3 태그."""
    r = _result("1985-03-15")
    on = EventEngineV2(_DICTS, enable_mt3_directional=True).score_years(r, [2019])  # 己亥
    tagged = [c for c in on if "MT3_DIRECTIONAL_DAY_BRANCH" in c.reason_codes]
    assert tagged
    assert all(
        c.event_key in (
            EventKeyV2.NEW_RELATIONSHIP, EventKeyV2.MARRIAGE_SIGNAL,
            EventKeyV2.RELATIONSHIP_CHANGE,
        )
        for c in tagged
    )
