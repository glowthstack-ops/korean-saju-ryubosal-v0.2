"""상담 결론 arbiter — 엔진 evidence → 단계별 행동 지침 → 요약 태세 (P1, 2026-08-21).

3층 파이프라인:
  1) StageAssessor  : 후보의 구조 필드(활성/유불리/뉘앙스/검토월/게이트)를 단계별
                      평가로 분류. SSOT 매핑(EVENT_PROCESS_ROLE)이 있는 단계만 만든다.
  2) StageArbiter   : 승인된 truth table(T1~T7)로 stage_action_policy 산출.
  3) SummaryDeriver : 파생 요약(summary_stance) + 미지 단계 커버리지 플래그.

불변식은 saju_shared_types.counseling 모듈 docstring 참조(INV-A~G).
특히: 배경 운(luck_backdrop)은 이 모듈의 **어떤 판정에도 입력되지 않는다**(INV-B) —
주석 문자열로만 실려 서술 배경에 쓰인다. HOLD 는 event-local 차단 근거가 있을 때만(INV-F).

플래그: SAJU_COUNSELING_SEMANTICS_ENABLED (기본 OFF — .env.beta 주입, pytest 오염 방지).
OFF 면 블록·디렉티브가 전혀 붙지 않아 프롬프트 byte 불변이다.
"""

from __future__ import annotations

import os

from saju_shared_types.counseling import (
    CounselingSemantics,
    FrictionKind,
    FrictionMark,
    StageAction,
    StageAssessment,
    StageScope,
)
from saju_shared_types.event_taxonomy_v2 import EVENT_PROCESS_ROLE, EVENT_STAGE_TAGS
from saju_shared_types.llm_input import LlmEventCandidate, MonthOverviewRow


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "on")


COUNSELING_SEMANTICS_ENABLED = _env_flag("SAJU_COUNSELING_SEMANTICS_ENABLED")

# favorability 밴드 임계 — context_reducer._favorability_ko(±0.2)와 동일 기준.
_FAV_TH = 0.2
# activation 밴드 임계 — 기존 score_band(강 75/중 50)와 동일 구획.
_ACT_HIGH, _ACT_MODERATE = 75.0, 50.0

# EVENT_PROCESS_ROLE → 주 단계(SSOT 유래 재라벨링 — 신규 의미론 아님).
# transition/delay/conflict 는 단계가 아니라 직교 축이라 매핑하지 않는다(fail-closed).
_ROLE_TO_STAGE: dict[str, StageScope] = {
    "entry": StageScope.OPPORTUNITY,
    "initiation": StageScope.OPPORTUNITY,
    "agreement": StageScope.DECISION,
    "advancement": StageScope.DECISION,
    "production": StageScope.REALIZATION,
    "expansion": StageScope.REALIZATION,
    "movement": StageScope.REALIZATION,
    "exposure": StageScope.REALIZATION,
    "unexpected_gain": StageScope.REALIZATION,
}

# T3 차단형(blocking) 근거 — 성립 자체를 막는 게이트만. 비차단 불리(뉘앙스·검토월)는 T4.
_BLOCKING_CODES = ("GATE_business_start_no_wealth",)
# 결과축 불리 코드(outcome adverse 증거) — favorability 조정 전용으로 설계된 코드들.
_OUTCOME_ADVERSE_PREFIXES = ("EXAM_FAIL", "CAREER_EXIT_RISK")
# 당락 단정 금지 영역(절대 원칙 8) — DECISION 단계 WITHHELD + 요약 캡.
_COMPETITION_EVENT_KEYS = frozenset({"education_admission", "public_exposure", "legal_conflict"})

_LOW_LUCK_GRADES = ("강한 기신운", "기신운(부분)")

_STANCE_KO = {
    StageAction.PROCEED: "진행",
    StageAction.CONDITIONAL: "조건부 진행(조건 확인 후)",
    StageAction.HOLD: "보류",
    StageAction.UNKNOWN: "판단 재료 없음",
    StageAction.WITHHELD: "행동 지침 미산출(정책)",
}
_STAGE_KO = {
    StageScope.OPPORTUNITY: "기회",
    StageScope.PROCESS: "과정",
    StageScope.DECISION: "결정(수락·계약)",
    StageScope.REALIZATION: "실행",
    StageScope.OUTCOME: "실속·유지",
}
_ACT_KO = {"high": "높음", "moderate": "보통", "low": "낮음", "unknown": "판단 불가"}
_OUTCOME_KO = {
    "favorable": "유리",
    "workable": "무난(실속 확인 필요)",
    "mixed": "혼합(양측 근거 공존)",
    "weak": "약함(결실 불리 경향)",
    "adverse": "불리",
    "unknown": "판단 불가(근거 없음)",
}
_SUMMARY_KO = {
    "PROCEED": "진행에 무게",
    "PROCEED_WITH_CONDITIONS": "조건부 진행",
    "HOLD": "보류 권고",
    "UNAVAILABLE": "판단 재료 없음",
}


