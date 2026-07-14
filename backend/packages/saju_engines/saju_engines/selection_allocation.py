"""추첨·선발·배치(selection_allocation) 풀이 엔진 (2026-07-14 데굴님 설계, shadow-first).

십성군 사실(DirectionFacts — 능동 제안 레이어와 공유)을 도메인 중립 **기능 신호**
(institution/qualification/application/competition/benefit/matching/transition/stability)로
추상화한 뒤, 단계별 가중 결합으로 8단계 성립도 점수를 산출한다. 도메인 어댑터
(군입대·청약·학교 등)는 신호를 현실 언어로 바꿀 뿐 판정을 바꾸지 않는다.

가중 상수는 사전(`dictionaries/selection_allocation_weights.json`)으로 외부화됐다 —
컴파일 스냅샷 우선 → 원본 폴백 → 코드 기본값(graceful, 원칙 5). 골든 사례
캘리브레이션(잔여 ①)은 이 사전을 조정한다.

핵심 가드(설계 §4·§8):
- 추첨 비중이 높은 선발 방식은 confidence 상한·단계 점수 상한을 강제한다.
- 당첨·탈락 단정, 확률 % 표시를 response_policy로 금지한다(상대 비교·단계 강약만 허용).
- 비겁(경쟁 신호)은 탈락 고정이 아니라 경쟁 환경 강도 — 용기신 여부로 감점 폭이 다르다.
- 충·이동 신호는 당첨이 아니라 실행(execution) 단계에 연결한다.
- 객관 경쟁률(objective_odds)은 사주 해석과 혼합 금지 — 분리 표기만 허용한다.

검증(실사례 캘리브레이션) 전까지 설명 보조 전용 — 기존 사건 점수·판정에 일절 개입하지
않는다(절대원칙 1·9).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_shared_types.direction_suggestions import DirectionFacts
from saju_shared_types.event_engine import TEN_GOD_GROUP, TEN_GOD_KO_TO_KEY
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.selection_allocation import (
    SELECTION_DOMAIN_ADAPTERS,
    ExternalUncertainty,
    FunctionSignal,
    ModeGuard,
    ObjectiveOdds,
    ResponsePolicy,
    SelectionAllocationReading,
    SelectionMechanism,
    SelectionMode,
    SelectionSignalEvidence,
    SelectionStage,
    SelectionWeightsConfig,
    StageScores,
    TimingWindow,
)

from .direction_suggestion import build_direction_facts

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
SELECTION_WEIGHTS_VERSION = "0.1.0"

# 군 → 소속 로마자 십성 (direction_suggestion과 동일 역인덱스).
_GROUP_TEN_GODS: dict[str, list[str]] = {}
for _tg, _grp in TEN_GOD_GROUP.items():
    _GROUP_TEN_GODS.setdefault(_grp.value, []).append(_tg.value)

# 기능 신호 ← 십성군 매핑 (설계 §6·§7). transition/stability는 군이 아니라
# 충·마찰 사실에서 산출하므로 여기 없음.
_SIGNAL_GROUP: dict[FunctionSignal, str] = {
    FunctionSignal.INSTITUTION: "authority",  # 관성 — 기관·규칙·선발 체계
    FunctionSignal.QUALIFICATION: "resource",  # 인성 — 자격·서류·승인
    FunctionSignal.APPLICATION: "output",  # 식상 — 지원·표현·시험
    FunctionSignal.COMPETITION: "peer",  # 비겁 — 경쟁자·정원
    FunctionSignal.BENEFIT: "wealth",  # 재성 — 혜택·효용
    FunctionSignal.MATCHING: "wealth",  # 재성 — 희망 조건 일치(효용 실현)
}
_GROUP_KO = {
    "peer": "비겁", "output": "식상", "wealth": "재성",
    "authority": "관성", "resource": "인성",
}

_INFLOW_STATES = frozenset({"luck_inflow", "luck_replenished", "luck_excess_onset"})
_EXCESS_STATES = frozenset({"natal_excess", "excess_intensified", "luck_excess_onset"})
_DEFICIENT_STATES = frozenset({"natal_deficient", "deficient_persistent"})
_ROLE_KO = {"yongsin": "용신", "heesin": "희신", "gisin": "기신", "gusin": "구신"}
_MERIT_MODES = frozenset({SelectionMode.SCORE_RANKED, SelectionMode.HYBRID})

# 코드 기본 가중(사전 부재 시 폴백) — dictionaries/selection_allocation_weights.json과
# 동일 값. 캘리브레이션은 사전에서 하고 이 기본값은 graceful 부팅 보장용이다.
_DEFAULT_STAGE_WEIGHTS: dict[str, dict[str, float]] = {
    "opportunity": {
        "institution_signal": 0.5, "transition_signal": 0.3, "application_signal": 0.2,
    },
    "application": {
        "application_signal": 0.5, "qualification_signal": 0.25, "institution_signal": 0.25,
    },
    "eligibility": {
        "qualification_signal": 0.55, "institution_signal": 0.3, "application_signal": 0.15,
    },
    "selection_support": {
        "institution_signal": 0.4, "application_signal": 0.2,
        "qualification_signal": 0.2, "competition_signal": 0.2,
    },
    "allocation": {
        "institution_signal": 0.4, "matching_signal": 0.3, "transition_signal": 0.3,
    },
    "preference_match": {
        "matching_signal": 0.5, "application_signal": 0.25, "qualification_signal": 0.25,
    },
    "execution": {
        "transition_signal": 0.5, "institution_signal": 0.25, "stability_signal": 0.25,
    },
    "adaptation": {
        "stability_signal": 0.6, "benefit_signal": 0.2, "institution_signal": 0.2,
    },
}
_DEFAULT_MERIT_WEIGHTS: dict[str, float] = {
    "application_signal": 0.35, "qualification_signal": 0.3,
    "institution_signal": 0.2, "competition_signal": 0.15,
}
_DEFAULT_MODE_GUARDS: dict[str, ModeGuard] = {
    "lottery": ModeGuard(
        uncertainty="high", confidence_cap="low",
        selection_cap=70, allocation_cap=75, preference_cap=65,
    ),
    "weighted_lottery": ModeGuard(
        uncertainty="high", confidence_cap="low",
        selection_cap=72, allocation_cap=78, preference_cap=68,
    ),
    "hybrid": ModeGuard(
        uncertainty="medium", confidence_cap="medium",
        selection_cap=80, allocation_cap=82, preference_cap=75,
    ),
    "first_come": ModeGuard(
        uncertainty="medium", confidence_cap="medium",
        selection_cap=82, allocation_cap=84, preference_cap=78,
    ),
    "queue": ModeGuard(
        uncertainty="medium", confidence_cap="medium",
        selection_cap=82, allocation_cap=84, preference_cap=78,
    ),
    "score_ranked": ModeGuard(
        uncertainty="low", confidence_cap="medium",
        selection_cap=88, allocation_cap=88, preference_cap=82,
    ),
    "administrative": ModeGuard(
        uncertainty="medium", confidence_cap="medium",
        selection_cap=84, allocation_cap=84, preference_cap=78,
    ),
}


def _default_config() -> SelectionWeightsConfig:
    """코드 기본 가중 설정 — 사전·스냅샷 부재 시 폴백(graceful)."""
    return SelectionWeightsConfig(
        stage_weights=dict(_DEFAULT_STAGE_WEIGHTS),
        merit_selection_weights=dict(_DEFAULT_MERIT_WEIGHTS),
        mode_guards=dict(_DEFAULT_MODE_GUARDS),
    )


@lru_cache(maxsize=8)
def load_selection_weights(
    dictionaries_dir: Path = _DICTS_DEFAULT, compiled_dir: Path = _COMPILED_DEFAULT
) -> SelectionWeightsConfig:
    """가중 사전 로드 — 컴파일 스냅샷 우선 → 원본 폴백 → 코드 기본값(원칙 5)."""
    snapshot = compiled_dir / f"selection_allocation_weights_v{SELECTION_WEIGHTS_VERSION}.json"
    for path in (snapshot, dictionaries_dir / "selection_allocation_weights.json"):
        if path.exists():
            return SelectionWeightsConfig.model_validate(
                json.loads(path.read_text("utf-8"))
            )
    return _default_config()


def _group_strength(
    facts: DirectionFacts, group: str, cfg: SelectionWeightsConfig
) -> tuple[float, list[str]]:
    """십성군 1개의 신호 강도(0~1)와 근거 조각들."""
    ten_gods = _GROUP_TEN_GODS.get(group, [])
    basis: list[str] = []
    base = cfg.base_strengths
    if any(tg in facts.ten_god_active for tg in ten_gods):
        v = base.get("active", 0.65)
        basis.append("작동")
    elif any(tg in facts.ten_god_present for tg in ten_gods):
        v = base.get("present", 0.40)
        basis.append("존재(비작동)")
    else:
        v = base.get("absent", 0.20)
        basis.append("부재")
    role = facts.yongsin_roles.get(group, "")
    if role in cfg.role_adjust:
        v += cfg.role_adjust[role]
        basis.append(_ROLE_KO.get(role, role))
    states = set(facts.group_states.get(group, []))
    adj = cfg.state_adjust
    if states & _INFLOW_STATES:
        v += adj.get("inflow", 0.10)
        basis.append("운 유입")
    if states & _DEFICIENT_STATES:
        v += adj.get("deficient", -0.15)
        basis.append("부족")
    elif states & _EXCESS_STATES and group != "peer":
        v += adj.get("excess_nonpeer", -0.05)  # 과다 편중 부담
        basis.append("과다 편중")
    elif states & _EXCESS_STATES:
        v += adj.get("excess_peer", 0.10)  # peer 과다 = 경쟁 환경 강화(강도 신호)
        basis.append("경쟁 과다")
    return max(0.0, min(1.0, v)), basis


def signal_strengths(
    facts: DirectionFacts, cfg: SelectionWeightsConfig | None = None
) -> list[SelectionSignalEvidence]:
    """DirectionFacts → 기능 신호 8종 강도 (설계 §6 추상화).

    transition은 충(이동·교체) 마찰 + 운 유입, stability는 마찰 밀도의 역수 +
    인성 보정으로 산출한다 — 이동 신호를 당첨이 아니라 실행에 연결하는 근거.
    """
    cfg = cfg or load_selection_weights()
    out: list[SelectionSignalEvidence] = []
    strengths: dict[FunctionSignal, tuple[float, list[str]]] = {}
    for sig, group in _SIGNAL_GROUP.items():
        strengths[sig] = _group_strength(facts, group, cfg)

    # transition — 충 신호(원국+운)와 운 유입 군 수.
    tw = cfg.transition
    clash_groups = [g for g, kinds in facts.group_conflicts.items() if "충" in kinds]
    inflow_any = any(
        set(states) & _INFLOW_STATES for states in facts.group_states.values()
    )
    t = (
        tw.get("base", 0.30)
        + (tw.get("clash", 0.25) if clash_groups else 0.0)
        + (tw.get("inflow", 0.15) if inflow_any else 0.0)
    )
    t_basis = (
        [f"충 신호({'·'.join(clash_groups)})"] if clash_groups else ["충 신호 없음"]
    ) + (["운 유입"] if inflow_any else [])
    strengths[FunctionSignal.TRANSITION] = (min(1.0, t), t_basis)

    # stability — 형·파·해·충 마찰 밀도의 역수 + 인성(보호·승인) 보정.
    sw = cfg.stability
    friction = sum(1 for kinds in facts.group_conflicts.values() if kinds)
    s = max(0.0, min(1.0, sw.get("base", 0.65) - sw.get("friction_step", 0.10) * friction))
    qual, _ = strengths[FunctionSignal.QUALIFICATION]
    s = max(0.0, min(1.0, s + (qual - 0.4) * sw.get("qualification_coupling", 0.30)))
    s_basis = [f"마찰 군 {friction}개"] + (["인성 보정"] if qual > 0.4 else [])
    strengths[FunctionSignal.STABILITY] = (s, s_basis)

    for sig in FunctionSignal:
        v, basis = strengths[sig]
        out.append(SelectionSignalEvidence(
            signal=sig, strength=round(v, 4), basis="·".join(basis),
        ))
    return out


def score_stages(
    signals: list[SelectionSignalEvidence],
    mechanism: SelectionMechanism,
    peer_favorable: bool = False,
    cfg: SelectionWeightsConfig | None = None,
) -> StageScores:
    """기능 신호 → 8단계 성립도 점수(0~100) + 외부 무작위성 캡 (설계 §5·§8).

    Args:
        signals: signal_strengths 산출물.
        mechanism: 선발·배치 방식 — merit형이면 selection 가중을 제출·자격 중심으로
            교체하고, 추첨형이면 선발·배치·일치 점수에 상한을 강제한다.
        peer_favorable: 비겁이 용·희신인가 — 경쟁 감점 폭 완화(설계 §7 비겁).
        cfg: 가중 설정(미지정 시 사전 로드).
    """
    cfg = cfg or load_selection_weights()
    smap = {e.signal.value: e.strength for e in signals}
    inv = cfg.competition_inversion

    def _combine(weights: dict[str, float]) -> int:
        total = 0.0
        for sig_key, w in weights.items():
            v = smap.get(sig_key, 0.0)
            if sig_key == FunctionSignal.COMPETITION.value:
                # 경쟁 신호는 반전 결합 — 강할수록 선발 압박. 용·희신이면 감점 완화.
                factor = (
                    inv.get("peer_favorable", 0.4) if peer_favorable
                    else inv.get("default", 0.7)
                )
                v = 1.0 - v * factor
            total += v * w
        return round(total * 100)

    weights = dict(cfg.stage_weights or _DEFAULT_STAGE_WEIGHTS)
    if mechanism.selection_mode in _MERIT_MODES:
        weights["selection_support"] = (
            cfg.merit_selection_weights or _DEFAULT_MERIT_WEIGHTS
        )

    scores = StageScores(**{
        stage: _combine(weights[stage]) for stage in _DEFAULT_STAGE_WEIGHTS
    })
    guard = _mode_guard(mechanism.selection_mode, cfg)
    return scores.model_copy(update={
        "selection_support": min(scores.selection_support, guard.selection_cap),
        "allocation": min(scores.allocation, guard.allocation_cap),
        "preference_match": min(scores.preference_match, guard.preference_cap),
    })


def _mode_guard(mode: SelectionMode, cfg: SelectionWeightsConfig) -> ModeGuard:
    """선발 방식별 가드(사전 미등재 방식은 코드 기본값 폴백)."""
    return cfg.mode_guards.get(mode.value) or _DEFAULT_MODE_GUARDS[mode.value]


# SelectionStage → 단계 점수 키(수락은 실행 직전 절차라 execution 축으로 본다).
_STAGE_SCORE_KEY: dict[SelectionStage, str] = {
    SelectionStage.OPPORTUNITY_OPEN: "opportunity",
    SelectionStage.APPLICATION: "application",
    SelectionStage.ELIGIBILITY: "eligibility",
    SelectionStage.SELECTION: "selection_support",
    SelectionStage.ALLOCATION: "allocation",
    SelectionStage.PREFERENCE_MATCH: "preference_match",
    SelectionStage.ACCEPTANCE: "execution",
    SelectionStage.EXECUTION: "execution",
    SelectionStage.ADAPTATION: "adaptation",
}


def rank_timing_windows(
    month_pillars: list[LuckPillar],
    focus_stage: SelectionStage,
    cfg: SelectionWeightsConfig | None = None,
    top_n: int = 3,
) -> list[TimingWindow]:
    """월운 간지의 십성군 유입 기반 상대 유리 창 (잔여 ③ — 사전계산 통합 전 경량 시기 축).

    각 달의 천간·지지 십성(LuckPillar.stem_ten_god/branch_ten_god)이 초점 단계의
    기능 신호 군과 일치하면 그 단계 가중만큼 가산하고, 경쟁(비겁) 유입은 감산한다.
    결과 보장이 아니라 **상대 비교**(response_policy.relative_timing_comparison 허용
    범위)이며, 정식 사전계산(T0~T2) 편입은 골든 검증 후 과제다.
    """
    cfg = cfg or load_selection_weights()
    stage_key = _STAGE_SCORE_KEY[focus_stage]
    weights = (cfg.stage_weights or _DEFAULT_STAGE_WEIGHTS)[stage_key]
    # 신호 → 군(전이·안정 등 군 비매핑 신호는 시기 스윕에서 제외).
    sig_group = {sig.value: grp for sig, grp in _SIGNAL_GROUP.items()}
    out: list[TimingWindow] = []
    for lp in month_pillars:
        groups: set[str] = set()
        for ko in (lp.stem_ten_god, lp.branch_ten_god):
            tg = TEN_GOD_KO_TO_KEY.get(ko)
            if tg is not None:
                groups.add(TEN_GOD_GROUP[tg].value)
        boost = 0.0
        reasons: list[str] = []
        for sig_key, w in weights.items():
            grp = sig_group.get(sig_key)
            if grp is None or grp not in groups:
                continue
            if sig_key == FunctionSignal.COMPETITION.value:
                boost -= w * 0.5
                reasons.append("경쟁(비겁) 유입")
            else:
                label = f"{_GROUP_KO[grp]} 유입"
                if label not in reasons:
                    boost += w
                    reasons.append(label)
        if boost > 0:
            out.append(TimingWindow(
                label=lp.label, boost=round(boost, 4), reason="·".join(reasons),
            ))
    out.sort(key=lambda t: (-t.boost, t.label))
    return out[:top_n]


def analyze_selection_allocation(
    result: ManseV2Result,
    domain: str = "generic",
    focus_stage: SelectionStage = SelectionStage.SELECTION,
    mechanism: SelectionMechanism | None = None,
    objective_odds: ObjectiveOdds | None = None,
) -> SelectionAllocationReading:
    """ManseV2Result → 선발·배치 풀이 (shadow/설명 보조 전용).

    도메인 어댑터의 기본 방식(mechanism)을 쓰되 호출 측이 명시하면 그것을 따른다.
    당첨·탈락 판정이 아니라 단계별 성립도와 표현 정책을 산출한다. objective_odds는
    분리 표기 전용으로 reading에 실린다(엔진 점수와 혼합하지 않음).
    """
    adapter = SELECTION_DOMAIN_ADAPTERS.get(domain) or SELECTION_DOMAIN_ADAPTERS["generic"]
    mech = mechanism or adapter.default_mechanism
    cfg = load_selection_weights()
    facts = build_direction_facts(result)
    signals = signal_strengths(facts, cfg)
    peer_favorable = facts.yongsin_roles.get("peer", "") in ("yongsin", "heesin")
    scores = score_stages(signals, mech, peer_favorable=peer_favorable, cfg=cfg)
    guard = _mode_guard(mech.selection_mode, cfg)
    return SelectionAllocationReading(
        domain=adapter.key,
        focus_stage=focus_stage,
        mechanism=mech,
        stage_scores=scores,
        signals=signals,
        external_uncertainty=ExternalUncertainty(
            level=guard.uncertainty,
            reason=(
                "lottery_based_selection"
                if mech.selection_mode in (
                    SelectionMode.LOTTERY, SelectionMode.WEIGHTED_LOTTERY,
                )
                else f"{mech.selection_mode}_selection"
            ),
        ),
        response_policy=ResponsePolicy(
            binary_outcome_prediction=False,
            confidence_cap=guard.confidence_cap,
            relative_timing_comparison=True,
            allow_waitlist_scenario=mech.waitlist_enabled,
        ),
        objective_odds=objective_odds,
    )


# ── LLM 입력 블록 (설명 보조 — 판정·점수는 위 엔진 산출물 그대로) ──────────

_STAGE_KO = {
    "opportunity": "기회 발생", "application": "지원 실행", "eligibility": "자격·서류",
    "selection_support": "선발 지원도", "allocation": "배정", "preference_match": "희망 조건 일치",
    "execution": "실제 실행", "adaptation": "적응",
}
_CAP_KO = {"low": "낮음", "medium": "보통", "high": "높음"}


def _odds_line(odds: ObjectiveOdds) -> str:
    """객관 경쟁률 분리 표기 라인 (설계 §8 — 가짜 확률 혼합 금지)."""
    prob = odds.base_probability
    if prob is None and odds.applicants and odds.seats and odds.applicants > 0:
        prob = odds.seats / odds.applicants
    detail = (
        f"약 {prob * 100:.0f}%" if prob is not None else "수치 미상"
    )
    if odds.applicants and odds.seats:
        detail += f" (모집 {odds.seats} / 지원 {odds.applicants})"
    return (
        f"객관 경쟁률(사용자 제공): {detail}. 이 수치는 사주 해석과 **별개의 사실**이다 "
        "— 사주 점수와 섞어 보정 확률('사주상 67%' 류)을 만들지 말고, '객관 확률은 "
        "이 정도이고, 사주상 시기·지원 흐름은 이렇다'로 분리 서술하라."
    )


# 리포트 노출 게이트 — 기관(관성)·자격(인성) 신호가 작동 수준 이상일 때만 표면화.
_REPORT_NOTABLE_MIN = 0.65


def selection_report_lines(result: ManseV2Result, domain: str) -> list[str]:
    """리포트용 선발·배치 보조 블록 (2026-07-14 방안 2 확정 — 목차 불변, 조건부 부착).

    리포트는 질문 intent가 없으므로 상시 노출하지 않는다(외적 인상 신호 관행):
    기관(관성)·자격(인성) 신호 중 하나가 작동 수준(≥0.65) 이상일 때만 표면화하고,
    미해당이면 빈 목록 — 본문 무언급을 보장한다. 노출돼도 본문 맥락과 무관하면
    통째 생략하라는 지침을 동봉한다(추첨류 주제 강제 삽입 방지).
    """
    reading = analyze_selection_allocation(result, domain=domain)
    smap = {e.signal: e.strength for e in reading.signals}
    notable = max(
        smap.get(FunctionSignal.INSTITUTION, 0.0),
        smap.get(FunctionSignal.QUALIFICATION, 0.0),
    )
    if notable < _REPORT_NOTABLE_MIN:
        return []
    adapter = SELECTION_DOMAIN_ADAPTERS.get(reading.domain) or (
        SELECTION_DOMAIN_ADAPTERS["generic"]
    )
    s = reading.stage_scores
    cap_ko = _CAP_KO[reading.response_policy.confidence_cap]
    return [
        f"[선발·배치 보조 — {adapter.label_ko}] 기관·자격 신호가 작동 수준이라 "
        "노출 조건을 충족했다(엔진 계산).",
        "단계 성립도(0~100, 상한 적용): "
        f"지원 {s.application} / 자격·서류 {s.eligibility} / 선발 지원도 "
        f"{s.selection_support} / 배정 {s.allocation} / 희망 조건 일치 "
        f"{s.preference_match} / 실제 실행 {s.execution}",
        f"서술 지침: 이 블록은 {adapter.label_ko} 같은 추첨·선발형 주제가 본문 맥락과 "
        "자연스럽게 닿을 때만 1~2문장으로 녹일 것 — 무관하면 통째로 언급하지 말 것. "
        "당첨·탈락 단정과 확률 % 표시는 금지, '선발되는 흐름'과 '희망 조건 배치'는 "
        "분리해 말하고, 이동·충 신호는 당첨 근거가 아니라 실제 실행(계약·입주·등록) "
        f"신호로만 쓸 것. 확신 수준은 최대 '{cap_ko}'.",
    ]


def format_selection_reading_block(
    reading: SelectionAllocationReading,
    timing_windows: list[TimingWindow] | None = None,
) -> str:
    """풀이 결과 → LLM 후행 지시문 블록.

    점수·신호·유리 창은 엔진 산출 사실로 주입하고, 표현 정책(단정 금지·confidence
    상한·답변 형식)을 지시로 강제한다(설계 §7·§11). "선발되는 운"과 "희망 조건
    배치"를 분리 서술하게 하는 것이 핵심이다.
    """
    adapter = SELECTION_DOMAIN_ADAPTERS.get(reading.domain) or (
        SELECTION_DOMAIN_ADAPTERS["generic"]
    )
    s = reading.stage_scores
    score_line = " / ".join(
        f"{_STAGE_KO[k]} {getattr(s, k)}"
        for k in (
            "opportunity", "application", "eligibility", "selection_support",
            "allocation", "preference_match", "execution", "adaptation",
        )
    )
    top_signals = sorted(reading.signals, key=lambda e: -e.strength)[:4]
    sig_lines = "; ".join(
        f"{adapter.signal_labels.get(e.signal.value, e.signal.value)}"
        f"={e.strength:.2f}({e.basis})"
        for e in top_signals
    )
    focus_ko = _STAGE_KO.get(
        _STAGE_SCORE_KEY[reading.focus_stage], reading.focus_stage.value
    )
    lottery = reading.external_uncertainty.level == "high"
    waitlist = (
        " 대기 순번·추가 선발·다음 회차로 이어지는 시나리오를 함께 제시하라."
        if reading.response_policy.allow_waitlist_scenario else ""
    )
    timing_line = ""
    if timing_windows:
        wins = " / ".join(f"{w.label}({w.reason})" for w in timing_windows)
        timing_line = (
            f"\n상대적으로 유리한 창(초점 단계 기준, 결과 보장 아님): {wins} — "
            "이 창은 확정 예언이 아니라 신호 유입의 상대 비교로만 서술하라."
        )
    odds_line = ""
    if reading.objective_odds is not None:
        odds_line = "\n" + _odds_line(reading.objective_odds)
    return (
        f"[선발·배치 풀이 — {adapter.label_ko}] 이 질문은 추첨·선발·배치형 사건이다. "
        f"질문 초점 단계: {focus_ko}. 아래는 엔진이 계산한 단계별 성립도(0~100)와 "
        "신호 근거다 — 초점 단계를 중심으로 답하되, '선발되는 흐름'과 '희망 조건 "
        "배치'는 서로 다른 사건이므로 반드시 분리해 서술하라.\n"
        f"단계 점수: {score_line}\n"
        f"주요 신호: {sig_lines}\n"
        f"선발 방식: {reading.mechanism.selection_mode} / 배치 방식: "
        f"{reading.mechanism.allocation_mode} / 외부 무작위성: "
        f"{_CAP_KO[reading.external_uncertainty.level]}"
        + timing_line
        + odds_line
        + "\n표현 규칙: ①당첨·탈락·합격을 단정하지 말 것(확률 % 표시 금지) — "
        f"확신 수준은 최대 '{_CAP_KO[reading.response_policy.confidence_cap]}' "
        "②상대적으로 유리한 시기·단계별 강약 비교는 허용 ③이동·충 신호는 당첨 "
        "근거가 아니라 실제 실행(입영·입주·등록) 신호로만 쓸 것 ④경쟁(비겁) 신호는 "
        "탈락 근거가 아니라 경쟁 환경의 강도로 서술할 것."
        + (
            " ⑤순수 추첨성이 강하므로 결과 예측 신뢰도가 낮음을 명시하고 '기회가 "
            "열려 있으나 결과 변수가 크다' 수준으로 표현할 것." if lottery else ""
        )
        + waitlist
        + "\n답변 형식: 결론(1~2문장) → 유리한 부분 → 변수 → 가능한 전개(조건 조정·"
        "다음 회차 포함) 순으로 짧게."
    )
