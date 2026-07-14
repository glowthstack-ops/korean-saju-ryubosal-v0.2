"""총운형 다변화 선별 회귀 테스트 (2026-07-14 데굴님 설계 확정).

실측 결함: "앞으로 1년 주요 이벤트"(FORTUNE_OVERVIEW·general)에 순수 점수순 Top-5를
적용해 한 사건(재물 변화)이 기간만 바꿔 5슬롯을 독점 → 답변이 단일 도메인으로 쏠림.

고정 축(감수 회신의 8케이스): ①동일 사건 월별 반복=1클러스터+반복 노트 ②실제
다도메인=2~3도메인 선택 ③단일 도메인 압도=약한 후보 강제 미포함 ④동일 key 반대
방향=분리 ⑤동일 key 독립 원인=분리 ⑥life_fit 계층 불변 ⑦특정 도메인 질문 불변
(활성 게이트) ⑧유효 클러스터 부족 시 강제 충원 금지.
"""

from __future__ import annotations

from saju_api.services.chat_service import _is_overview_multi_domain
from saju_engines.context_reducer import (
    OVERVIEW_COVERAGE_MIN_SCORE,
    reduce_overview_candidates,
)
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventKey,
    EventPolarity,
    EventType,
    Signal,
)
from saju_shared_types.intent import Domain, IntentJson, QueryType


def _cand(
    key: str,
    period: str,
    score: int,
    quality: str | None = "opportunity",
    trigger: str = "ten_god_activation",
    life_fit: float = 0.0,
    favorability: float = 0.5,
) -> EventCandidate:
    return EventCandidate(
        event_key=EventKey(key),
        event_type=EventType.PROGRESS,
        period=period,
        score=score,
        confidence=Confidence.MEDIUM,
        polarity=EventPolarity.POSITIVE,
        quality=quality,
        favorability=favorability,
        life_fit=life_fit,
        signals=[Signal(type=trigger, name="신호", effect="", weight=10.0)],
    )


def _select(cands: list[EventCandidate], top_n: int = 5):
    return reduce_overview_candidates(cands, "2026-07", "2027-06", top_n=top_n)


def test_case1_same_event_monthly_repeat_aggregates() -> None:
    """①동일 사건 월별 반복 — 대표 1개 + supporting_periods 반복 노트로 집계."""
    cands = [
        _cand("wealth_change", p, s)
        for p, s in [("2027-01", 91), ("2026-12", 88), ("2027-06", 84),
                     ("2026-09", 80), ("2026-10", 78)]
    ]
    selected, notes, _ = _select(cands)
    assert len(selected) == 1  # 5개 후보가 1클러스터로 압축
    assert selected[0].period == "2027-01"  # 최고점 기간이 대표
    assert 0 in notes and "총 5회" in notes[0] and "2026-12" in notes[0]


def test_case2_multi_domain_coverage() -> None:
    """②실제 다도메인 — 충분히 강한 재물·직업·이동이 모두 선택된다."""
    cands = [
        _cand("wealth_change", "2027-01", 91),
        _cand("wealth_change", "2026-12", 88),
        _cand("career_change", "2026-10", 82),
        _cand("relocation", "2027-03", 76),
    ]
    selected, _, _ = _select(cands)
    domains = {str(c.event_key) for c in selected}
    assert {"wealth_change", "career_change", "relocation"} <= domains


def test_case3_single_domain_dominance_preserved() -> None:
    """③단일 도메인 압도 — 게이트 미달(43·38·31점) 후보를 억지로 끌어올리지 않는다."""
    cands = [
        _cand("wealth_change", "2027-01", 91),
        _cand("wealth_change", "2026-12", 88, trigger="branch_clash"),  # 별도 원인 클러스터
        _cand("career_change", "2026-10", 79),
        _cand("new_relationship", "2026-09", 43),
        _cand("relocation", "2027-02", 41),
    ]
    selected, _, _ = _select(cands)
    keys = [str(c.event_key) for c in selected]
    assert "new_relationship" not in keys and "relocation" not in keys
    assert keys[0] == "wealth_change" and "career_change" in keys
    # 게이트 상수 자체 확인 — 43점은 절대 최소(55) 미달.
    assert 43 < OVERVIEW_COVERAGE_MIN_SCORE