def _activation_band(c: LlmEventCandidate) -> str:
    if c.activation >= _ACT_HIGH:
        return "high"
    if c.activation >= _ACT_MODERATE:
        return "moderate"
    if c.activation > 0.0:
        return "low"
    return "unknown"


def _outcome_outlook(c: LlmEventCandidate) -> str:
    """결과 전망 — favorability 밴드 × 결실 뉘앙스 × 결과축 코드(승인 조합 규칙).

    INV-D: favorability 0.0 + 극성 중립 + 결과축 증거 없음 = unknown(중립·혼합 아님).
    """
    has_adverse_code = any(
        code.startswith(_OUTCOME_ADVERSE_PREFIXES) for code in c.evidence_path
    )
    if c.favorability <= -_FAV_TH or has_adverse_code:
        return "adverse"
    if c.favorability >= _FAV_TH:
        return "workable" if c.result_nuance == "leak" else "favorable"
    # 중립 대역 — 실증거가 있어야만 mixed/weak, 없으면 unknown(자동 폴백 금지).
    if c.quality == "mixed":
        return "mixed"
    if c.result_nuance == "unfavorable":
        return "weak"
    return "unknown"


def _frictions(c: LlmEventCandidate) -> list[FrictionMark]:
    """마찰 신호 수집 — direction/outcome 을 바꾸지 않는 직교 축(INV-G)."""
    marks: list[FrictionMark] = []
    if c.quality == "pressure":
        marks.append(FrictionMark(kind=FrictionKind.PRESSURE, stage=None, source="quality"))
    if c.quality == "conflict":
        marks.append(FrictionMark(kind=FrictionKind.CONFLICT, stage=None, source="quality"))
    if any(code.startswith("VOID_") for code in c.evidence_path):
        marks.append(FrictionMark(kind=FrictionKind.DELAY, stage=None, source="VOID_delay"))
    if c.review_month:
        marks.append(FrictionMark(
            kind=FrictionKind.CONDITION_DEFECT, stage=StageScope.DECISION, source="review_month",
        ))
    if c.result_nuance == "unfavorable":
        marks.append(FrictionMark(
            kind=FrictionKind.CONDITION_DEFECT, stage=StageScope.DECISION,
            source="ganji_nuance_unfavorable",
        ))
    return marks


def _assess_stages(c: LlmEventCandidate, outlook: str) -> list[StageAssessment]:
    """단계 평가 — SSOT(EVENT_PROCESS_ROLE) 유래 주 단계 + 결정/실속 축(뉘앙스 근거)."""
    stages: dict[StageScope, StageAssessment] = {}

    def _get(stage: StageScope) -> StageAssessment:
        if stage not in stages:
            stages[stage] = StageAssessment(stage=stage)
        return stages[stage]

    # 주 단계 — EVENT_STAGE_TAGS(P2-1, SSOT 유래)가 있으면 그 단계 집합을, 없으면
    # EVENT_PROCESS_ROLE 접힘을 쓴다. 사건 형성 자체는 극성이 아니라 neutral
    # (형성력은 activation 밴드가 전달). 실행·실속 단계는 결과 증거가 있을 때만
    # 방향을 부여한다 — 무근거 '실행 진행' 지침 방지(fail-closed).
    tag_stages: list[StageScope] = []
    for tag in EVENT_STAGE_TAGS.get(c.event_key, ()):
        try:
            tag_stages.append(StageScope(tag))
        except ValueError:
            continue
    if not tag_stages:
        role = EVENT_PROCESS_ROLE.get(c.event_key, "")
        primary = _ROLE_TO_STAGE.get(role)
        if primary is not None:
            tag_stages = [primary]
    for st in tag_stages:
        a = _get(st)
        a.evidence.append(f"stage_tag:{st.value}")
        if st in (StageScope.OPPORTUNITY, StageScope.PROCESS):
            a.direction = "neutral"
        elif st in (StageScope.REALIZATION, StageScope.OUTCOME):
            if outlook in ("favorable", "workable"):
                a.direction = "favorable"
            elif outlook in ("adverse", "weak"):
                a.direction = "adverse"
            elif outlook == "mixed":
                a.direction = "mixed"
            # outlook unknown → direction unknown 유지(정책 UNKNOWN — 서술 금지).
        # DECISION 태그는 평가 슬롯만 연다 — 방향은 아래 결정 블록이 증거로 정한다.

    # 과정 단계 — 경험 마찰(압박·갈등·지연)이 있으면 평가를 만들되 direction 은 중립 유지
    # (INV-G: 마찰은 유불리가 아니다).
    frictions = _frictions(c)
    process_marks = [m for m in frictions if m.stage is None]
    if process_marks:
        a = _get(StageScope.PROCESS)
        if a.direction == "unknown":
            a.direction = "neutral"
        a.frictions.extend(process_marks)
        a.evidence.extend(m.source for m in process_marks)

    # 결정 단계 — 결실 뉘앙스·검토월·결과축 증거가 있을 때만.
    decision_marks = [m for m in frictions if m.stage is StageScope.DECISION]
    has_outcome_evidence = outlook != "unknown"
    if decision_marks or has_outcome_evidence:
        a = _get(StageScope.DECISION)
        a.frictions.extend(decision_marks)
        a.evidence.extend(m.source for m in decision_marks)
        if c.result_nuance == "unfavorable" or outlook == "adverse":
            a.direction = "adverse"
        elif outlook in ("favorable", "workable"):
            a.direction = "favorable"
        elif outlook == "mixed":
            a.direction = "mixed"
        elif outlook == "weak":
            a.direction = "adverse"
        # outlook == unknown 이면서 marks 만 있는 경우 direction 은 unknown 유지.

    # 실속·유지 단계 — 길신 누설(leak)일 때만(실속 약화 근거).
    if c.result_nuance == "leak":
        a = _get(StageScope.OUTCOME)
        a.direction = "adverse"
        a.evidence.append("ganji_nuance_leak")

    return list(stages.values())


