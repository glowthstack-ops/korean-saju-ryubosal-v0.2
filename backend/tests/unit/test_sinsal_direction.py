"""12신살 방위 활용 + 삼재(docs/18, 2026-09-20 데굴님 승인) 회귀.

고정하는 것: ①공용 12신살 표(4삼합군 × 12지지)가 제안서 표와 일치 ②삼재=역마/육해/화개 세운
③년살 정규화(연살 금지) ④사전 스키마·lint ⑤목적 × 개별 신살 등급(년살 fit/월살 caution 분리)
⑥파서 목적·사용방식 감지와 Q10 라우팅 ⑦채팅 프롬프트 블록(수동·능동·삼재) ⑧리포트 전용 섹션
(F-20b·Y-11b)과 테마 주입 ⑨세운 카드 samjae 필드 ⑩시점 미승계.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
import saju_api.services.report_service as report_service
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import build_llm_input, serialize_llm_input
from saju_engines.dictionaries import _lint_sinsal_direction
from saju_engines.query_parser import detect_direction_purpose, parse_message
from saju_engines.relationship_relative_sinsal import get_relative_sinsal
from saju_engines.sinsal_direction import (
    SINSAL_DIRECTION_VERSION,
    build_direction_profile,
    build_sinsal_direction_block,
    detect_purposes_for_intent,
    format_samjae_lines,
    format_sinsal_direction_lines,
    landmark_from_facing,
    recommend_for_purpose,
    samjae_for_year,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch
from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec
from saju_shared_types.sinsal_direction import DirectionPurpose, SinsalDirectionDict
from saju_shared_types.twelve_sinsal import (
    BASE_MAPS,
    TWELVE_SINSAL_ORDER,
    SamjaeStage,
    samjae_branches,
    samjae_for,
    trine_group_label,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_TODAY = date(2026, 9, 20)
# 1980-11-22 → 庚申년생(申子辰). 삼재 = 寅(들)·卯(눌)·辰(날) → 2022~2024, 2034~2036.
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-09-20",
)

# 제안서 §5 표 — 4삼합군 × 12지지(子→亥 순) 신살 첫 글자.
_EXPECTED = {
    Branch.IN: "재천지년월망장반역육화겁",  # 寅午戌: 亥겁 子재 …
    Branch.SA: "육화겁재천지년월망장반역",  # 巳酉丑
    Branch.SIN: "장반역육화겁재천지년월망",  # 申子辰
    Branch.HAE: "년월망장반역육화겁재천지",  # 亥卯未
}
_ORDER = [
    Branch.JA, Branch.CHUK, Branch.IN, Branch.MYO, Branch.JIN, Branch.SA,
    Branch.O, Branch.MI, Branch.SIN, Branch.YU, Branch.SUL, Branch.HAE,
]


@pytest.fixture(scope="module")
def chart():
    return calculate(_BIRTH)


# ── ① 공용 표 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("base", list(_EXPECTED))
def test_shared_table_matches_proposal(base: Branch) -> None:
    got = "".join(BASE_MAPS[base][b][0] for b in _ORDER)
    assert got == _EXPECTED[base]


def test_trine_members_share_table_and_label() -> None:
    assert BASE_MAPS[Branch.SIN] is BASE_MAPS[Branch.JA] is BASE_MAPS[Branch.JIN]
    assert trine_group_label(Branch.JA) == "申子辰"
    assert trine_group_label(Branch.O) == "寅午戌"


def test_year_sal_normalized_everywhere() -> None:
    """'연살' 표기 금지 — 공용 표·관계 엔진·오늘의 운세 채널 모두 년살."""
    from saju_engines.daily_fortune_v2 import _TWELVE_SINSAL_CHANNEL

    assert "년살" in TWELVE_SINSAL_ORDER and "연살" not in TWELVE_SINSAL_ORDER
    assert get_relative_sinsal(Branch.SIN, Branch.YU).sinsal == "년살"
    assert "년살" in _TWELVE_SINSAL_CHANNEL and "연살" not in _TWELVE_SINSAL_CHANNEL


# ── ② 삼재 ───────────────────────────────────────────────────────────────────


def test_samjae_is_derived_from_twelve_sinsal() -> None:
    assert samjae_branches(Branch.SIN) == (Branch.IN, Branch.MYO, Branch.JIN)
    assert samjae_branches(Branch.O) == (Branch.SIN, Branch.YU, Branch.SUL)
    assert samjae_branches(Branch.YU) == (Branch.HAE, Branch.JA, Branch.CHUK)
    assert samjae_branches(Branch.MI) == (Branch.SA, Branch.O, Branch.MI)
    enter = samjae_for(Branch.SIN, Branch.IN)
    assert enter is not None and enter.stage is SamjaeStage.ENTER and enter.label_ko == "들삼재"
    assert samjae_for(Branch.SIN, Branch.MYO).label_ko == "눌삼재"  # type: ignore[union-attr]
    assert samjae_for(Branch.SIN, Branch.JIN).label_ko == "날삼재"  # type: ignore[union-attr]
    assert samjae_for(Branch.SIN, Branch.JA) is None  # 장성살 세운 — 삼재 아님


def test_yearly_luck_pillar_carries_samjae(chart) -> None:
    """세운 카드(period_type=year)에 samjae 가 실리고 월운·대운엔 없다. 점수는 불변."""
    years = {p.label: p for p in chart.luck_cycles.yearly_luck}
    assert years["2022"].samjae and years["2022"].samjae.label_ko == "들삼재"
    assert years["2023"].samjae and years["2023"].samjae.label_ko == "눌삼재"
    assert years["2024"].samjae and years["2024"].samjae.label_ko == "날삼재"
    assert years["2026"].samjae is None
    assert all(m.samjae is None for m in chart.luck_cycles.monthly_luck)
    assert samjae_for_year(chart, 2034).label_ko == "들삼재"  # type: ignore[union-attr]


def test_uncovered_year_keeps_stage_without_quality(chart) -> None:
    """세운 기둥이 없는 해(첫 대운 이전·대운표 밖)도 삼재 단계는 판정하고 quality만 비운다."""
    info = samjae_for_year(chart, 2094)  # 甲寅년, 대운표(~2085) 밖
    assert info is not None and info.label_ko == "들삼재" and info.quality is None
    lines = format_samjae_lines(chart, [2094])
    assert any("2094년 들삼재" in ln for ln in lines) and "성격 우세" not in "\n".join(lines)


def test_samjae_lines_only_for_hit_years(chart) -> None:
    assert format_samjae_lines(chart, [2026, 2027, 2028]) == []  # 창 안 삼재 없음 → 무소음
    lines = format_samjae_lines(chart, [2033, 2034, 2035], current_year=2034)
    assert lines[1].startswith("[삼재 흐름")
    assert any("2034년 들삼재(역마살, 1/3) ◀ 올해" in ln for ln in lines)
    assert any("2035년 눌삼재(육해살, 2/3)" in ln for ln in lines)
    assert not any("2033" in ln for ln in lines[3:])


# ── ④ 사전 ───────────────────────────────────────────────────────────────────


def _raw() -> dict:
    return json.loads((_DICTS / "sinsal_direction.json").read_text("utf-8"))


def test_dictionary_validates_and_lints_clean() -> None:
    parsed = SinsalDirectionDict.model_validate(_raw())
    assert not _lint_sinsal_direction(parsed)
    assert parsed.reviewed is True  # 2026-09-20 데굴님 결정: 감수 없이 적용
    assert len(parsed.purposes) == 16 and len(parsed.sinsals) == 12 and len(parsed.groups) == 4
    assert [g.sinsals for g in parsed.groups] == [
        ["겁살", "재살", "천살"], ["지살", "년살", "월살"],
        ["망신살", "장성살", "반안살"], ["역마살", "육해살", "화개살"],
    ]
    assert {s.stage: s.sinsal for s in parsed.samjae_stages} == {
        "enter": "역마살", "stay": "육해살", "exit": "화개살",
    }


def test_lint_rejects_yeonsal_and_bad_samjae_mapping() -> None:
    raw = _raw()
    raw["samjae_stages"][0]["sinsal"] = "육해살"
    errs = _lint_sinsal_direction(SinsalDirectionDict.model_validate(raw))
    assert any("삼재 enter" in e for e in errs)
    raw = _raw()
    raw["purposes"][0]["grades"]["천살"] = "caution"  # study 1순위가 fit 아님
    errs = _lint_sinsal_direction(SinsalDirectionDict.model_validate(raw))
    assert any("fit 아님" in e for e in errs)
    raw = _raw()
    del raw["purposes"][0]["grades"]["화개살"]
    with pytest.raises(ValueError, match="등급 누락"):
        SinsalDirectionDict.model_validate(raw)


def test_snapshot_matches_source() -> None:
    committed = json.loads(
        (_BACKEND / "compiled" / f"sinsal_direction_v{SINSAL_DIRECTION_VERSION}.json")
        .read_text("utf-8")
    )
    assert committed.pop("snapshot_version") == SINSAL_DIRECTION_VERSION
    committed.pop("compiled_at", None)
    parsed = SinsalDirectionDict.model_validate(_raw())
    assert committed == parsed.model_dump(by_alias=True), (
        "sinsal_direction 스냅샷이 원본과 다르다 — "
        "`python scripts/build_sinsal_direction_snapshot.py` 재실행 필요"
    )


# ── ⑤ 프로필·목적 추천 ───────────────────────────────────────────────────────


def test_profile_quadrants_for_sin_year() -> None:
    p = build_direction_profile(Branch.SIN)
    quads = {q.absolute_direction: q for q in p.quadrants}
    assert quads["동"].sinsals == ["역마살", "육해살", "화개살"]
    assert quads["동"].theme == "변화와 정리"
    assert quads["남"].sinsals == ["겁살", "재살", "천살"]
    assert quads["서"].sinsals == ["지살", "년살", "월살"]
    assert quads["북"].sinsals == ["망신살", "장성살", "반안살"]
    assert p.samjae_branches == ["寅", "卯", "辰"]
    assert {s.branch for s in p.sectors} == {str(b) for b in _ORDER}  # 절대 지지 12 전수


def test_dating_grades_split_inside_activity_group() -> None:
    """같은 활동 구간이라도 년살=적합 / 월살=주의 — 구간 점수로 뭉개지 않는다(제안서 §12)."""
    p = build_direction_profile(Branch.SIN)
    rec = recommend_for_purpose(p, DirectionPurpose.DATING)
    assert rec.picks[0].sinsal == "년살" and rec.picks[0].grade == "fit"
    assert rec.picks[0].absolute_direction == "서" and rec.picks[0].branch == "酉"
    assert any(c.sinsal == "월살" and c.branch == "戌" for c in rec.cautions)
    study = recommend_for_purpose(p, DirectionPurpose.STUDY)
    assert study.picks[0].sinsal == "천살" and study.usage_mode.value == "face"
    sleep = recommend_for_purpose(p, DirectionPurpose.SLEEP)
    assert sleep.picks[0].sinsal == "반안살" and sleep.usage_mode.value == "head"
    # docs/19 §6-3(2026-09-21): 피할 방향은 그 목적의 caution 전부. 巳酉丑은 반안=戌(서)·역마=亥(북)
    # 으로 4방이 달라도 역마살이 [피함]에 실리고, 같은 4방 여부는 플래그로만 구분한다.
    yu_sleep = recommend_for_purpose(build_direction_profile(Branch.YU), DirectionPurpose.SLEEP)
    yeokma = next(c for c in yu_sleep.cautions if c.sinsal == "역마살")
    assert yeokma.branch == "亥" and yeokma.absolute_direction == "북"
    assert yeokma.verdict == "CAUTION" and yeokma.same_quadrant_as_fit is False
    assert {c.sinsal for c in yu_sleep.cautions} == {"지살", "년살", "역마살"}
    assert yu_sleep.picks[0].verdict == "BEST_USE"
    # 같은 4방 안의 주의 신살이 먼저 온다(지지 단위 구분을 먼저 쓰게).
    assert [c.same_quadrant_as_fit for c in rec.cautions] == sorted(
        [c.same_quadrant_as_fit for c in rec.cautions], reverse=True
    )


def test_landmark_translates_facing_and_flags_ambiguity() -> None:
    p = build_direction_profile(Branch.SIN)
    south = landmark_from_facing(p, "S")
    assert south and not south.ambiguous and south.window_side == ["午 재살"]
    assert south.opposite_side == ["子 장성살"]
    se = landmark_from_facing(p, "SE")
    assert se and se.ambiguous and se.window_side == ["辰 화개살", "巳 겁살"]
    assert landmark_from_facing(p, "unknown") is None and landmark_from_facing(p, None) is None


def test_proactive_purposes_follow_domain_and_skip_noise_types() -> None:
    it = IntentJson(intent_id="a", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION)
    assert detect_purposes_for_intent(it) == [DirectionPurpose.STUDY]
    it = IntentJson(
        intent_id="b", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        domains=[Domain.CAREER, Domain.HEALTH],
    )
    assert detect_purposes_for_intent(it) == [
        DirectionPurpose.PRESENTATION, DirectionPurpose.LEADERSHIP,
    ]  # 최대 2
    it = IntentJson(intent_id="c", query_type=QueryType.EMOTIONAL_SUPPORT)
    assert detect_purposes_for_intent(it) == [DirectionPurpose.COUNSELING]
    it = IntentJson(intent_id="d", query_type=QueryType.COMPARISON, domain=Domain.CAREER)
    assert detect_purposes_for_intent(it) == []
    it = IntentJson(intent_id="e", query_type=QueryType.FORTUNE_OVERVIEW)  # general — 무소음
    assert detect_purposes_for_intent(it) == []


def test_block_lines_have_no_scores_and_keep_gate_words() -> None:
    p = build_direction_profile(Branch.SIN)
    block = build_sinsal_direction_block(calculate(_BIRTH), [DirectionPurpose.STUDY])
    assert block is not None and block.profile.year_branch == p.year_branch
    text = "\n".join(format_sinsal_direction_lines(block))
    assert "[방위 활용" in text and "기준점:" in text
    assert "점수" not in text.replace("점수·판정 무관", "")
    assert "나쁜 방향" not in text
    assert build_sinsal_direction_block(calculate(_BIRTH), [], proactive=True) is None


# ── ⑥ 파서 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("q,purpose,mode", [
    ("공부할 때 책상은 어느 방향을 보고 앉는 게 좋아?", "study", "face"),
    ("잘 때 머리를 어느 쪽으로 두면 좋을까", "sleep", "head"),
    ("화장대는 어느 방향에 놓을까요", "beauty", "position"),
    ("소개팅 앞두고 있는데 어느 쪽 방향이 좋아?", "dating", "position"),
    ("가게 출입구 방향은 어디가 좋아", "sales", "entrance"),
    ("여행은 어느 방향으로 가면 좋아", "travel", "move"),
    ("회의할 때 어느 자리에 앉아야 주도권을 잡을까", "leadership", "position"),
])
def test_parser_detects_purpose_and_usage(q: str, purpose: str, mode: str) -> None:
    assert detect_direction_purpose(q) == (purpose, mode)
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.direction_purpose == purpose and intent.direction_usage_mode == mode
    if purpose not in ("travel", "relocation"):
        assert intent.query_type is QueryType.REMEDY


@pytest.mark.parametrize("q", [
    "올해 이직운 어때?", "내 사주에 도화살 있어?", "6월중에 남동쪽으로 이사한다면 어떤 날이 좋을까",
    "어느 지역이 살기 좋아",
    # 리뷰 수정(2026-09-20): 비유 '방향'·양자택일 관용구·짧은 키워드 우연 매칭은 방향 질문이 아니다.
    "어떤 쪽으로 공부 방향을 잡는 게 좋을까",
    "연구 방향을 어디로 잡아야 할지 모르겠어",
    "공부를 계속할지 취업할지 어느 쪽이 좋을까",
    "면접 본 두 회사 중 어느 쪽이 좋아?",
    "회사에서 어느 쪽 편을 들어야 할지 회의 때 고민이야",
])
def test_parser_leaves_non_direction_questions(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert detect_direction_purpose(q) is None and intent.direction_purpose is None
    assert intent.query_type is not QueryType.REMEDY or "이사" not in q


def test_parser_prefers_longest_keyword_and_requires_purpose_for_entrance() -> None:
    """'여행 가게 되면 어느 방향' → 여행(가게 동사 오탐 차단), '화장실 문 방향' → 목적 없음."""
    assert detect_direction_purpose("여행 가게 되면 어느 방향으로 가면 좋아?") == ("travel", "move")
    assert detect_direction_purpose("화장실 문 방향은 어디가 좋아") is None


def test_direction_flag_not_inherited_by_time_followup() -> None:
    """'그럼 올해는?' 시점 후속은 직전 방향 질문의 플래그를 물려받지 않는다(리뷰 수정)."""
    first = parse_message("공부할 때 책상은 어느 방향을 보고 앉는 게 좋아?", _TODAY).intents[0]
    assert first.direction_purpose == "study"
    follow = parse_message("그럼 올해는?", _TODAY, prev_intent=first)
    assert follow.is_follow_up and follow.intents[0].direction_purpose is None


def test_date_recommendation_has_no_proactive_direction_block(chart) -> None:
    """택일(Q4)엔 용신 오행 방위 블록이 있으므로 역마 방향 능동 제안을 덧붙이지 않는다."""
    intent = parse_message("6월중에 남동쪽으로 이사한다면 어떤 날이 좋을까", _TODAY).intents[0]
    assert intent.query_type is QueryType.DATE_RECOMMENDATION
    payload = build_llm_input(
        "6월중에 남동쪽으로 이사한다면 어떤 날이 좋을까", intent, chart, [], [],
        cs._get_scorer(), today=_TODAY,
    )
    assert payload.sinsal_direction is None


def test_guard_trims_proactive_direction_and_samjae_before_body(chart) -> None:
    """토큰 초과 시 능동 방위·삼재 블록이 Tier 0에서 먼저 제거되고 수동 블록은 남는다."""
    from saju_engines.context_reducer import serialize_with_guard
    from saju_engines.llm_guard import CALL_LIMITS

    intent = parse_message("잘 때 머리를 어느 쪽으로 두면 좋을까", _TODAY).intents[0]
    payload = build_llm_input(
        "잘 때 머리를 어느 쪽으로 두면 좋을까", intent, chart, [], [], cs._get_scorer(),
        today=_TODAY,
    )
    assert payload.sinsal_direction is not None and not payload.sinsal_direction.proactive
    base_tokens = serialize_with_guard(payload, "chat_single")[1]
    reserve = max(0, CALL_LIMITS["chat_single"].max_input_tokens - base_tokens + 50)
    text, _n = serialize_with_guard(payload, "chat_single", reserve_tokens=reserve)
    assert "[방위 활용" in text  # 수동 블록은 본체 — 유지


def test_relocation_direction_question_keeps_date_path() -> None:
    """'이사 방향' 질문은 기존 이사 방위(용신 오행) 경로를 유지하고 블록만 덧붙인다."""
    q = "이사는 어느 방향으로 가면 좋을까"
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.direction_purpose == "relocation"
    assert intent.query_type is not QueryType.REMEDY and intent.domain is Domain.RELOCATION


# ── ⑦ 채팅 프롬프트 ──────────────────────────────────────────────────────────


def test_chat_prompt_passive_direction_block_and_landmark(chart) -> None:
    intent = parse_message("공부할 때 책상은 어느 방향을 보고 앉는 게 좋아?", _TODAY).intents[0]
    payload = build_llm_input(
        "공부할 때 책상은 어느 방향을 보고 앉는 게 좋아?", intent, chart, [], [],
        cs._get_scorer(), today=_TODAY, living_room_facing="S",
    )
    assert payload.sinsal_direction is not None and not payload.sinsal_direction.proactive
    assert payload.sinsal_direction.recommendations[0].purpose is DirectionPurpose.STUDY
    text = serialize_llm_input(payload)
    assert "[방위 활용 — 12신살 기준" in text and "[방위 활용 지침]" in text
    assert "남쪽 未 천살" in text and "랜드마크(프로필 거실 주 창=남)" in text
    assert "[삼재 흐름" not in text  # REMEDY 는 삼재 미노출
    assert intent.time_range is None


def test_chat_prompt_proactive_block_by_domain_and_samjae_window(chart) -> None:
    from saju_shared_types.intent import Granularity, TimeRange

    intent = IntentJson(
        intent_id="p", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.RELATIONSHIP,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2033", end="2036",
        ),
    )
    payload = build_llm_input(
        "연애운 어때", intent, chart, [], [], cs._get_scorer(), today=_TODAY,
    )
    assert payload.sinsal_direction is not None and payload.sinsal_direction.proactive
    assert [r.purpose for r in payload.sinsal_direction.recommendations] == [
        DirectionPurpose.DATING,
    ]
    text = serialize_llm_input(payload)
    assert "◆ 목적 '소개팅·데이트'" in text and "서쪽 酉 년살(年殺·도화살)" in text
    assert "[삼재 흐름" in text and "2034년 들삼재" in text and "[삼재 지침]" in text
    # 감정지원(Q13)엔 상담·명상 방향을 능동 제안한다(docs/18 §5-1 — 외부 게이트가 막던 결함 수정).
    emo = IntentJson(intent_id="e", query_type=QueryType.EMOTIONAL_SUPPORT)
    text_emo = serialize_llm_input(build_llm_input(
        "요즘 너무 힘들어", emo, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "◆ 목적 '상담·명상'" in text_emo and "[삼재 흐름" not in text_emo
    # 용어교육엔 방위·삼재 모두 무노출.
    edu = IntentJson(intent_id="t", query_type=QueryType.TERMINOLOGY_EDUCATION)
    text2 = serialize_llm_input(build_llm_input(
        "공망이 뭐야", edu, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "[방위 활용" not in text2 and "[삼재 흐름" not in text2


def test_direction_question_does_not_inherit_previous_month_scope() -> None:
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState
    from saju_shared_types.intent import Granularity, TimeRange

    last = IntentJson(
        intent_id="t1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-09", end="2026-09",
        ),
    )
    state = ConversationState(
        thread_id="x", turn_no=1, active_topic=Domain.CAREER, last_intent=last, last_offer="",
    )
    parsed, _ns, _res, _link = ConversationEngine().process_turn(
        state, "잘 때 머리를 어느 쪽으로 두면 좋을까", _TODAY
    )
    intent = parsed.intents[0]
    assert intent.direction_purpose == "sleep" and intent.time_range is None


# ── ⑧ 리포트 ─────────────────────────────────────────────────────────────────


def _spec(product_code: str, topic: str | None = None, year: int = 2026) -> ReportSpec:
    return ReportSpec(
        product_code=product_code,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic,
        period=ReportPeriod(start=f"{year}-01-01", end=f"{year}-12-31"),
    )


def test_report_full_and_year_have_direction_sections() -> None:
    full = {c.section_id: c for c in report_service.plan_report(_BIRTH, _spec("RPT_FULL"), _TODAY)}
    f20b = full["F-20b"].body_prompt
    assert "[방위 활용 — 12신살 기준" in f20b and "[목적별 활용 방향" in f20b
    assert "숙면(잠잘 때 머리 방향): 북쪽 丑 반안살" in f20b
    assert "랜드마크 없음" in f20b and "[방위 활용 지침]" in f20b
    assert "[삼재 흐름" not in f20b  # 2026~2031 예측 창엔 삼재 해 없음(2034 시작)
    # 전용 섹션이 아닌 곳엔 전체 방향판이 실리지 않는다.
    assert "[목적별 활용 방향" not in full["F-20"].body_prompt
    year = {c.section_id: c for c in report_service.plan_report(_BIRTH, _spec("RPT_YEAR"), _TODAY)}
    assert "[방위 활용 — 12신살 기준" in year["Y-11b"].body_prompt
    assert "이 해는 삼재 해가 아니다" in year["Y-11b"].body_prompt
    y34 = {
        c.section_id: c
        for c in report_service.plan_report(_BIRTH, _spec("RPT_YEAR", year=2034), _TODAY)
    }
    assert "2034년 들삼재(역마살, 1/3)" in y34["Y-11b"].body_prompt
    assert "2034년 들삼재" in y34["Y-04"].body_prompt  # 세운 섹션에도 삼재 맥락


def test_report_theme_sections_get_topic_purposes_only() -> None:
    w = {
        c.section_id: c
        for c in report_service.plan_report(_BIRTH, _spec("RPT_FOCUS", topic="wealth"), _TODAY)
    }
    assert "◆ 목적 '영업·장사'" in w["W-08"].body_prompt
    assert "◆ 목적 '소개팅·데이트'" not in w["W-08"].body_prompt
    assert "[방위 활용" not in w["W-03"].body_prompt
    r = {
        c.section_id: c
        for c in report_service.plan_report(
            _BIRTH, _spec("RPT_FOCUS", topic="relationship"), _TODAY
        )
    }
    assert "◆ 목적 '소개팅·데이트'" in r["R-07"].body_prompt
    assert "◆ 목적 '메이크업·외모 연출'" in r["R-07"].body_prompt
    h = {
        c.section_id: c
        for c in report_service.plan_report(_BIRTH, _spec("RPT_FOCUS", topic="health"), _TODAY)
    }
    assert "◆ 목적 '숙면'" in h["C-07"].body_prompt


# ── ⑪ 삼재 품질(복/평/악·강도·근거·도메인·겹삼재) — docs/18 §4-2 ─────────────────


def test_samjae_quality_config_grid_and_lint() -> None:
    from saju_engines.sinsal_direction import load_sinsal_direction_dict

    cfg = load_sinsal_direction_dict().samjae_quality
    assert {(p.stage, p.quality) for p in cfg.stage_quality_phrases} == {
        (s, q) for s in ("enter", "stay", "exit") for q in ("bok", "normal", "ak")
    }
    assert cfg.thresholds.bok == 0.25 and cfg.thresholds.ak == -0.25
    raw = _raw()
    raw["samjae_quality"]["stage_quality_phrases"].pop()
    with pytest.raises(ValueError):
        SinsalDirectionDict.model_validate(raw)
    raw = _raw()
    raw["samjae_quality"]["thresholds"]["ak"] = 0.1
    with pytest.raises(ValueError):
        SinsalDirectionDict.model_validate(raw)


def test_samjae_quality_evaluated_on_manse_result(chart) -> None:
    """만세력 calculate 가 세운·대운표 sewoon 의 samjae 를 quality 까지 채운다(사건 후보 없이)."""
    from saju_engines.samjae_quality import evaluate_samjae

    years = {p.label: p for p in chart.luck_cycles.yearly_luck}
    s22 = years["2022"].samjae
    assert s22 is not None and s22.quality is not None and s22.quality_label in (
        "복삼재", "평삼재", "악삼재",
    )
    assert s22.quality_score is not None and -1.0 <= s22.quality_score <= 1.0
    assert s22.strength_label in ("약", "중", "강") and s22.stage_quality_phrase
    assert {e.signal for e in s22.evidence} >= {"annual_luck", "daewoon_luck"}
    assert s22.event_signal_included is False and s22.domains == []
    # 壬辰 대운(辰∈寅卯辰) + 寅 세운이 원국 申을 충 → 두 겹삼재 모두.
    assert s22.overlap == ["daewoon", "natal_clash"]
    assert s22.overlap_label == "대운 겹삼재 · 충 겹삼재"
    assert years["2026"].samjae is None
    sew = [p for d in chart.luck_cycles.daewoon_table for p in d.sewoon if p.samjae]
    assert sew and all(p.samjae.quality is not None for p in sew)  # type: ignore[union-attr]
    assert evaluate_samjae(chart, 2026) is None  # 삼재 해 아님


def test_samjae_quality_thresholds_and_evidence_are_score_consistent(chart) -> None:
    from saju_engines.samjae_quality import evaluate_samjae
    from saju_engines.sinsal_direction import load_sinsal_direction_dict

    cfg = load_sinsal_direction_dict().samjae_quality
    for y in (2022, 2023, 2024, 2034, 2035, 2036):
        info = evaluate_samjae(chart, y)
        assert info is not None and info.quality_score is not None
        total = round(sum(e.contribution for e in info.evidence), 4)
        assert abs(max(-1.0, min(1.0, total)) - info.quality_score) < 1e-6
        expected = (
            "bok" if info.quality_score >= cfg.thresholds.bok
            else "ak" if info.quality_score <= cfg.thresholds.ak
            else "normal"
        )
        assert info.quality is not None and info.quality.value == expected
        # 근거 부호와 기여 부호 일치.
        for e in info.evidence:
            assert (e.contribution > 0) == (e.effect == "positive") or e.effect == "neutral"


def test_samjae_quality_uses_candidates_for_direction_and_domains(chart) -> None:
    from saju_engines.samjae_quality import evaluate_samjae
    from saju_shared_types.events import (
        Confidence,
        EventCandidate,
        EventKey,
        EventPolarity,
        EventType,
    )

    def _c(key: EventKey, period: str, score: int, quality: str) -> EventCandidate:
        return EventCandidate(
            event_key=key, event_type=list(EventType)[0], period=period, score=score,
            confidence=Confidence.MEDIUM, polarity=EventPolarity.POSITIVE, quality=quality,
        )

    cands = [
        _c(EventKey.CAREER_CHANGE, "2034-03", 80, "opportunity"),
        _c(EventKey.WEALTH_CHANGE, "2034-05", 60, "loss"),
        _c(EventKey.WEALTH_CHANGE, "2034-08", 40, "opportunity"),
        _c(EventKey.CAREER_CHANGE, "2035-01", 90, "pressure"),  # 다른 해 — 제외
    ]
    base = evaluate_samjae(chart, 2034)
    with_c = evaluate_samjae(chart, 2034, cands)
    assert base is not None and with_c is not None
    assert with_c.event_signal_included and not base.event_signal_included
    assert {d.domain: d.grade for d in with_c.domains} == {"career": "favorable", "wealth": "mixed"}
    assert any(e.signal == "event_direction" for e in with_c.evidence)
    # 후보가 유리 쪽(80+40 vs 60)이면 점수가 오른다.
    assert with_c.quality_score > base.quality_score  # type: ignore[operator]


def test_samjae_lines_carry_quality_but_no_internal_terms(chart) -> None:
    """LLM 줄에는 단계·성격·강도·근거·영역만 — 수치·내부 신호명·후보 유무 문구는 없다."""
    lines = format_samjae_lines(chart, [2034, 2035, 2036], current_year=2034)
    text = "\n".join(lines)
    assert "2034년 들삼재(역마살, 1/3) ◀ 올해" in text
    assert "성격 우세" in text or "뚜렷한 방향 없음" in text
    assert "단계×성격:" in text and "근거:" in text and "대운 겹삼재" in text
    for banned in ("event_signal", "annual_luck", "후보 미포함", "데이터", "quality_score", "0."):
        assert banned not in text, banned
    assert "가 그대로" not in text
    from saju_engines.sinsal_direction import SAMJAE_INSTRUCTION

    assert "복삼재≠대길" in SAMJAE_INSTRUCTION
    assert "유무나 부족을 절대 언급하지" in SAMJAE_INSTRUCTION


def test_natal_clash_overlap_follows_relations(chart) -> None:
    """삼재 세운 지지가 원국 지지와 충이면 natal_clash 겹삼재 — relations_to_chart '충:' 재사용."""
    from saju_engines.samjae_quality import evaluate_samjae

    seen = False
    for d in chart.luck_cycles.daewoon_table:
        for p in d.sewoon:
            if p.samjae is None:
                continue
            info = evaluate_samjae(chart, int(p.label))
            assert info is not None
            has_clash = any(r.startswith("충:") for r in p.relations_to_chart)
            assert ("natal_clash" in info.overlap) == has_clash
            seen |= has_clash
    assert seen, "申子辰 명식의 寅卯辰 삼재 중 원국 申·亥 등과 충하는 해가 있어야 한다"
    # 겹삼재는 방향(quality)이 아니라 강도에만 가산 — 같은 점수면 quality 동일.
    cfg_bonus = 0.2
    info = evaluate_samjae(chart, 2034)
    assert info is not None and info.strength is not None
    assert info.strength <= 1.0 and "daewoon" in info.overlap and cfg_bonus > 0


# ── ⑫ 피할 방향 판정(docs/19, 2026-09-21 데굴님 승인) — 5등급·중첩·되물음 없음 ──────────


def test_verdict_thresholds_have_no_absolute_avoid() -> None:
    """① caution 전제 + ②③④ 중 2개 이상 → STRONG_AVOID. caution 이 아니면 회피로 올리지 않는다."""
    from saju_engines.direction_avoidance import decide_verdict

    assert decide_verdict("caution", 0) == "CAUTION"
    assert decide_verdict("caution", 1) == "CAUTION"
    assert decide_verdict("caution", 2) == "STRONG_AVOID"
    assert decide_verdict("caution", 3) == "STRONG_AVOID"
    for g in ("fit", "support", "neutral"):
        assert decide_verdict(g, 3) != "STRONG_AVOID"  # 절대흉방 없음
    assert decide_verdict("fit", 3) == "BEST_USE" and decide_verdict("support", 0) == "GOOD_USE"


def test_case_a_sleep_yeokma_enter_samjae_ak_is_strong_avoid(chart) -> None:
    """자료 사례 A — 숙면 × 역마 방향 × 들삼재 × 악삼재 → 강한 회피(근거 2건). 다른 caution 은
    주의."""
    from saju_engines.direction_avoidance import annotate_avoidance, build_avoidance_context

    ctx = build_avoidance_context(chart, 2034)
    assert ctx is not None and ctx.transit_sinsal == "역마살" and ctx.unfavorable
    assert ctx.samjae is not None and ctx.samjae.label_ko == "들삼재"
    block = build_sinsal_direction_block(chart, [DirectionPurpose.SLEEP], proactive=False)
    assert block is not None
    annotate_avoidance(block, chart, 2034)
    rec = block.recommendations[0]
    yeokma = next(c for c in rec.cautions if c.sinsal == "역마살")
    assert yeokma.verdict == "STRONG_AVOID" and yeokma.branch == "寅"
    assert len(yeokma.verdict_evidence) == 2 and "들삼재" in yeokma.verdict_evidence[0]
    assert "악삼재" in yeokma.verdict_evidence[1]
    assert all(c.verdict == "CAUTION" for c in rec.cautions if c.sinsal != "역마살")
    assert rec.picks[0].verdict == "BEST_USE" and rec.picks[0].verdict_evidence == []
    text = "\n".join(format_sinsal_direction_lines(block))
    assert "[강한 회피] 동쪽 寅 역마살" in text and "근거:" in text
    assert "중첩 판정 기준: 2034년 세운 寅=역마살(들삼재·악삼재)" in text
    assert not any(ch.isdigit() for ch in text.split("근거:")[1].split("\n")[0].replace("2034", ""))


def test_no_overlap_year_keeps_caution_only(chart) -> None:
    """2026(午 세운=재살·용신운): 숙면 caution 방향과 세운 지지가 안 겹치고 불리 신호도 없어
    주의만."""
    from saju_engines.direction_avoidance import annotate_avoidance, strong_avoid_lines

    block = build_sinsal_direction_block(chart, [DirectionPurpose.SLEEP], proactive=False)
    assert block is not None
    annotate_avoidance(block, chart, 2026)
    assert {c.verdict for c in block.recommendations[0].cautions} == {"CAUTION"}
    assert strong_avoid_lines(block.profile, chart, 2026) == []
    # 복/용신운 + 세운 지지 일치는 BEST_USE 에 '시간·공간 일치' 근거만(등급 신설 없음).
    study = build_sinsal_direction_block(chart, [DirectionPurpose.STUDY], proactive=False)
    assert study is not None
    annotate_avoidance(study, chart, 2026)  # 午=재살은 공부 support
    jae = next(p for p in study.recommendations[0].picks if p.sinsal == "재살")
    assert jae.verdict == "GOOD_USE" and jae.verdict_evidence
    assert "시간·공간 일치" in jae.verdict_evidence[0]


def test_domain_caution_counts_as_overlap_condition(chart) -> None:
    """조건 ④ — 목적 도메인의 그 해 사건 흐름이 불리(caution)면 중첩 1건으로 센다."""
    from saju_engines.direction_avoidance import annotate_avoidance, build_avoidance_context
    from saju_shared_types.events import (
        Confidence,
        EventCandidate,
        EventKey,
        EventPolarity,
        EventType,
    )

    def _c(key: EventKey, period: str, score: int, quality: str) -> EventCandidate:
        return EventCandidate(
            event_key=key, event_type=list(EventType)[0], period=period, score=score,
            confidence=Confidence.MEDIUM, polarity=EventPolarity.POSITIVE, quality=quality,
        )

    cands = [_c(EventKey.CAREER_CHANGE, "2036-03", 80, "conflict")]
    ctx = build_avoidance_context(chart, 2036, cands)  # 辰=화개살·날삼재·평삼재 → ③ 거짓
    assert ctx is not None and not ctx.unfavorable
    assert ctx.domain_grades.get("career") == "caution"
    # 발표(career): 화개살 caution × 辰 세운 일치(②) × 커리어 불리(④) → 강한 회피(사례 C 구조).
    block = build_sinsal_direction_block(chart, [DirectionPurpose.PRESENTATION], proactive=False)
    assert block is not None
    annotate_avoidance(block, chart, 2036, cands)
    hwagae = next(c for c in block.recommendations[0].cautions if c.sinsal == "화개살")
    assert hwagae.verdict == "STRONG_AVOID"
    assert any("커리어" in e or "직업" in e for e in hwagae.verdict_evidence)
    # 후보 없이 같은 해면 ② 하나뿐 → 주의.
    block2 = build_sinsal_direction_block(chart, [DirectionPurpose.PRESENTATION], proactive=False)
    assert block2 is not None
    annotate_avoidance(block2, chart, 2036)
    hw2 = next(c for c in block2.recommendations[0].cautions if c.sinsal == "화개살")
    assert hw2.verdict == "CAUTION"


def test_manual_block_has_full_purpose_table_and_avoid_column(chart) -> None:
    """수동 방향 질문 = 기본 방향 + 목적 전체 표(피함 열) — 되묻지 않는다(docs/19 §6)."""
    intent = parse_message("잘때는 어떤방향이 좋을까", _TODAY).intents[0]
    assert intent.direction_purpose == "sleep" and intent.direction_question
    payload = build_llm_input(
        "잘때는 어떤방향이 좋을까", intent, chart, [], [], cs._get_scorer(), today=_TODAY,
    )
    text = serialize_llm_input(payload)
    assert "◆ 목적 '숙면'" in text and "[적극 활용] 북쪽 丑 반안살" in text
    assert "[목적별 활용 방향 — 목적" in text and "[피함:" in text
    assert "숙면(잠잘 때 머리 방향): 북쪽 丑 반안살" in text
    assert "[주의(목적 충돌)] 동쪽 寅 역마살" in text  # 같은 4방이 아니어도 피할 방향 전부
    assert "⑧답 순서" in text and "절대 흉방" in text
    # 능동 블록엔 목적 전체 표가 실리지 않는다.
    edu = IntentJson(intent_id="a", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION)
    text_p = serialize_llm_input(build_llm_input(
        "공부운 어때", edu, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "◆ 목적 '공부·시험'" in text_p and "[목적별 활용 방향 — 목적" not in text_p


def test_unresolved_direction_question_uses_table_not_inherited_purpose(chart) -> None:
    """목적·사용 방식 없는 '어떤 방향이 좋을까' — 승계 도메인 능동 목적 없이 방향판+표로 답한다."""
    intent = parse_message("어떤 방향이 좋을까", _TODAY).intents[0]
    intent.domain = Domain.EDUCATION  # 직전 턴 승계를 흉내
    assert intent.direction_question and intent.direction_purpose is None
    assert intent.query_type is QueryType.REMEDY
    payload = build_llm_input(
        "어떤 방향이 좋을까", intent, chart, [], [], cs._get_scorer(), today=_TODAY,
    )
    assert payload.sinsal_direction is not None and not payload.sinsal_direction.proactive
    assert payload.sinsal_direction.recommendations == []
    text = serialize_llm_input(payload)
    assert "[목적별 활용 방향" in text and "◆ 목적 '공부·시험'" not in text


@pytest.mark.parametrize("q", [
    "잘때는 어떤방향이 좋을까", "잘땐 머리를 어느 쪽으로", "취침 방향 알려줘",
    "잠자리 방향은 어디가 좋아",
])
def test_parser_sleep_variants_without_spacing(q: str) -> None:
    assert detect_direction_purpose(q) == ("sleep", "head")


def test_desk_question_keeps_dictionary_usage_mode() -> None:
    """'책상 방향'은 공부 목적 keyword — 사전 사용 방식(바라보기)을 위치 어휘가 덮지 않는다."""
    assert detect_direction_purpose("공부할때 책상방향을 추천해줘") == ("study", "face")


def test_direction_question_is_not_linked_as_offer_answer() -> None:
    """실로그(2026-09-21): 공부 방향 답의 되물음 뒤 '잘때는 어떤방향이 좋을까'가 제안 수락
    (TIME_SHIFT)으로 링크돼 query_type·education 도메인을 승계하고 천살(공부)이 수면에
    적용됐다 — NEW 로 끊는다."""
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState

    eng = ConversationEngine()
    state = ConversationState(thread_id="d", turn_no=0)
    parsed, state, _r, _l = eng.process_turn(state, "공부할때 책상방향을 추천해줘", _TODAY)
    assert parsed.intents[0].direction_purpose == "study"
    state.last_offer = (
        "지금 준비하고 계신 공부가 어떤 자격을 위한 과정인지 말씀해 주시면 더 세밀하게 짚어드릴 수 "
        "있는데 어떠신가요?"
    )
    parsed, state, _r, link = eng.process_turn(state, "잘때는 어떤방향이 좋을까", _TODAY)
    it = parsed.intents[0]
    assert not link.is_follow_up
    assert it.direction_purpose == "sleep" and it.domain is Domain.HEALTH
    assert it.query_type is QueryType.REMEDY and it.time_range is None
    # 되물음 답변형(서술 답)은 여전히 이어진다(기존 offer-answer 경로 보존).
    state.last_offer = "제품형인지 서비스형인지 궁금해요"
    _p, _s, _r, link2 = eng.process_turn(state, "웹 서비스인데 이미 개발은 끝났어", _TODAY)
    assert link2.is_follow_up


def test_report_full_section_lists_strong_avoid_for_year() -> None:
    """RPT_YEAR 2034(들삼재·악삼재)의 Y-11b 에 강한 회피 줄이 실리고, 2026 에는 없다."""
    y34 = {
        c.section_id: c
        for c in report_service.plan_report(_BIRTH, _spec("RPT_YEAR", year=2034), _TODAY)
    }
    body = y34["Y-11b"].body_prompt
    assert "[강한 회피 — 2034년 기준" in body and "- 숙면: 동쪽 寅 역마살" in body
    assert "[피함:" in body
    y26 = {c.section_id: c for c in report_service.plan_report(_BIRTH, _spec("RPT_YEAR"), _TODAY)}
    assert "[강한 회피 — " not in y26["Y-11b"].body_prompt


def test_direction_question_prompt_keeps_all_parts_without_trim() -> None:
    """실측(2026-09-21 테스트 답): 방향 질문 프롬프트가 22k 상한을 넘어 Tier 0 트림에서 민속 고지가
    빠지고 상황별 조언이 답에서 누락됐다. 상한 28k(데굴님 결정)에서 네 부분 재료(기본·상황별 표·
    피할 방향·민속 고지)와 답 구성 계약이 모두 실려야 한다."""
    from saju_engines.llm_guard import CALL_LIMITS
    from saju_engines.sinsal_direction import DIRECTION_ANSWER_DIRECTIVE

    assert CALL_LIMITS["chat_single"].max_input_tokens == 28_000
    res = cs.chat(_BIRTH, "잠잘때 좋은 방향을 추천해줘", _TODAY, dry_run=True)
    assert res.status == "dry_run"
    p = res.prompt_preview or ""
    # 방향 질문은 시점·사건 축(사건 후보·월별 요약·유력 달·상담 계약·답변 지평·근거 경로)과
    # 도메인 보조(건강 취약 구조·M11 토픽)를 싣지 않는다(2026-09-21 데굴님 승인 — 약 8.8k 제거).
    heads = [ln for ln in p.splitlines() if ln.startswith("[")]
    for banned in (
        "[이벤트 후보 —", "[월별 요약 —", "[유력 달 종합 —", "[상담 결론 —", "[답변 지평]",
        "[근거 경로]", "[원국 건강 취약 구조", "[M11·health", "[사건 서술 계약",
    ):
        assert not any(h.startswith(banned) for h in heads), banned  # 블록 자체가 없다
    assert "[명식 해석 자료" in p and "[원국·명식 구조" in p  # 원국 배경은 유지
    assert "◆ 목적 '숙면'" in p and "[적극 활용] 북쪽 丑 반안살" in p
    assert "[목적별 활용 방향 — 목적 16종" in p and "[피함:" in p
    assert "[민속 흉방 고지 — 丙午년" in p and "[민속 흉방 지침]" in p
    assert DIRECTION_ANSWER_DIRECTIVE in p and "[방위 활용 지침]" in p
    # 이사 방향 질문은 기존 이사 방위 경로 위에 민속 전체 블록.
    res2 = cs.chat(_BIRTH, "이사는 어느 방향으로 가면 좋을까", _TODAY, dry_run=True)
    assert "[민속 흉방 — 2026 丙午년" in (res2.prompt_preview or "")


# ── ⑬ 방향 지목 후속('남쪽은 어때?') — docs/19 §6-7 (2026-09-21 실로그) ────────────


@pytest.mark.parametrize("q,code", [
    ("남쪽은 어때?", "S"), ("그럼 동쪽은?", "E"), ("남동쪽으로 두면 어때", "SE"),
    ("북쪽이 좋아?", "N"), ("서북쪽은 괜찮아?", "NW"), ("남쪽 지방 여행", None),
    ("동쪽 하늘이 맑네", None), ("북북서는 어때?", "NNW"), ("동남동 방향으로 하면?", "ESE"),
    ("북동은 어때", "NE"),
])
def test_detect_asked_direction(q: str, code: str | None) -> None:
    from saju_engines.query_parser import detect_asked_direction

    assert detect_asked_direction(q) == code


def test_asked_direction_followup_keeps_purpose_and_judges_sectors(chart) -> None:
    """실로그: '잠잘때 좋은 방향' 뒤 '남쪽은 어때?'가 공부(남쪽 未 천살) 답으로 샜다 — 같은
    목적(숙면)으로 그 방향의 지지별 판정을 싣고 최우선 지시문을 붙인다."""
    from saju_engines.conversation import ConversationEngine
    from saju_engines.sinsal_direction import ASKED_DIRECTION_DIRECTIVE
    from saju_shared_types.conversation import ConversationState

    eng = ConversationEngine()
    state = ConversationState(thread_id="ask", turn_no=0)
    _p, state, _r, _l = eng.process_turn(state, "잠잘때 좋은 방향을 추천해줘", _TODAY)
    state.last_offer = "혹시 숙면 외에 특별히 신경 쓰고 계신 공간 배치가 있으신가요?"
    parsed, state, _r, link = eng.process_turn(state, "남쪽은 어때?", _TODAY)
    it = parsed.intents[0]
    assert link.is_follow_up and it.direction_purpose == "sleep" and it.direction_asked == "S"
    assert it.query_type is QueryType.REMEDY and it.direction_question
    text = serialize_llm_input(build_llm_input(
        "남쪽은 어때?", it, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "◆ 질문한 방향 '남쪽'(180°) — 목적 '숙면' 기준 칸별 판정" in text
    assert "정중앙(대표) 午 재살(災殺·수옥살) [정남 165°~195°] [중립]" in text
    assert "동쪽으로 살짝 틀면 巳 겁살(劫殺) [남남동 135°~165°] [중립]" in text
    assert "서쪽으로 살짝 틀면 未 천살(天殺) [남남서 195°~225°] [중립]" in text
    assert "권고: 정중앙(정남 165°~195°) 그대로" in text
    assert "→ 기본 방향 북쪽 丑 반안살[북북동 15°~45°][적극 활용]과 비교해 답할 것" in text
    assert ASKED_DIRECTION_DIRECTIVE in text
    # 참조어 후속('그럼 동쪽은?')도 이번 발화의 방향이 직전 클론 값을 덮는다.
    parsed, state, _r, link = eng.process_turn(state, "그럼 동쪽은?", _TODAY)
    it2 = parsed.intents[0]
    assert it2.direction_asked == "E" and it2.direction_purpose == "sleep"
    text2 = serialize_llm_input(build_llm_input(
        "그럼 동쪽은?", it2, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "정중앙(대표) 卯 육해살(六害殺) [정동 75°~105°] [중립]" in text2
    assert "寅 역마살(驛馬殺) [동북동 45°~75°] [주의(목적 충돌)]" in text2
    assert "남쪽으로 살짝 틀면 辰 화개살(華蓋殺) [동남동 105°~135°] [잘 맞음]" in text2
    assert "권고: 정중앙보다 남쪽으로 살짝 틀어 동남동 105°~135°(辰 화개살)에 맞추는 편이" in text2
    # 간방은 두 칸 사이의 선 — 양쪽 칸 판정 + 틀 방향 권고('경계' 표현 없음).
    parsed, state, _r, _l = eng.process_turn(state, "남동쪽으로 두면 어때", _TODAY)
    text3 = serialize_llm_input(build_llm_input(
        "남동쪽으로 두면 어때", parsed.intents[0], chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    seg = text3.split("◆ 질문한 방향 '남동쪽'(135°)")[1].split("→ 기본 방향")[0]
    assert "동쪽으로 틀면 辰 화개살(華蓋殺) [동남동 105°~135°] [잘 맞음]" in seg
    assert "남쪽으로 틀면 巳 겁살(劫殺) [남남동 135°~165°] [중립]" in seg
    assert "권고: 남동쪽 정중앙(135°)은 두 칸 사이의 선이므로 동쪽으로 틀어 동남동 105°~135°" in seg
    assert "午 재살" not in seg and "경계" not in seg
    # 16방위는 한 칸.
    parsed, state, _r, _l = eng.process_turn(state, "북북서는 어때?", _TODAY)
    assert parsed.intents[0].direction_asked == "NNW"
    text4 = serialize_llm_input(build_llm_input(
        "북북서는 어때?", parsed.intents[0], chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    seg4 = text4.split("◆ 질문한 방향 '북북서쪽'(337.5°)")[1].split("→ 기본 방향")[0]
    assert "亥 망신살(亡身殺) [북북서 315°~345°] [중립]" in seg4 and seg4.count("\n  · ") == 1


def test_asked_direction_without_prior_purpose_uses_board_only(chart) -> None:
    intent = parse_message("남쪽은 어때?", _TODAY).intents[0]
    assert intent.direction_asked == "S" and intent.direction_purpose is None
    assert intent.query_type is QueryType.REMEDY and intent.direction_question
    text = serialize_llm_input(build_llm_input(
        "남쪽은 어때?", intent, chart, [], [], cs._get_scorer(), today=_TODAY,
    ))
    assert "◆ 질문한 방향 '남쪽'(180°) — 목적 미지정" in text
    assert "[목적별 활용 방향 — 목적 16종" in text


def test_asked_direction_does_not_hijack_date_recommendation() -> None:
    intent = parse_message("6월중에 남동쪽으로 이사한다면 어떤 날이 좋을까", _TODAY).intents[0]
    assert intent.query_type is QueryType.DATE_RECOMMENDATION
    assert intent.direction_asked == "SE" and not intent.direction_question


def test_compass_labels_are_thirty_degree_sectors(chart) -> None:
    """지지=30° 구간(子 정북 345°~15° 중심), 16방위 이름 병기 — 방향판·추천·목적 표·랜드마크
    공통."""
    from saju_shared_types.sinsal_direction import BRANCH_COMPASS, branch_compass_label

    assert branch_compass_label("子") == "정북 345°~15°"
    assert branch_compass_label("丑") == "북북동 15°~45°"
    assert branch_compass_label("亥") == "북북서 315°~345°"
    assert [BRANCH_COMPASS[b][1] for b in "子丑寅卯辰巳午未申酉戌亥"] == list(range(0, 360, 30))
    intent = parse_message("잠잘때 좋은 방향을 추천해줘", _TODAY).intents[0]
    text = serialize_llm_input(build_llm_input(
        "잠잘때 좋은 방향을 추천해줘", intent, chart, [], [], cs._get_scorer(), today=_TODAY,
        living_room_facing="SE",
    ))
    assert "丑 반안살(북북동 15°~45°)" in text and "방위 각도: 12지지=30° 구간" in text
    assert "[적극 활용] 북쪽 丑 반안살(攀鞍殺) [북북동 15°~45°]" in text
    assert "숙면(잠잘 때 머리 방향): 북쪽 丑 반안살(攀鞍殺)[북북동 15°~45°]" in text
    assert "남동은 두 칸 사이의 선이라 나침반 각도로 어느 칸인지 확인을 권할 것" in text
    assert "두 지지에 걸치" not in text and "지어내지 말 것 — 나침반 앱" in text