def test_case4_opposite_direction_not_merged() -> None:
    """④동일 event_key 반대 방향(기회 vs 손실) — 하나로 합치지 않는다."""
    cands = [
        _cand("wealth_change", "2027-01", 91, quality="opportunity", favorability=0.6),
        _cand("wealth_change", "2027-06", 87, quality="loss", favorability=-0.6),
    ]
    selected, _, _ = _select(cands)
    assert len(selected) == 2
    assert {c.quality for c in selected} == {"opportunity", "loss"}


def test_case5_independent_trigger_kept_separate() -> None:
    """⑤동일 key·같은 방향이라도 지배 신호 계열이 다르면 별도 클러스터."""
    cands = [
        _cand("wealth_change", "2026-09", 90, trigger="ten_god_activation"),
        _cand("wealth_change", "2027-05", 85, trigger="branch_clash"),
    ]
    selected, notes, _ = _select(cands)
    assert len(selected) == 2 and notes == {}


def test_case6_life_fit_tier_not_broken() -> None:
    """⑥life_fit 계층 불변 — 비적합(낮은 life_fit) 새 도메인이 적합 후보를 밀지 않는다."""
    cands = [
        _cand("wealth_change", "2027-01", 85, life_fit=0.8),
        _cand("wealth_change", "2026-11", 82, life_fit=0.8, trigger="branch_clash"),
        # 새 도메인이지만 life_fit 격차(0.8→0.1)가 허용 창(0.15)을 초과 — 커버리지 제외.
        _cand("career_change", "2026-10", 84, life_fit=0.1),
    ]
    selected, _, _ = _select(cands, top_n=2)
    keys = [str(c.event_key) for c in selected]
    assert keys == ["wealth_change", "wealth_change"]


def test_case7_domain_question_unaffected() -> None:
    """⑦특정 도메인·이벤트·단일최대 질문은 다변화 모드 밖(기존 Top-N 그대로)."""
    base = dict(intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW)
    overview = IntentJson(**base, domain=Domain.GENERAL)
    assert _is_overview_multi_domain(
        overview, "앞으로 1년내에 내게 있을 주요 이벤트는 뭐가 있을까?"
    )
    # 도메인 확정 질문 — 미적용.
    wealth = IntentJson(**base, domain=Domain.WEALTH)
    assert not _is_overview_multi_domain(wealth, "내년 재물운 어때?")
    # 분석형 질문 유형 — 미적용.
    analysis = IntentJson(
        intent_id="i2", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.GENERAL
    )
    assert not _is_overview_multi_domain(analysis, "올해 흐름 알려줘")
    # 단일 최대 사건 요구 — 다양화 대신 최고점 중심.
    assert not _is_overview_multi_domain(overview, "내년에 가장 중요한 일은 뭐야?")
    assert not _is_overview_multi_domain(overview, "내년 조심할 거 딱 하나만 알려줘")


def test_case9_co_top_not_crowded_out_by_coverage() -> None:
    """⑨근-최고점 후보가 커버리지에 밀리지 않는다(2026-07-14 실사용 2차 결함).

    실측: '주요 이벤트' 총운에서 결혼 신호 98점이 커버리지 패스의 이동 82·건강 75점에
    슬롯을 뺏겨 탈락 — 후속 질문("애정운은 없어?")에서야 드러남. co-top 창(최고점−10)
    이내 클러스터는 도메인 커버리지보다 우선한다.
    """
    cands = [
        _cand("job_gain", "2027-02", 100),
        _cand("career_change", "2027-03", 99),
        _cand("relationship_change", "2026-07", 98),
        _cand("marriage_signal", "2027", 98),
        _cand("contract_document", "2026-08", 97),
        _cand("wealth_change", "2026-10", 96),
        _cand("relocation", "2026-07", 82),
        _cand("health_attention", "2027-04", 75),
    ]
    selected, _, _ = _select(cands)
    keys = [str(c.event_key) for c in selected]
    assert "marriage_signal" in keys  # 98점 결혼 신호는 반드시 포함
    assert "career_change" in keys  # 99점도 포함
    # 도메인 캡 — career 3개(100·99·97) 전부가 아니라 최대 2개(관계·재물에 자리).
    career = [k for k in keys if k in ("job_gain", "career_change", "contract_document")]
    assert len(career) == 2
    assert "health_attention" not in keys  # 75점이 98점을 밀어내지 않는다


