"""추첨·선발·배치(selection_allocation) 코어 테스트 (2026-07-14 설계).

검증 축: ①상태 머신(이진 당첨값 금지 — 대기·차선·취소 서사) ②기능 신호·단계 점수
(십성군 매핑, 경쟁 반전, merit형 가중) ③외부 무작위성 캡(추첨=confidence low·점수
상한) ④질문 파싱(도메인·단계 분리 — 군입대 단일 인텐트 금지) ⑤실차트 통합 +
LLM 블록 표현 정책. shadow-first — 기존 사건 점수·판정 불변이 전제.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.selection_allocation import (
    analyze_selection_allocation,
    format_selection_reading_block,
    score_stages,
    signal_strengths,
)
from saju_engines.selection_intent import detect_selection_query
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.direction_suggestions import DirectionFacts
from saju_shared_types.selection_allocation import (
    FunctionSignal,
    SelectionMechanism,
    SelectionMode,
    SelectionStage,
    SelectionState,
    can_transition,
)


def _facts(**overrides: object) -> DirectionFacts:
    """합성 facts — 관성·인성 작동(선발 우호형) 기본형."""
    base: dict[str, object] = {
        "group_states": {"authority": ["luck_inflow"]},
        "ten_god_present": ["ZHENGGUAN", "ZHENGYIN", "SHISHEN", "BIJIAN"],
        "ten_god_active": ["ZHENGGUAN", "ZHENGYIN"],
        "yongsin_roles": {"authority": "yongsin", "resource": "heesin"},
        "group_conflicts": {},
    }
    base.update(overrides)
    return DirectionFacts.model_validate(base)


# ── ① 상태 머신 ────────────────────────────────────────────────────


def test_state_machine_realistic_flows() -> None:
    """대표 흐름 — 차선 배정 수락·대기 전환이 구조로 표현된다."""
    flow = [
        SelectionState.ELIGIBLE, SelectionState.SELECTED,
        SelectionState.ALLOCATED_NONPREFERRED, SelectionState.ACCEPTED,
        SelectionState.EXECUTED, SelectionState.ADAPTED_MIXED,
    ]
    assert all(can_transition(a, b) for a, b in zip(flow, flow[1:], strict=False))
    waitlist = [
        SelectionState.ELIGIBLE, SelectionState.NOT_SELECTED,
        SelectionState.WAITLISTED, SelectionState.SELECTED,
        SelectionState.ALLOCATED_PREFERRED,
    ]
    assert all(can_transition(a, b) for a, b in zip(waitlist, waitlist[1:], strict=False))
    # 선발은 자격 재검토 취소로도 빠질 수 있다(설계 §1).
    assert can_transition(SelectionState.SELECTED, SelectionState.CANCELLED)
    # 단계 건너뛰기 금지 — 선발에서 곧장 적응으로 갈 수 없다.
    assert not can_transition(SelectionState.SELECTED, SelectionState.ADAPTED_POSITIVE)
    assert not can_transition(SelectionState.NOT_APPLIED, SelectionState.SELECTED)


# ── ② 기능 신호·단계 점수 ──────────────────────────────────────────


def test_signals_reflect_group_facts() -> None:
    """관성 작동+용신 → institution 강, 식상 부재 → application 약."""
    sig = {e.signal: e for e in signal_strengths(_facts())}
    assert sig[FunctionSignal.INSTITUTION].strength > 0.8  # 작동+용신+운유입
    assert sig[FunctionSignal.APPLICATION].strength <= 0.45  # 존재(비작동)
    assert sig[FunctionSignal.BENEFIT].strength <= 0.25  # 재성 부재
    assert "용신" in sig[FunctionSignal.INSTITUTION].basis


def test_transition_linked_to_clash_not_selection() -> None:
    """충 신호는 transition(실행)으로 — 당첨 단계 가중엔 없다(설계 §2-충·역마)."""
    calm = {e.signal: e for e in signal_strengths(_facts())}
    moving = {e.signal: e for e in signal_strengths(
        _facts(group_conflicts={"authority": ["충"]})
    )}
    assert moving[FunctionSignal.TRANSITION].strength > calm[FunctionSignal.TRANSITION].strength
    mech = SelectionMechanism(selection_mode=SelectionMode.LOTTERY)
    calm_scores = score_stages(list(calm.values()), mech)
    moving_scores = score_stages(list(moving.values()), mech)
    assert moving_scores.execution > calm_scores.execution


def test_competition_inverted_and_softened_by_role() -> None:
    """비겁 과다=경쟁 강화(선발 감점), 비겁이 용·희신이면 감점 완화(설계 §7)."""
    crowded = signal_strengths(_facts(
        ten_god_active=["ZHENGGUAN", "ZHENGYIN", "BIJIAN"],
        group_states={"peer": ["natal_excess"]},
    ))
    mech = SelectionMechanism(selection_mode=SelectionMode.SCORE_RANKED)
    hard = score_stages(crowded, mech, peer_favorable=False)
    soft = score_stages(crowded, mech, peer_favorable=True)
    assert soft.selection_support > hard.selection_support


def test_merit_mode_weights_application() -> None:
    """점수제 선발은 식상·인성(제출·자격) 비중이 커진다(설계 §2-③)."""
    output_strong = signal_strengths(_facts(
        ten_god_active=["SHISHEN", "SHANGGUAN", "ZHENGYIN"],
        yongsin_roles={"output": "yongsin", "resource": "heesin"},
    ))
    lottery = score_stages(
        output_strong, SelectionMechanism(selection_mode=SelectionMode.LOTTERY)
    )
    merit = score_stages(
        output_strong, SelectionMechanism(selection_mode=SelectionMode.SCORE_RANKED)
    )
    assert merit.selection_support > lottery.selection_support


# ── ③ 외부 무작위성 캡 ─────────────────────────────────────────────


def test_lottery_caps_scores_and_confidence() -> None:
    """순수 추첨 — selection_support ≤70, confidence 'low'(설계 §4·§8)."""
    maxed = [
        e.model_copy(update={"strength": 1.0}) for e in signal_strengths(_facts())
    ]
    lottery = score_stages(maxed, SelectionMechanism(selection_mode=SelectionMode.LOTTERY))
    assert lottery.selection_support <= 70
    assert lottery.preference_match <= 65
    ranked = score_stages(
        maxed, SelectionMechanism(selection_mode=SelectionMode.SCORE_RANKED)
    )
    assert ranked.selection_support > lottery.selection_support


# ── ④ 질문 파싱(설계 §9) ───────────────────────────────────────────


def test_query_stage_mapping() -> None:
    """군입대 단일 인텐트 금지 — 표현별 단계 분리."""
    cases = {
        "군대 지원해도 될까?": ("military_service", SelectionStage.APPLICATION),
        "이번 입영 추첨에 붙을까?": ("military_service", SelectionStage.SELECTION),
        "원하는 날짜로 입영 갈 수 있을까?": (
            "military_service", SelectionStage.PREFERENCE_MATCH,
        ),
        "청약에 당첨될까?": ("housing_subscription", SelectionStage.SELECTION),
        "기숙사 배정 받을 수 있을까?": (
            "dormitory_assignment", SelectionStage.ALLOCATION,
        ),
        "배정된 학교에서 잘 적응할까?": (
            "school_assignment", SelectionStage.ADAPTATION,
        ),
    }
    for text, (domain, stage) in cases.items():
        q = detect_selection_query(text)
        assert q is not None, text
        assert (q.domain, q.stage) == (domain, stage), text


def test_query_guards() -> None:
    """로또(횡재 정책 관할)·비선발 질문은 감지하지 않는다."""
    assert detect_selection_query("로또 당첨될까?") is None
    assert detect_selection_query("내년에 이직할 수 있을까?") is None
    assert detect_selection_query("대학에 합격할까?") is None  # 시험은 기존 분류 관할
    waitq = detect_selection_query("청약 떨어지면 다음 회차는 어때?")
    assert waitq is not None and waitq.waitlist_focus


def test_followup_inherits_selection_domain() -> None:
    """설계 §9 멀티턴 — 도메인 단어 없는 후속이 직전 답변의 선발 맥락을 승계."""
    prior = "9월 입영 모집병 추첨은 지원 흐름이 살아 있는 편이지만 결과 변수가 큽니다."
    q = detect_selection_query("그래서 원하는 날짜로 갈 수 있다는 거야?", prior_text=prior)
    assert q is not None
    assert q.domain == "military_service"
    assert q.stage is SelectionStage.PREFERENCE_MATCH
    assert not q.explicit_domain  # 승계 표시 — 이번 발화 자체엔 도메인 없음
    # 직전 맥락이 선발형이 아니면 승계하지 않는다.
    assert detect_selection_query(
        "그래서 원하는 날짜로 갈 수 있다는 거야?", prior_text="이사 방위는 남동이 유리해요.",
    ) is None
    # prior 없이 단독 발화도 미감지(기존 경로 유지).
    assert detect_selection_query("그래서 원하는 날짜로 갈 수 있다는 거야?") is None


# ── ⑤ 실차트 통합 + LLM 블록 ───────────────────────────────────────


def _chart():
    return calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울",
        gender="male", reference_date=date(2026, 7, 14),
    ))


def test_analyze_real_chart_military() -> None:
    """실차트 — 군입대 어댑터 기본 방식(가중추첨)·정책 가드가 산출된다."""
    reading = analyze_selection_allocation(
        _chart(), domain="military_service",
        focus_stage=SelectionStage.PREFERENCE_MATCH,
    )
    assert reading.domain == "military_service"
    assert reading.mechanism.selection_mode is SelectionMode.WEIGHTED_LOTTERY
    assert reading.external_uncertainty.level == "high"
    assert reading.response_policy.binary_outcome_prediction is False
    assert reading.response_policy.confidence_cap == "low"
    assert reading.stage_scores.selection_support <= 72
    assert len(reading.signals) == len(FunctionSignal)


def test_weights_dictionary_externalized() -> None:
    """잔여② — 스냅샷/원본/코드 기본값이 같은 구조·값으로 로드된다(원칙 5)."""
    import json
    from pathlib import Path

    from saju_engines.selection_allocation import (
        SELECTION_WEIGHTS_VERSION,
        _default_config,
        load_selection_weights,
    )

    backend = Path(__file__).resolve().parents[2]
    snapshot = backend / "compiled" / (
        f"selection_allocation_weights_v{SELECTION_WEIGHTS_VERSION}.json"
    )
    assert snapshot.exists(), "컴파일 스냅샷 부재 — build_selection_allocation_snapshot 실행"
    loaded = load_selection_weights()
    default = _default_config()
    # 초안(v0.1.0)은 코드 기본값과 동일해야 한다 — 캘리브레이션 전 기준선 고정.
    assert loaded.stage_weights == default.stage_weights
    assert loaded.mode_guards == default.mode_guards
    assert loaded.merit_selection_weights == default.merit_selection_weights
    # 각 단계 가중 합 1.0(빌드 검증과 동일 불변식).
    for stage, ws in loaded.stage_weights.items():
        assert abs(sum(ws.values()) - 1.0) <= 0.001, stage
    # 원본 사전도 validate를 통과한다.
    import importlib.util

    spec_path = backend / "scripts" / "build_selection_allocation_snapshot.py"
    spec = importlib.util.spec_from_file_location("build_sel_snap", spec_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = json.loads(
        (backend / "dictionaries" / "selection_allocation_weights.json").read_text("utf-8")
    )
    assert mod.validate(raw) == []


def test_timing_windows_rank_by_stage_signals() -> None:
    """잔여③ — 초점 단계 신호가 유입되는 달이 유리 창으로 뽑힌다(상대 비교 전용)."""
    from saju_engines.selection_allocation import rank_timing_windows
    from saju_shared_types.luck import LuckPillar

    def _lp(label: str, stem_tg: str, branch_tg: str) -> LuckPillar:
        return LuckPillar(
            label=label, period_type="month", ganji="甲子", stem="甲", branch="子",
            stem_ten_god=stem_tg, branch_ten_god=branch_tg,
        )

    months = [
        _lp("2026-08", "정관", "정인"),  # 관성+인성 — selection 신호 최대
        _lp("2026-09", "비견", "겁재"),  # 비겁 — 경쟁 유입(감산)
        _lp("2026-10", "식신", "정재"),  # 식상+재성
        _lp("2026-11", "정재", "편재"),  # 재성만
    ]
    wins = rank_timing_windows(months, SelectionStage.SELECTION, top_n=2)
    assert wins and wins[0].label == "2026-08"
    assert "관성 유입" in wins[0].reason
    assert all(w.label != "2026-09" for w in wins)  # 비겁 달은 유리 창이 아니다
    # preference_match 초점이면 재성(matching) 달이 앞선다.
    pref = rank_timing_windows(months, SelectionStage.PREFERENCE_MATCH, top_n=2)
    assert pref and pref[0].label == "2026-10"


def test_objective_odds_parse_and_separation() -> None:
    """잔여④ — 경쟁률 파싱 3형 + 지시문 분리 표기(가짜 확률 혼합 금지)."""
    from saju_engines.selection_intent import parse_objective_odds

    ratio = parse_objective_odds("경쟁률이 5대 1이라는데 청약 당첨될까?")
    assert ratio is not None and ratio.base_probability == 0.2
    seats = parse_objective_odds("1000명 중 200명 뽑는 모집병 추첨에 붙을까?")
    assert seats is not None and (seats.applicants, seats.seats) == (1000, 200)
    pct = parse_objective_odds("당첨 확률이 20%라던데 이번 추첨 어때?")
    assert pct is not None and pct.base_probability == 0.2
    assert parse_objective_odds("이번 추첨에 붙을까?") is None  # 수치 없으면 미생성
    # detect가 odds를 싣고, 블록은 분리 표기를 강제한다.
    q = detect_selection_query("경쟁률이 5대 1이라는데 청약 당첨될까?")
    assert q is not None and q.odds is not None
    reading = analyze_selection_allocation(
        _chart(), domain="housing_subscription", objective_odds=q.odds,
    )
    block = format_selection_reading_block(reading)
    assert "객관 경쟁률(사용자 제공): 약 20%" in block
    assert "분리 서술하라" in block


def test_report_lines_notable_gate() -> None:
    """잔여⑤ 방안2 — 기관·자격 신호 notable일 때만 리포트 블록 노출(미달=무언급)."""
    from saju_engines.selection_allocation import selection_report_lines

    lines = selection_report_lines(_chart(), "housing_subscription")
    # 실차트(1980-11-22, 2026)는 관성 작동 — 노출되며 지침·상한이 실린다.
    assert lines and "청약·공공주택" in lines[0]
    assert "무관하면 통째로 언급하지 말 것" in lines[2]
    assert "확률 % 표시는 금지" in lines[2]


def test_report_section_attachment_map() -> None:
    """잔여⑤ 방안2 — 부착 지점은 기존 운 신호 섹션(목차 불변, 원칙 10)."""
    from saju_api.services.report_service import _SELECTION_AUX_SECTIONS

    assert _SELECTION_AUX_SECTIONS == {
        "RL-04": "housing_subscription",
        "J-04": "workplace_assignment",
    }


def test_format_block_policy_and_labels() -> None:
    """LLM 블록 — 도메인 언어 번역 + 단정 금지·분리 서술·답변 형식 계약."""
    reading = analyze_selection_allocation(
        _chart(), domain="military_service", focus_stage=SelectionStage.SELECTION,
    )
    block = format_selection_reading_block(reading)
    assert "군입대·모집병" in block
    assert "단정하지 말 것" in block and "확률 % 표시 금지" in block
    assert "분리해 서술하라" in block  # 선발 ≠ 희망 조건 배치
    assert "실제 실행" in block and "결과 변수가 크다" in block  # 추첨성 명시
    assert "결론(1~2문장)" in block
    # 청약 어댑터는 같은 신호를 주거 언어로 번역한다(범용성 회귀 — 설계 §6).
    housing = analyze_selection_allocation(_chart(), domain="housing_subscription")
    hblock = format_selection_reading_block(housing)
    assert "청약·공공주택" in hblock and "청약 가점" in hblock
