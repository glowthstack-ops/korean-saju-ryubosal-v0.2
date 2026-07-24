"""관계 상태 해소기 — P0-B3 (RELATIONSHIP_EVENT_SYSTEM 부록 C-3).

처리 단계 분리(쓰기 규칙 — 부록 C-3 §7):

  parse_relationship_utterance()   발화 → 시간성·단계·상태 힌트 (rules-first, LLM 미사용)
  decide_state_update()            갱신 가능 판정(CURRENT+명시+target 해소만 갱신)
  apply_state_update()             RelationshipStateStore 갱신(+프로필 충돌 표시)

갱신 금지: PAST / PLANNED(planned_stage만 보존) / HYPOTHETICAL / 제3자 발화 /
target 미해소 / 엔진 추론. **명식 추론으로 관계 상태를 추정하지 않는다.**
"전 연인과 연락 중"은 RECONCILING으로 자동 확정하지 않는다(재회는 연락 재개보다
강한 상태 — 별도 명시 필요).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from saju_shared_types.relationship_event import RelationshipCondition, RelationshipStage
from saju_shared_types.relationship_state import (
    RelationshipStateSource,
    RelationshipStateStore,
    ResolvedRelationshipState,
    TemporalStatus,
)

# ── 어휘(rules-first) ────────────────────────────────────────────────

_PARTNER_WORDS = r"(?:남자\s*친구|여자\s*친구|남친|여친|애인|연인)"
_SPOUSE_WORDS = r"(?:남편|아내|와이프|배우자|신랑|집사람)"

# 제3자 소유격 — 사용자 상태 갱신 금지(친구 남자친구 사주 등).
_THIRD_PARTY_RE = re.compile(
    r"(?:친구|동생|언니|누나|형|오빠|엄마|아빠|어머니|아버지|부모님|동료|지인|딸|아들)"
    rf"(?:의|네)?\s*(?:{_PARTNER_WORDS}|{_SPOUSE_WORDS})"
)
# 가정형 — "헤어지면 어떻게 될까", "이혼한다면", "결혼할 수 있을까?"(질문형 미래)
_HYPOTHETICAL_RE = re.compile(
    r"(?:[하지]면\s*(?:어떻|어떨|어찌)|다면|가정(?:하면|해서)"
    r"|(?:할|될|있을|가능할)\s*수\s*있을까|(?:할|될|일)까\s*\?)"
)
# 막연한 계획("언젠가·나중에 결혼할 예정") — planned 보존은 하되 신규 상태 생성 금지.
_VAGUE_PLAN_RE = re.compile(r"언젠가|나중에|때가\s*되면|여유가\s*되면")
# 계획형 — "결혼할 예정", "내년에 결혼하려고" ('준비 중'은 현재형 FORMALIZATION)
_PLANNED_RE = re.compile(r"(?:예정|하려고|할\s*거(?:야|예요)|하기로\s*했)")
# 과거형 — "남자친구가 있었어", "사귀었었"
_PAST_RE = re.compile(r"(?:있었|사귀었|만났었|였었)")
# 정정 — "…가 아니라/아니고 …", "사실은", "알고 보니"
_CORRECTION_RE = re.compile(r"(?:아니라|아니고|사실은|알고\s*보니)")
_EX_RE = re.compile(rf"(?:전\s*{_PARTNER_WORDS}|전남친|전여친|헤어진\s*(?:사람|{_PARTNER_WORDS}))")
_CONTACT_RE = re.compile(r"연락(?:만)?\s*(?:하고|중|해|하며)|연락을\s*(?:주고받|이어)")
_RECONCILE_RE = re.compile(r"재회|다시\s*(?:만나기로|사귀기로|합치기로)")

# (패턴, stage, condition, role) — 앞선 항목 우선. 정정 발화는 뒤 절만 본다.
_STAGE_RULES: list[tuple[re.Pattern[str], RelationshipStage, RelationshipCondition | None, str]] = [
    (re.compile(rf"{_SPOUSE_WORDS}[^.!?\n]{{0,12}}?별거|별거\s*중"),
     RelationshipStage.MARRIED, RelationshipCondition.SEPARATED, "spouse"),
    (re.compile(rf"{_PARTNER_WORDS}[^.!?\n]{{0,10}}?헤어졌|헤어졌"),
     RelationshipStage.NONE, RelationshipCondition.SEPARATED, "ex_partner"),
    (re.compile(r"약혼|결혼\s*준비\s*중|상견례[^.!?\n]{0,8}?(?:했|마쳤)"),
     RelationshipStage.FORMALIZATION, None, "partner"),
    (re.compile(r"결혼\s*(?:논의|이야기|얘기)\s*(?:중|하고)"),
     RelationshipStage.COMMITMENT, None, "partner"),
    (re.compile(rf"결혼했|기혼|{_SPOUSE_WORDS}"),
     RelationshipStage.MARRIED, None, "spouse"),
    (re.compile(rf"{_PARTNER_WORDS}[^.!?\n]{{0,8}}?(?:있|생겼)|사귀는\s*중|사귀고\s*있|연애\s*중"),
     RelationshipStage.DATING, None, "partner"),
    (re.compile(r"썸"), RelationshipStage.CONTACT, None, "partner"),
]
_MARITAL_OVERRIDE_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"이혼했"), "이혼"),
    (re.compile(r"사별했"), "사별"),
    (re.compile(r"재혼했"), "재혼"),
]


class RelationshipUtterance(BaseModel):
    """발화 파싱 결과(해소 전 힌트) — 상태 저장 아님."""

    quote: str
    temporal_status: TemporalStatus = TemporalStatus.CURRENT
    third_party: bool = False
    correction: bool = False
    # 한 발화에 서로 다른 대상 범주(배우자+전 연인 등)의 상태 서술이 공존 —
    # 단일 결과가 다른 대상에 오귀속될 수 있어 fail-closed(폐쇄 보완 §6).
    multiple_targets: bool = False
    # 막연한 계획(언젠가·나중에) — planned 보존은 가능하나 신규 상태 생성 금지(§4).
    planned_vague: bool = False
    target_role_hint: str | None = None
    stage_hint: RelationshipStage | None = None
    condition_hint: RelationshipCondition | None = None
    contact_hint: str | None = None
    planned_stage_hint: RelationshipStage | None = None
    marital_override_hint: str | None = None


class StateUpdateDecision(BaseModel):
    """갱신 판정 — 어떤 이유로 갱신했는지/안 했는지 항상 남긴다(계측 근거)."""

    update: bool
    reason: str  # ok | no_signal | third_party | hypothetical | past | planned_only |
    #              target_unresolved | ambiguous_multiple_targets | marital_override_only
    new_state: ResolvedRelationshipState | None = None
    planned_stage: RelationshipStage | None = None
    # 막연한 계획이면 planned 보존만 하고 신규 상태(COMMITMENT 함의) 생성 금지(§4).
    planned_may_create_state: bool = True
    marital_override: str | None = None


def parse_relationship_utterance(text: str) -> RelationshipUtterance | None:
    """관계 발화 rules-first 파싱 — 신호 없으면 None(보수적).

    정정 발화("있는 게 아니라 썸")는 정정 접속 이후의 절로 단계를 판정한다.
    """
    if not text:
        return None
    third = bool(_THIRD_PARTY_RE.search(text))
    correction = bool(_CORRECTION_RE.search(text))
    focus = text
    if correction:
        # 마지막 정정 표지 이후 절이 최종 사실이다.
        parts = _CORRECTION_RE.split(text)
        focus = parts[-1]

    # 다중 대상 감지(정정 발화 제외 — 정정은 같은 대상의 재서술) — 배우자·현재 연인·
    # 전 연인 중 2범주 이상이 상태 서술과 함께 등장하면 fail-closed 대상.
    if not correction and not third:
        categories = 0
        if re.search(rf"{_SPOUSE_WORDS}", text):
            categories += 1
        if _EX_RE.search(text):
            categories += 1
        # '전 남자친구'의 '남자친구' 중복 매칭 방지 — ex 표현 제거 후 현재 연인 검사.
        stripped = _EX_RE.sub("", text)
        if re.search(rf"{_PARTNER_WORDS}", stripped) or re.search(r"만나는\s*사람", stripped):
            categories += 1
        if categories >= 2:
            return RelationshipUtterance(
                quote=text.strip()[:120], multiple_targets=True,
            )

    is_ex = bool(_EX_RE.search(focus))
    marital: str | None = None
    for pat, value in _MARITAL_OVERRIDE_RE:
        if pat.search(focus):
            marital = value
            break

    stage: RelationshipStage | None = None
    condition: RelationshipCondition | None = None
    role: str | None = None
    if _RECONCILE_RE.search(focus):
        stage, condition, role = (
            RelationshipStage.CONTACT, RelationshipCondition.RECONCILING, "ex_partner",
        )
    elif is_ex:
        # 전 연인 언급 — 연락 중이면 CONTACT(재접촉)까지만. RECONCILING 자동 확정 금지.
        role = "ex_partner"
        if _CONTACT_RE.search(focus):
            stage = RelationshipStage.CONTACT
    else:
        for pat, st, cond, rl in _STAGE_RULES:
            if pat.search(focus):
                stage, condition, role = st, cond, rl
                break
    contact = "in_contact" if _CONTACT_RE.search(focus) else None
    if stage is None and contact is not None:
        stage = RelationshipStage.CONTACT  # 연락만 하는 상태 = 연락·재접촉 단계
    planned_marriage = bool(_PLANNED_RE.search(focus) and re.search(r"결혼|혼인", focus))
    if stage is None and condition is None and contact is None and marital is None \
            and not planned_marriage:
        # 상태 동사 없는 관계어 — 제3자('친구 남자친구 사주')·가정형('헤어지면 어떻게')은
        # 갱신 차단 사유를 계측에 남기기 위해 표식만 있는 발화로 반환한다.
        has_rel_word = bool(
            re.search(rf"{_PARTNER_WORDS}|{_SPOUSE_WORDS}|헤어지|이혼", text)
        )
        if has_rel_word and third:
            return RelationshipUtterance(quote=text.strip()[:120], third_party=True)
        if has_rel_word and _HYPOTHETICAL_RE.search(text):
            return RelationshipUtterance(
                quote=text.strip()[:120],
                temporal_status=TemporalStatus.HYPOTHETICAL,
            )
        return None

    # 시간성: 가정형 > 계획형 > 과거형 > 현재형. "헤어졌/이혼했"은 결과가 현재인 종료 발화.
    # '결혼 준비 중'(FORMALIZATION 현재형)에 '예정'이 함께 있어도 준비 사실이 우선.
    if _HYPOTHETICAL_RE.search(text):
        temporal = TemporalStatus.HYPOTHETICAL
    elif (planned_marriage or _PLANNED_RE.search(focus)) and marital is None \
            and stage not in (RelationshipStage.FORMALIZATION,):
        temporal = TemporalStatus.PLANNED
    elif _PAST_RE.search(focus):
        temporal = TemporalStatus.PAST
    else:
        temporal = TemporalStatus.CURRENT

    planned: RelationshipStage | None = None
    planned_vague = False
    if temporal is TemporalStatus.PLANNED:
        # "결혼할 예정" → 현 stage 승격 금지, planned로만 보존(부록 C-3 §7).
        planned = (
            RelationshipStage.MARRIED if re.search(r"결혼|혼인", focus) else stage
        )
        stage = None
        planned_vague = bool(_VAGUE_PLAN_RE.search(text))
    return RelationshipUtterance(
        quote=text.strip()[:120],
        temporal_status=temporal,
        third_party=third,
        correction=correction,
        planned_vague=planned_vague,
        target_role_hint=role,
        stage_hint=stage,
        condition_hint=condition,
        contact_hint=contact,
        planned_stage_hint=planned,
        marital_override_hint=marital,
    )


def decide_state_update(
    parsed: RelationshipUtterance | None,
    *,
    target_id: str | None,
    turn: int,
    source: RelationshipStateSource = RelationshipStateSource.QUESTION_EXPLICIT,
) -> StateUpdateDecision:
    """갱신 가능 판정 — CURRENT + user_explicit + target 해소만 상태를 만든다.

    marital override(이혼했어 등)는 전역이라 target 없이도 반환한다.
    """
    if parsed is None:
        return StateUpdateDecision(update=False, reason="no_signal")
    if parsed.third_party:
        return StateUpdateDecision(update=False, reason="third_party")
    if parsed.multiple_targets:
        # 한 발화에 배우자·현재 연인·전 연인 등 복수 대상 서술 — 자동 저장 금지(계측만).
        return StateUpdateDecision(update=False, reason="ambiguous_multiple_targets")
    if parsed.temporal_status is TemporalStatus.HYPOTHETICAL:
        return StateUpdateDecision(update=False, reason="hypothetical")
    if parsed.temporal_status is TemporalStatus.PAST:
        return StateUpdateDecision(update=False, reason="past")
    if parsed.temporal_status is TemporalStatus.PLANNED:
        # 계획은 현 stage를 바꾸지 않는다 — planned_stage만 전달("결혼 예정"≠MARRIED).
        return StateUpdateDecision(
            update=False, reason="planned_only",
            planned_stage=parsed.planned_stage_hint,
            planned_may_create_state=not parsed.planned_vague,
            marital_override=parsed.marital_override_hint,
        )
    if parsed.stage_hint is None and parsed.contact_hint is None:
        # 혼인 정정만 있는 발화(이혼했어) — 전역 override만.
        return StateUpdateDecision(
            update=False, reason="no_signal" if parsed.marital_override_hint is None
            else "marital_override_only",
            marital_override=parsed.marital_override_hint,
        )
    if target_id is None:
        return StateUpdateDecision(
            update=False, reason="target_unresolved",
            marital_override=parsed.marital_override_hint,
        )
    state = ResolvedRelationshipState(
        target_id=target_id,
        target_role=parsed.target_role_hint,
        stage=parsed.stage_hint or RelationshipStage.NONE,
        condition=parsed.condition_hint,
        contact_state=parsed.contact_hint,
        temporal_status=TemporalStatus.CURRENT,
        source=source,
        source_turn=turn,
        confidence="high",
    )
    return StateUpdateDecision(
        update=True, reason="ok", new_state=state,
        marital_override=parsed.marital_override_hint,
    )


def apply_state_update(
    store: RelationshipStateStore,
    decision: StateUpdateDecision,
    *,
    turn: int,
    target_id: str | None = None,
    profile_marital_status: str | None = None,
) -> bool:
    """결정 반영(store in-place 갱신). 반환값=프로필 충돌 여부(텔레메트리 근거).

    - planned_only: 기존/신규 target 상태의 planned_stage만 채운다(stage 불변).
    - marital_override: 전역 override 저장(프로필 자체는 자동 수정하지 않는다).
    """
    conflict = False
    if decision.marital_override:
        store.marital_status_override = decision.marital_override
        store.marital_status_source = RelationshipStateSource.QUESTION_EXPLICIT
        if profile_marital_status and profile_marital_status != decision.marital_override:
            conflict = True
    if decision.planned_stage is not None and target_id is not None:
        existing = store.target_states.get(target_id)
        if existing is not None:
            existing.planned_stage = decision.planned_stage
            store.last_resolved_turn = turn
        elif decision.planned_may_create_state:
            # 구체적 계획 + 기존 상태 없음 → 약속 존재 함의(COMMITMENT) + planned 보존.
            # 막연한 계획("언젠가 결혼할 예정")은 신규 상태를 만들지 않는다(§4).
            store.target_states[target_id] = ResolvedRelationshipState(
                target_id=target_id, target_role="partner",
                stage=RelationshipStage.COMMITMENT,
                planned_stage=decision.planned_stage,
                source=RelationshipStateSource.QUESTION_EXPLICIT, source_turn=turn,
                confidence="medium",
            )
            store.last_resolved_turn = turn
    if decision.update and decision.new_state is not None:
        st = decision.new_state
        if profile_marital_status and _conflicts_with_profile(st, profile_marital_status):
            st = st.model_copy(update={"profile_conflict": True})
            conflict = True
        store.target_states[st.target_id] = st
        store.last_resolved_turn = turn
    return conflict


def _conflicts_with_profile(st: ResolvedRelationshipState, marital: str) -> bool:
    """프로필 혼인 상태와 해소 상태의 명백한 충돌만 감지(보수)."""
    if marital in ("기혼", "재혼") and st.stage is RelationshipStage.NONE \
            and st.condition is RelationshipCondition.SEPARATED \
            and st.target_role == "ex_partner":
        return False  # 애인과의 이별은 혼인 상태와 무충돌일 수 있음 — 미판정
    if marital == "미혼" and st.stage is RelationshipStage.MARRIED:
        return True
    if marital in ("연애중",) and st.stage is RelationshipStage.NONE \
            and st.condition is RelationshipCondition.SEPARATED:
        return True  # 프로필=연애중인데 "헤어졌어"
    return False