def test_case8_no_forced_fill() -> None:
    """⑧유효 클러스터가 1~2개뿐이면 약한 후보로 3~5개를 강제 충원하지 않는다."""
    cands = [
        _cand("wealth_change", "2027-01", 91),
        _cand("career_change", "2026-10", 80),
        _cand("health_attention", "2026-09", 38),  # floor(40) 미달 — pool 제외
    ]
    selected, _, _ = _select(cands)
    assert len(selected) == 2


def test_case11_no_score_or_key_leak_in_selection_reason() -> None:
    """⑪세운 선별 사유 — 점수 숫자·영문 키 비노출('98점' 인용 사고의 소스 차단)."""
    from saju_engines.context_reducer import _selection_reason

    reason = _selection_reason("2027", [
        _cand("wealth_change", "2027", 98),
        _cand("marriage_signal", "2027", 91),
    ])
    assert "98" not in reason and "wealth_change" not in reason
    assert "재물" in reason and "매우 강" in reason  # 한글 라벨 + tone 표현


def test_case12_overview_display_order_by_score() -> None:
    """⑫총운 표시 순서 — 선정은 life_fit 계층, 직렬화는 강도(점수) 내림차순.

    실측(5차): fit 부스트를 받은 최약 직업 후보(흐름 등급)가 목록 맨 앞에 놓여
    LLM 서술 리드를 잡음 — 표시 순서만 점수순으로 조정(선정 결과 불변).
    """
    from saju_engines.context_reducer import reduce_overview_candidates

    cands = [
        _cand("career_change", "2027", 60, life_fit=0.9),  # fit 최상, 점수 최약
        _cand("relationship_change", "2026-07", 99, life_fit=0.8),
        _cand("wealth_change", "2026-10", 96, life_fit=0.8),
    ]
    selected, _, _ = reduce_overview_candidates(cands, "2026-07", "2027-06")
    # 선정 자체는 fit 우선 정렬(career가 global top) — 3개 모두 선정.
    assert len(selected) == 3
    # 표시 정렬은 build_llm_input에서 수행 — 여기서는 점수순 재정렬 결과를 검증.
    disp = sorted(selected, key=lambda c: (-c.score, c.period))
    assert str(disp[0].event_key) == "relationship_change"  # 최강 신호가 리드
    assert str(disp[-1].event_key) == "career_change"


def test_case13_coverage_detector_sentence_level() -> None:
    """⑬커버리지 계측(관측 전용 — 재생성 금지, 데굴님 확정) — 문장 단위 동시 출현 판정.

    실측: 답변에 '관계'와 '7월'이 서로 다른 문장에 있어도 전역 검사는 통과 —
    같은 문장에 라벨 토큰+기간 마커가 함께 있어야 서술로 인정한다.
    """
    from saju_api.services.chat_service import _overview_missed_candidates
    from saju_shared_types.events import EventKey, EventType  # noqa: F401
    from saju_shared_types.llm_input import LlmEventCandidate

    def _lc(key: str, ko: str, period: str) -> LlmEventCandidate:
        return LlmEventCandidate(
            event_key=EventKey(key), event_ko=ko, period=period, ganji="乙未",
            daewoon_context="壬辰", score=90, confidence="medium", polarity="positive",
        )

    cands = [
        _lc("relationship_change", "관계 변화", "2026-07"),
        _lc("wealth_change", "재물 변화", "2027-02"),
        _lc("career_change", "이직·직업 변화", "2026-12"),
    ]
    answer = (
        "2027년 2월에는 재물 변화와 지출 압박이 함께 옵니다. "
        "2026년 12월에는 직업 변동 신호가 강합니다. "
        "7월은 책임이 늘어나는 시기예요. 주변 관계는 대체로 무난합니다."
    )
    missed = _overview_missed_candidates(answer, cands)
    # 재물(2월)·직업(12월)은 같은 문장에 라벨+시기 동시 출현 → 커버.
    # 관계(7월)는 '관계'와 '7월'이 다른 문장 → 누락으로 계측.
    assert missed == ["관계 변화 @ 2026-07"]


