"""횡재 택일 등급·사유·횡재 관점 라벨·표 인용 감사(2026-11-16 데굴님 승인).

실답(web-mwj26i50): '이번주중 로또사기 좋은 날'에 乙未일(천간 편관·기신, 지지 비견)을 "비견의
기운이 들어와 힘을 실어주는 날"이라며 가장 추천했다. 원인 세 겹 —
  ① 재물 신호 0건인 날이 중립 50점으로 [추천] 문턱(70)을 넘었다.
  ② 표 사유가 신호 유무와 무관하게 '재물 신호 기반'이었다.
  ③ 일별 흐름 줄 '기신 · 십성 편관/비견'에서 LLM이 지지 십성만 골랐다.

각 테스트는 반례(종전 규칙이면 통과했을 입력)를 함께 둔다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import (
    _DATE_TABLE_GRADE_INSTRUCTION,
    _DATE_TABLE_INSTRUCTION,
    _DATE_TABLE_NO_RECOMMEND_INSTRUCTION,
)
from saju_engines.date_selection import (
    GRADE_BASIS_NOTE,
    GRADE_STEM_NOTE,
    DateSelectionEngine,
    hit_label_ko,
    relation_label_ko,
)
from saju_engines.date_table_audit import audit_date_table_answer
from saju_engines.precompute import CompositeBuilder
from saju_engines.windfall_lens import (
    BODY_NEUTRAL,
    BODY_STRONG,
    BODY_WEAK,
    body_side,
    windfall_day_lens,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.llm_input import DateChoiceRow, DateSelectionBlock
from saju_shared_types.precompute import (
    CompositeLevel,
    DomainSignal,
    InteractionHit,
    InteractionKind,
    InteractionParticipant,
    InteractionSource,
    LuckComposite,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def engine() -> DateSelectionEngine:
    return DateSelectionEngine(_DICTS)


@pytest.fixture(scope="module")
def base_composites() -> list[LuckComposite]:
    """기준 차트(1980) 2026-06 합성 — 아래에서 신호·역할만 바꿔 쓴다."""
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    return CompositeBuilder(_DICTS).build(chart, "본인", "1.0.0", "2026-06-11T00:00:00+00:00")


def _wealth(weight: float, rel: str = "rel_巳申破") -> DomainSignal:
    return DomainSignal(
        domain="wealth", event_key="wealth_change", weight=weight, source_interaction=rel,
    )


def _clash(rel: str, a: str, b: str) -> InteractionHit:
    return InteractionHit(
        relation_id=rel, kind=InteractionKind.BRANCH_CLASH,
        participants=[
            InteractionParticipant(source=InteractionSource.NATAL_DAY, ganji=a),
            InteractionParticipant(source=InteractionSource.DAY, ganji=b),
        ],
    )


def _crafted(base: list[LuckComposite]) -> list[LuckComposite]:
    """월운을 강한 재물 유리(→ 최종 70 이상)로 두고 네 날의 신호·역할만 다르게 만든다.

    06-02: 용신·재물 신호 + · 걸림 없음   → 추천
    06-03: 용신·재물 신호 0건 · 걸림 없음 → 종전 추천(중립 50), 이제 무난  ← 반례
    06-04: 기신·재물 신호(불리)           → 무난
    06-05: 용신·재물 신호 + · 충 3건      → 회피(위험도)
    """
    spec = {
        "2026-06-02": ("용신", [_wealth(0.6)], []),
        "2026-06-03": ("용신", [], []),
        "2026-06-04": ("기신", [_wealth(0.6)], []),
        "2026-06-05": ("용신", [_wealth(0.6)], [
            _clash("rel_巳亥沖", "巳", "亥"), _clash("rel_巳亥沖", "巳", "亥"),
            _clash("rel_子午沖", "子", "午"),
        ]),
    }
    out: list[LuckComposite] = []
    for c in base:
        if c.level is CompositeLevel.MONTH and c.period_key == "2026-06":
            out.append(c.model_copy(update={
                "favorability": "용신", "domain_signals": [_wealth(1.0)],
            }))
        elif c.level is CompositeLevel.YEAR:
            out.append(c.model_copy(update={"domain_signals": []}))
        elif c.level is CompositeLevel.DAY and c.period_key in spec:
            fav, signals, hits = spec[c.period_key]
            out.append(c.model_copy(update={
                "favorability": fav, "domain_signals": signals, "interactions": hits,
            }))
        elif c.level is not CompositeLevel.DAY:
            out.append(c)
    return out


# ── B. 등급 규칙 ─────────────────────────────────────────────────


def test_windfall_recommend_requires_positive_day_signal(engine, base_composites) -> None:
    result = engine.select(
        EventKey.WINDFALL, _crafted(base_composites), "2026-06-02", "2026-06-05", top_n=8,
    )
    by_date = {c.date: c for c in result.candidates}
    assert by_date["2026-06-02"].recommendation == "recommended"
    # 반례: 신호 0건인 날 — 점수는 추천 문턱을 넘지만(종전 규칙이면 추천) 근거가 없어 무난.
    no_signal = by_date["2026-06-03"]
    assert no_signal.scores.final >= 70 and no_signal.risk_score < 40
    assert no_signal.day_signal == "none"
    assert no_signal.recommendation == "acceptable"
    assert by_date["2026-06-04"].day_signal == "negative"
    assert by_date["2026-06-04"].recommendation == "acceptable"
    assert by_date["2026-06-05"].recommendation == "avoid"
    # [추천] 날이 표 머리에 온다.
    assert result.candidates[0].date == "2026-06-02"


def _with_domain(comps: list[LuckComposite], domain: str, event_key: str) -> list[LuckComposite]:
    """재물 신호로 만든 합성본의 신호 도메인만 바꾼다(월운·일운 모두)."""
    return [
        c.model_copy(update={"domain_signals": [
            s.model_copy(update={"domain": domain, "event_key": event_key})
            for s in c.domain_signals
        ]})
        for c in comps
    ]


def test_grade_note_follows_purpose_options(engine) -> None:
    """근거 요구 = 횡재·재물·개업·결혼, 기신·구신 천간 차단만 = 이사·계약·수술(2026-11-16 확대)."""
    for purpose, domain in (
        (EventKey.WINDFALL, "재물"), (EventKey.WEALTH_CHANGE, "재물"),
        (EventKey.BUSINESS_START, "직업"), (EventKey.MARRIAGE_SIGNAL, "관계"),
    ):
        note = engine.grade_basis_note(purpose)
        assert note == GRADE_BASIS_NOTE.format(domain=domain), purpose
    for purpose in (
        EventKey.RELOCATION, EventKey.CONTRACT_DOCUMENT, EventKey.HEALTH_ATTENTION,
    ):
        assert engine.grade_basis_note(purpose) == GRADE_STEM_NOTE, purpose
    # 목적 별칭(취업 서류 제출 = 계약·문서 프로필 + 직업 도메인)도 프로필의 등급 옵션을 따른다.
    assert engine.grade_basis_note(EventKey.CONTRACT_DOCUMENT, "career") == GRADE_STEM_NOTE


def test_business_and_marriage_require_positive_day_signal(engine, base_composites) -> None:
    for purpose, domain, key in (
        (EventKey.BUSINESS_START, "career", "business_start"),
        (EventKey.MARRIAGE_SIGNAL, "relationship", "marriage_signal"),
    ):
        comps = _with_domain(_crafted(base_composites), domain, key)
        result = engine.select(purpose, comps, "2026-06-02", "2026-06-04", top_n=8)
        by_date = {c.date: c for c in result.candidates}
        assert by_date["2026-06-02"].recommendation == "recommended", purpose
        # 반례: 신호 0건(점수는 문턱 통과)·기신 천간 날은 종전 규칙이면 추천이었다.
        assert by_date["2026-06-03"].scores.final >= 70
        assert by_date["2026-06-03"].recommendation == "acceptable", purpose
        assert by_date["2026-06-04"].recommendation == "acceptable", purpose


def test_surgery_blocks_unfavorable_stem_but_keeps_calm_day(engine, base_composites) -> None:
    """수술은 걸리는 관계가 없는 것이 그날 근거다 — 신호 0건인 날은 [추천]으로 남고, 천간이
    기신·구신인 날만 빠진다."""
    # 수술 프로필은 일운 비중이 0.5라 신호 0건인 날이 문턱을 넘으려면 연·월이 모두 유리해야 한다.
    comps = []
    for c in _with_domain(_crafted(base_composites), "health", "health_attention"):
        if c.level is CompositeLevel.DAY and c.period_key == "2026-06-04":
            c = c.model_copy(update={"favorability": "기신", "domain_signals": []})
        elif c.level is CompositeLevel.YEAR and c.period_key == "2026":
            c = c.model_copy(update={"favorability": "용신", "domain_signals": [
                DomainSignal(domain="health", event_key="health_attention", weight=1.0,
                             source_interaction="rel_巳申破"),
            ]})
        comps.append(c)
    result = engine.select(EventKey.HEALTH_ATTENTION, comps, "2026-06-03", "2026-06-04", top_n=8)
    by_date = {c.date: c for c in result.candidates}
    calm = by_date["2026-06-03"]
    assert calm.day_signal == "none" and calm.recommendation == "recommended"
    # 반례: 같은 점수 조건(신호 0건·문턱 통과)인데 천간만 기신이다.
    unfavorable = by_date["2026-06-04"]
    assert unfavorable.scores.final >= 70 and unfavorable.risk_score < 40
    assert unfavorable.recommendation == "acceptable"
    assert unfavorable.reasons[0].startswith("천간 ") and "(기신)" in unfavorable.reasons[0]


# ── A. 표 사유 ───────────────────────────────────────────────────


def test_reason_states_signal_presence_not_generic_label(engine, base_composites) -> None:
    result = engine.select(
        EventKey.WINDFALL, _crafted(base_composites), "2026-06-02", "2026-06-05",
        top_n=8, body=BODY_WEAK,
    )
    by_date = {c.date: c for c in result.candidates}
    assert not any("신호 기반" in r for c in result.candidates for r in c.reasons)
    pos = by_date["2026-06-02"].reasons
    assert pos[0].startswith("천간 ") and "(용신)" in pos[0] and "지지 " in pos[0]
    assert "재물 신호 있음(유리 방향: 巳申 파)" in pos
    assert "걸리는 관계(충·형·원진) 없음" in pos
    assert "재물 신호 없음" in by_date["2026-06-03"].reasons
    assert "재물 신호 있음(불리 방향: 巳申 파)" in by_date["2026-06-04"].reasons
    risky = by_date["2026-06-05"]
    assert risky.risk_relations == ["巳亥 충 ×2", "子午 충"]
    assert "걸리는 관계 3건(巳亥 충 ×2·子午 충)" in risky.reasons


def test_reason_for_other_purposes_is_truthful(engine, base_composites) -> None:
    """다른 목적도 신호 0건인 날을 '신호 기반'이라 적지 않고, 사유를 엔진 값으로 싣는다."""
    result = engine.select(
        EventKey.BUSINESS_START, _crafted(base_composites), "2026-06-03", "2026-06-03",
    )
    assert result.candidates
    reasons = result.candidates[0].reasons
    assert reasons[0].startswith("천간 ") and "(용신)" in reasons[0]
    assert reasons[1:3] == ["직업 신호 없음", "걸리는 관계(충·형·원진) 없음"]
    assert not any("횡재 관점" in r for r in reasons)


def test_relation_labels() -> None:
    assert relation_label_ko("rel_巳申破") == "巳申 파"
    assert relation_label_ko("rel_午午自刑") == "午午 자형"
    assert relation_label_ko("rel_子未怨嗔") == "子未 원진"
    assert relation_label_ko("rel_甲庚沖") == "甲庚 충"
    assert relation_label_ko("rel_복음") == "복음"  # 모르는 꼴은 그대로
    # 부분 성립(2자) 삼형은 완성형 ID 대신 실제 참여 글자로 — 없는 寅이 있는 것처럼 읽히지 않게.
    partial = InteractionHit(
        relation_id="rel_寅巳申三刑", kind=InteractionKind.BRANCH_PUNISH, partial=True,
        participants=[
            InteractionParticipant(source=InteractionSource.NATAL_HOUR, ganji="巳"),
            InteractionParticipant(source=InteractionSource.DAY, ganji="申"),
        ],
    )
    assert hit_label_ko(partial) == "巳申 형(삼형 일부)"
    assert hit_label_ko(partial.model_copy(update={"partial": False})) == "寅巳申 삼형"


# ── C. 횡재 관점 라벨 ────────────────────────────────────────────


def test_body_side() -> None:
    assert body_side("신약", False) == BODY_WEAK
    assert body_side("중화신약", False) == BODY_WEAK
    assert body_side("신강", False) == BODY_STRONG
    assert body_side("신약", True) == BODY_STRONG  # 강신 게이트 통과가 우선
    assert body_side("중화", False) == BODY_NEUTRAL


def test_lens_peer_depends_on_body() -> None:
    """실답의 날(乙未: 편관/비견) — 비겁은 신약이면 감당 조건, 신강이면 나뉘는 쪽. 어느 쪽도
    '유입 표지'가 아니다."""
    weak = windfall_day_lens(
        stem_ten_god="편관", branch_ten_god="비견", body=BODY_WEAK, wealth_role="구신")
    assert len(weak) == 1 and "비겁(지지)" in weak[0] and "감당하는 조건" in weak[0]
    assert "유입 표지는 아니다" in weak[0]
    strong = windfall_day_lens(
        stem_ten_god="겁재", branch_ten_god="겁재", body=BODY_STRONG, wealth_role="용신")
    assert "비겁(천간·지지)" in strong[0] and "나뉘는 쪽" in strong[0]
    neutral = windfall_day_lens(
        stem_ten_god="비견", branch_ten_god="정관", body=BODY_NEUTRAL, wealth_role=None)
    assert "유입 표지가 아니다" in neutral[0]


def test_lens_wealth_star_and_output() -> None:
    burden = windfall_day_lens(
        stem_ten_god="편재", branch_ten_god="정인", body=BODY_WEAK, wealth_role="구신")
    assert burden[0].startswith("편재(천간) — 횡재 유입 표지") and "구신" in burden[0]
    assert "인성(지지)" in burden[1]
    good = windfall_day_lens(
        stem_ten_god="식신", branch_ten_god="편재", body=BODY_STRONG, wealth_role="용신")
    assert "유리한 방향" in good[0]
    assert "통로와 유입이 이어진다" in good[1]
    # 반례: 인성은 신약일 때만 라벨이 붙고, 정재·관성에는 라벨이 없다.
    assert windfall_day_lens(
        stem_ten_god="정인", branch_ten_god="정재", body=BODY_STRONG, wealth_role="한신") == []
    assert windfall_day_lens(
        stem_ten_god="정관", branch_ten_god="정재", body=BODY_WEAK, wealth_role="한신") == []


def test_lens_only_for_windfall_purpose(engine, base_composites) -> None:
    comps = _crafted(base_composites)
    windfall = engine.select(
        EventKey.WINDFALL, comps, "2026-06-02", "2026-06-05", top_n=8, body=BODY_WEAK)
    change = engine.select(
        EventKey.WEALTH_CHANGE, comps, "2026-06-02", "2026-06-05", top_n=8, body=BODY_WEAK)
    assert any(c.lens_notes for c in windfall.candidates)
    assert not any(c.lens_notes for c in change.candidates)
    assert not any("횡재 관점" in r for c in change.candidates for r in c.reasons)


# ── 프롬프트 지시 분기 ───────────────────────────────────────────


def test_no_recommend_instruction_differs() -> None:
    assert "1–3개 날짜를 명확히 추천할 것" in _DATE_TABLE_INSTRUCTION
    assert "추천할 것" not in _DATE_TABLE_NO_RECOMMEND_INSTRUCTION
    assert "회피성 답변을 절대 하지 말 것" in _DATE_TABLE_NO_RECOMMEND_INSTRUCTION
    assert "천간 십성과 지지 십성을 함께" in _DATE_TABLE_GRADE_INSTRUCTION


# ── 생성 후 감사(로그 전용) ──────────────────────────────────────


def _block(recommendation: str = "acceptable") -> DateSelectionBlock:
    return DateSelectionBlock(
        purpose_ko="횡재", period="2026-11-16 – 2026-11-21",
        grade_notes=["[추천]은 …"], has_recommended=False,
        rows=[
            DateChoiceRow(
                date="2026-11-17", weekday="화", ganji="乙未", score=70,
                recommendation=recommendation,
                stem_ten_god="편관", branch_ten_god="비견", stem_role="기신"),
            DateChoiceRow(
                date="2026-11-19", weekday="목", ganji="丁酉", score=70,
                recommendation="acceptable",
                stem_ten_god="편인", branch_ten_god="식신", stem_role="희신"),
        ],
    )


def test_audit_flags_real_answer_sentence() -> None:
    answer = (
        "가장 추천하는 날인 11월 17일 화요일은 비견의 기운이 들어와 일간의 힘을 실어주는 "
        "날입니다. 11월 19일 목요일은 편인의 기운이 들어와 직관력이 예리해지는 날입니다."
    )
    audit = audit_date_table_answer(answer, _block())
    assert len(audit.stem_omitted) == 1 and audit.stem_omitted[0].startswith("2026-11-17")
    assert len(audit.grade_raised) == 1 and audit.grade_raised[0].startswith("2026-11-17")
    assert not audit.clean


def test_audit_counter_examples() -> None:
    block = _block()
    # 천간·지지를 함께 말한 문장, 부정 표현, 희신 천간 날은 걸리지 않는다.
    ok = (
        "17일은 천간에 편관이 부담으로 들어오고 지지의 비견이 버팀목이 되는 날이라 "
        "추천하기는 어렵습니다. 목요일은 식신이 들어오는 무난한 날입니다."
    )
    assert audit_date_table_answer(ok, block).clean
    # 두 날을 한 문장에 묶으면 판정하지 않는다.
    both = "화요일과 목요일 모두 비견과 식신이 들어와 추천합니다."
    assert audit_date_table_answer(both, block).clean
    # [추천] 등급 날을 추천이라 부르는 것은 정당하다.
    assert not audit_date_table_answer(
        "11월 17일은 편관과 비견이 함께 들어오는 추천일입니다.", _block("recommended"),
    ).grade_raised
    # 등급 기준을 쓰지 않는 표(이사 등)는 감사하지 않는다.
    plain = block.model_copy(update={"grade_notes": []})
    assert audit_date_table_answer("11월 17일은 비견이 들어와 추천합니다.", plain).clean
    assert audit_date_table_answer("", block).clean
    assert audit_date_table_answer("아무 말", None).clean