def _stage_action(a: StageAssessment, c: LlmEventCandidate) -> StageAction:
    """truth table T2~T7 — 단계 1개의 행동 지침(T1 도메인 캡은 상위에서)."""
    if a.direction == "unknown":
        return StageAction.UNKNOWN  # T2 — LLM 보충 금지
    if a.direction == "adverse":
        blocking = any(code in _BLOCKING_CODES for code in c.evidence_path)
        if blocking:
            return StageAction.HOLD  # T3 — event-local 차단 근거(INV-F)
        return StageAction.CONDITIONAL  # T4 — 비차단 불리(조건 확인 후)
    if a.direction == "mixed":
        return StageAction.CONDITIONAL  # T7
    if any(m.kind is FrictionKind.CONDITION_DEFECT for m in a.frictions):
        return StageAction.CONDITIONAL  # T5
    return StageAction.PROCEED  # T6 — delay/pressure 마찰은 PROCEED 를 깎지 않는다(INV-G)


def _summary(policy: dict[str, str], domain_cap: str) -> str:
    """파생 요약(INV-A) — 채워진 단계 중 최악 행동. 캡은 요약에도 적용."""
    if domain_cap == "competition":
        # 당락 단정 금지 영역(절대 원칙 8) — 지원 권유(PUSH형)도 회피 권유(HOLD형)도
        # 당락 예측의 우회 표현이 된다. 평가가 하나라도 있으면 '조건부 진행'(결과
        # 미단정·준비 조건 프레임)으로 고정한다(승인 설계 §도메인 캡).
        return "PROCEED_WITH_CONDITIONS" if policy else "UNAVAILABLE"
    actions = {
        v for v in policy.values()
        if v not in (StageAction.UNKNOWN.value, StageAction.WITHHELD.value)
    }
    if not actions:
        return "UNAVAILABLE"
    if StageAction.HOLD.value in actions:
        summary = "HOLD"
    elif StageAction.CONDITIONAL.value in actions:
        summary = "PROCEED_WITH_CONDITIONS"
    else:
        summary = "PROCEED"
    if domain_cap == "big_decision" and summary == "PROCEED":
        summary = "PROCEED_WITH_CONDITIONS"  # 결혼·이혼 — 조건부·권유형 상한
    return summary