def test_case10_dropped_notable_meta() -> None:
    """⑩선정 제외 강신호 메타(not_selected_due_to_limit) — 침묵 대신 제한 언급 채널.

    실측(데굴님 재검): 개인화 life_fit 계층에서 밀린 결혼 신호 98점이 총운에서 완전
    침묵 — '신호 없음'이 아니므로 근-최고점 미선정 클러스터는 사유와 함께 메타로
    노출한다(감수 확정: 엔진 메타가 있을 때만 제한 언급).
    """
    # life_fit 강등 — 점수는 co-top인데 개인화 적합도 격차로 게이트 탈락.
    cands = [
        _cand("career_change", "2027-02", 100, life_fit=0.6),
        _cand("wealth_change", "2026-10", 96, life_fit=0.6),
        _cand("marriage_signal", "2027", 98, life_fit=0.1),
    ]
    selected, _, dropped = _select(cands)
    keys = [str(c.event_key) for c in selected]
    assert "marriage_signal" not in keys  # life_fit 계층 불변(감수 규칙 ④)
    assert len(dropped) == 1
    assert "결혼" in dropped[0] and "개인화 적합도" in dropped[0]
    # 슬롯 제한 — 게이트는 통과했지만 top_n에서 밀린 근-최고점도 메타에 남는다.
    many = [
        _cand("job_gain", "2027-02", 100),
        _cand("career_change", "2027-03", 99),
        _cand("relationship_change", "2026-07", 98),
        _cand("marriage_signal", "2027", 98),
        _cand("wealth_change", "2026-10", 97),
        _cand("contract_document", "2026-08", 96),
    ]
    sel2, _, dropped2 = _select(many, top_n=4)
    assert any("조망 슬롯 제한" in d for d in dropped2)
    # '강' 등급(70) 미달 탈락은 메타에 넣지 않는다(노이즈 방지 — 3차 확대 후 하한).
    low = [_cand("wealth_change", "2027-01", 91), _cand("relocation", "2026-08", 60)]
    _, _, dropped3 = _select(low, top_n=1)
    assert dropped3 == []
    # 3차 확대 — 85점급(최고점 100, co-top 창 밖·상대 창 −30 안)도 메타에 남는다.
    mid = [
        _cand("job_gain", "2027-02", 100),
        _cand("career_change", "2027-03", 99, trigger="branch_clash"),
        _cand("marriage_signal", "2027", 85),
    ]
    _, _, dropped4 = _select(mid, top_n=2)
    assert any("결혼" in d for d in dropped4)
    # 캡 3건 — 강신호가 많아도 메타는 상위 3개까지만.
    crowd = [_cand("job_gain", "2027-02", 100)] + [
        _cand(k, p, 90, trigger=t)
        for k, p, t in [
            ("career_change", "2027-03", "tg"), ("marriage_signal", "2027", "tg"),
            ("wealth_change", "2026-10", "tg"), ("relocation", "2026-08", "tg"),
            ("education_admission", "2026-09", "tg"),
        ]
    ]
    _, _, dropped5 = _select(crowd, top_n=1)
    assert len(dropped5) == 3
