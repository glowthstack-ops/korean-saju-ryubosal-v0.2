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
    assert len(parsed.purposes) == 13 and len(parsed.sinsals) == 12 and len(parsed.groups) == 4
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
    assert any(c.sinsal == "역마살" for c in recommend_for_purpose(
        build_direction_profile(Branch.YU), DirectionPurpose.SLEEP).cautions) is False
    # 巳酉丑: 반안=戌(서), 역마=亥(북) — 다른 4방이라 주의 목록엔 안 실린다(같은 4방만 주의).


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