def build_counseling(
    c: LlmEventCandidate,
    overview_rows: list[MonthOverviewRow] | None = None,
    *,
    competition: bool = False,
    big_decision: bool = False,
    health: bool = False,
    minor: bool = False,
) -> CounselingSemantics:
    """후보 1건 → 상담 결론 파생 판정. 점수·간지·기존 판정은 읽기만 한다(불변)."""
    if minor:
        # 미성년 — 서술 자체 금지 영역이 있어 stance 를 산출하지 않는다(설계 §3-3).
        return CounselingSemantics(
            event_key=str(c.event_key), event_ko=c.event_ko, period=c.period,
            summary_stance="UNAVAILABLE", domain_cap="minor",
        )
    outlook = _outcome_outlook(c)
    stages = _assess_stages(c, outlook)
    domain_cap = ""
    if competition or str(c.event_key) in _COMPETITION_EVENT_KEYS:
        domain_cap = "competition"
    elif big_decision:
        domain_cap = "big_decision"
    elif health:
        domain_cap = "health"

    policy: dict[str, str] = {}
    for a in stages:
        action = _stage_action(a, c)
        # T1 도메인 캡 — 결정 단계의 당락·확정형 지침 차단(절대 원칙 8).
        if domain_cap == "competition" and a.stage is StageScope.DECISION:
            action = StageAction.WITHHELD
        # 건강 — 보류/회피가 '치료를 미뤄라'로 읽히는 것 금지 → 조건부(확인 안내)로 캡.
        if domain_cap == "health" and action is StageAction.HOLD:
            action = StageAction.CONDITIONAL
        policy[a.stage.value] = action.value

    backdrop = ""
    for row in overview_rows or []:
        if row.period == c.period and row.luck_grade:
            low = " (배경 저점 — 행동 지침의 근거로 쓰지 말 것)" \
                if row.luck_grade in _LOW_LUCK_GRADES else ""
            backdrop = f"{row.period} 운 품질 {row.luck_grade}{low}"
            break

    assessed = {a.stage.value for a in stages}
    unknown_stages = [
        s.value for s in StageScope
        if s.value not in assessed or policy.get(s.value) == StageAction.UNKNOWN.value
    ]
    return CounselingSemantics(
        event_key=str(c.event_key), event_ko=c.event_ko, period=c.period,
        activation_band=_activation_band(c),
        outcome_outlook=outlook,
        stages=stages,
        stage_action_policy=policy,
        summary_stance=_summary(policy, domain_cap),
        luck_backdrop=backdrop,
        domain_cap=domain_cap,
        unknown_stages=unknown_stages,
    )


def counseling_block_lines(sem: CounselingSemantics) -> list[str]:
    """프롬프트 블록 직렬화 — 엔진 확정값만, LLM 재판정 금지 계약 동반."""
    if sem.summary_stance == "UNAVAILABLE" and not sem.stages:
        return []  # 판단 재료 전무 — 블록 자체를 내지 않는다(빈 슬롯 침묵)
    lines = [
        "[상담 결론 — 엔진 파생 판정. 아래 값만 사용하고 임의로 재판정·보충하지 말 것]",
        f"대상 사건: {sem.event_ko or sem.event_key} @ {sem.period}",
        (
            f"활성(사건 형성력): {_ACT_KO.get(sem.activation_band, sem.activation_band)}"
            f" · 결과 전망: {_OUTCOME_KO.get(sem.outcome_outlook, sem.outcome_outlook)}"
            " — 두 축은 별개다(활성 높음≠결과 좋음, 하나의 좋다/나쁘다로 합치지 말 것)"
        ),
    ]
    if sem.stage_action_policy:
        parts = []
        for stage in StageScope:
            act = sem.stage_action_policy.get(stage.value)
            if act is None or act == StageAction.UNKNOWN.value:
                continue
            if act == StageAction.WITHHELD.value:
                parts.append(f"{_STAGE_KO[stage]}: 당락·확정 지침 미산출(단정 금지 영역)")
            else:
                parts.append(f"{_STAGE_KO[stage]}: {_STANCE_KO[StageAction(act)]}")
        if parts:
            lines.append("단계별 행동 지침: " + " / ".join(parts))
    frics = [m for a in sem.stages for m in a.frictions]
    if frics:
        fric_ko = {
            FrictionKind.DELAY: "지연(시점 이연 — 실패 신호 아님)",
            FrictionKind.PRESSURE: "압박(과정 경험 — 결과 실패 아님)",
            FrictionKind.CONFLICT: "마찰(과정 경험)",
            FrictionKind.CONDITION_DEFECT: "조건·유지력 하자(확인 대상)",
        }
        uniq = list(dict.fromkeys(fric_ko[m.kind] for m in frics))
        lines.append("마찰 신호: " + " / ".join(uniq))
    lines.append(f"요약 태세: {_SUMMARY_KO.get(sem.summary_stance, sem.summary_stance)}")
    if sem.unknown_stages:
        missing = " · ".join(_STAGE_KO[StageScope(s)] for s in sem.unknown_stages)
        lines.append(f"판단 재료 없는 단계: {missing} — 이 단계의 행동·전망을 지어내지 말 것")
    if sem.luck_backdrop:
        lines.append(f"배경 운 맥락(서술 배경 전용): {sem.luck_backdrop}")
    lines.append(
        "[상담 서술 계약] 답변에 ①무엇이 움직이는지 ②단계별로 어디가 힘들고 어디가 "
        "수월한지 ③그럼에도 결과 전망 ④단계별 행동(위 지침 그대로)을 모두 담아라. "
        "마찰(지연·압박)을 결과 실패로 번역하지 말고, 위 블록에 없는 단계·행동·전망을 "
        "만들지 마라. 요약 태세는 결론 문단 한 곳에서만 밝힌다."
    )
    return lines
