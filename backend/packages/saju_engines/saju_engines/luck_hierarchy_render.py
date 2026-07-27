"""계층형 운 grounding 렌더 — 3단 뷰 (P1 — 2026-07-27 데굴님 확정).

  본문(narrative)   : 서술 가능한 관계의 압축 뷰. 클러스터 대표는 확정 문장, 보조는 한 줄.
  근거 부록(appendix): 성립이 확정되고 서술 가능한 관계 전체(RESOLVED + STRUCTURAL_ONLY).
  감사 SSOT          : LuckHierarchy 객체 자체(엔진 불일치·제외 사유 포함, 이 모듈 밖).

본문 선별은 개수순이 아니라 **축별 최소 보존**이다. 우호 신호만 남고 불리 강화·손실·
층간 충돌이 토큰 절약 과정에서 밀리면 다시 한쪽으로 치우친 서술이 나온다.
"""

from __future__ import annotations

from saju_shared_types.luck_hierarchy import (
    LAYER_KO,
    HierarchyInteraction,
    LuckHierarchy,
    ParticipantLayer,
)
from saju_shared_types.relation_semantics import (
    FormationState,
)

from .signal_polarity import classify_relation_polarity

#: 축별 본문 보존 상한(클러스터 대표는 별도로 항상 포함).
_MAX_PER_AXIS = 3


def _who(inter: HierarchyInteraction) -> str:
    """참여 글자를 층위와 함께 — '원국 시지 巳 + 세운 午 + 월운 未'."""
    return " + ".join(f"{LAYER_KO[p.layer]} {p.char}" for p in inter.participants)


def _name(inter: HierarchyInteraction) -> str:
    """표시 이름 — 축약 라벨이 성립 수준을 왜곡하지 않도록 부분 성립을 명시한다.

    '寅辰방합'이라고만 쓰면 완성된 방합처럼 읽힌다. canonical claim이 '국의 성립은
    아니다'라고 말하는데 라벨이 이를 되돌리면 안 된다.
    """
    label = inter.relation_label or inter.interaction_id.removeprefix("rel_")
    if inter.formation_state is FormationState.PARTIAL and "반합" not in label:
        return f"{label[:-2]} 부분 {label[-2:]}" if label.endswith("방합") else f"{label}(부분)"
    return label


#: 본문 축 — 구조적 효과(강화/묶임)와 **길흉 방향**을 함께 본다. 효과만 보고 묶으면
#: 기신 오행 강화가 '지원'으로, 이로운 글자가 묶이는 손실이 '완화'로 뒤집힌다
#: (2026-07-27 데굴님 지적 — 寅辰 木(기신) 강화를 '지원'으로 낸 결함).
AXIS_LABEL: dict[str, str] = {
    "favorable_activation": "우호 강화",
    "adverse_activation": "불리 강화·전환",
    "mitigation": "완화(불리 대상이 묶임)",
    "loss": "손실(이로운 대상이 묶임)",
    "mixed_binding": "혼재(이로운 쪽·불리한 쪽이 함께 묶임)",
    "neutral_activation": "중립 작용",
    "structural_tension": "구조적 긴장",
}
_AXIS_ORDER = (
    "favorable_activation", "adverse_activation", "mitigation",
    "loss", "mixed_binding", "neutral_activation", "structural_tension",
)


def _axis(inter: HierarchyInteraction) -> str:
    """관계 1건의 본문 축 — P3 점수와 **같은 분류기**가 정한 값을 그대로 쓴다.

    렌더용 분류기를 따로 두면 화면 설명과 점수가 다른 규칙으로 갈라진다.
    """
    return classify_relation_polarity(inter).narrative_axis


_LEVEL_TO_LAYER = {
    "day": ParticipantLayer.DAILY,
    "month": ParticipantLayer.MONTHLY,
    "year": ParticipantLayer.ANNUAL,
}


def _sort_key(inter: HierarchyInteraction, target: ParticipantLayer | None) -> tuple:
    """질문 대상 기간이 참여한 관계 > 층간 관계 > 사전 강도 순.

    대상 기간 우선을 넣지 않으면 상한에 걸렸을 때 정작 그날의 관계가 잘린다 —
    실측에서 寅亥合(일진 寅 + 원국 亥, 壬·甲 흉 제거)이 본문에서 빠졌다.
    """
    involves_target = target is not None and any(
        p.layer is target for p in inter.participants
    )
    return (
        0 if involves_target else 1,
        0 if inter.crosses_luck_layers else 1,
        -inter.base_intensity,
        inter.interaction_id,
    )


def render_hierarchy_narrative(h: LuckHierarchy) -> list[str]:
    """본문용 압축 뷰. 엔진 불일치 관계는 들어가지 않는다."""
    usable = [i for i in h.interactions if i.can_render_narrative()]
    if not usable:
        return []
    target = _LEVEL_TO_LAYER.get(h.requested_level)

    def key(i: HierarchyInteraction) -> tuple:
        return _sort_key(i, target)
    clustered: set[str] = {mid for c in h.clusters for mid in c.member_ids}

    lines = [
        "[상위 운 결합 — 엔진 확정값. 층위 표기 그대로 인용하고 재해석하지 말 것]",
        "활성 층위: " + " · ".join(
            f"{LAYER_KO[p.layer]} {p.ganji}" for p in h.active_layers
        ),
    ]
    # ① 클러스터 — 대표 1문장 + 보조 한 줄. 대표의 축 라벨을 그대로 쓴다.
    for cluster in h.clusters:
        primary = h.by_id(cluster.primary_interaction_id)
        if primary is None or not primary.can_render_narrative():
            continue
        lines.append(
            f"{AXIS_LABEL[_axis(primary)]}: {_name(primary)} [{_who(primary)}] "
            f"— {primary.canonical_claim}"
        )
        support = [
            s for sid in cluster.supporting_interaction_ids
            if (s := h.by_id(sid)) is not None and s.can_render_narrative()
            and _axis(s) == _axis(primary)  # 축이 다르면 같은 문장에 묶지 않는다
        ]
        if support:
            lines.append("  보조: " + " / ".join(
                f"{_name(s)} [{_who(s)}]" for s in support
            ))
    # ② 축별로 나머지를 채운다 — 개수순이 아니라 역할별 최소 보존.
    for axis in _AXIS_ORDER:
        rest = sorted(
            (i for i in usable
             if _axis(i) == axis and i.interaction_id not in clustered),
            key=key,
        )[:_MAX_PER_AXIS]
        for inter in rest:
            if axis == "structural_tension":
                lines.append(
                    f"{AXIS_LABEL[axis]}: {_name(inter)} [{_who(inter)}] — 성립 확정, "
                    "길흉 방향은 이번 판정에서 확정하지 않았으므로 유불리로 단정하지 말 것"
                )
            else:
                lines.append(
                    f"{AXIS_LABEL[axis]}: {_name(inter)} [{_who(inter)}] "
                    f"— {inter.canonical_claim}"
                )
    return lines


def render_hierarchy_appendix(h: LuckHierarchy) -> list[str]:
    """근거 부록 — 성립이 확정되고 서술 가능한 관계 전체.

    RESOLVED만 담으면 본문이 인용한 충·형·해(STRUCTURAL_ONLY)의 근거가 사라진다.
    엔진 불일치(ENGINE_CONFLICT)는 사용자 근거에서 제외하고 감사 SSOT에만 남긴다.
    """
    rows = [
        i for i in h.interactions
        if i.can_affect_volatility() and i.can_render_narrative()
    ]
    if not rows:
        return []
    target = _LEVEL_TO_LAYER.get(h.requested_level)
    lines = ["[운 관계 전체 근거 — 본문 서술의 출처]"]
    for inter in sorted(rows, key=lambda i: _sort_key(i, target)):
        state = (
            inter.canonical_claim
            if inter.canonical_claim
            else "구조적 긴장(길흉 방향 미판정)"
        )
        lines.append(f"- {_name(inter)} [{_who(inter)}] {state}")
    return lines


# ── P2 연·월·일 역할 요약 렌더 ────────────────────────────────────────────────

_STATE_KO = {
    "FAVORABLE": "우호", "ADVERSE": "불리", "NEUTRAL": "중립",
    "MIXED": "혼합", "UNKNOWN": "미상",
}
_BACKGROUND_KO = {
    "SUPPORT": "지원", "PRESSURE": "부담", "MIXED": "지원과 부담이 함께",
    "NEUTRAL": "중립", "NONE": "상위 층위 없음", "UNKNOWN": "판단 불가",
}
_LAYER_ROLE_KO = {
    "daewoon": "장기 배경", "annual": "연간 환경",
    "monthly": "활성 창구", "daily": "당일 촉발",
}
#: 요청 단위별 대상 표현 — 계산·서술 규칙은 같고 이 문구만 치환된다.
TARGET_UNIT_KO = {"day": "당일", "month": "이번 달", "year": "올해"}


def render_period_role_summary(summary) -> list[str]:
    """연·월·일 역할 요약 — 층별 천간·지지 근거를 모두 남긴다.

    종합 유형(enum)만 넘기면 '여러 운이 혼재하는 시기'로 다시 추상화되고, MIXED 층위의
    양방향 근거(乙 기신 / 未 용신)가 사라진다. 이번 사건의 핵심 교정이 그 지점이므로
    층별 상태를 항상 함께 전달한다(2026-07-27 데굴님 지적).
    """
    if summary is None or summary.target is None:
        return []
    unit = TARGET_UNIT_KO.get(summary.requested_level, "대상 기간")
    lines = [
        f"[운 계층 요약 — 엔진 확정값. 배경과 {unit}을 분리해 서술하고, 좋은 층위와 "
        "나쁜 층위를 평균 내 '중립'이라고 하지 말 것]"
    ]
    for row in [*summary.background, summary.target]:
        role = (
            f"{unit}(대상)" if row is summary.target
            else _LAYER_ROLE_KO.get(row.layer.value, "배경")
        )
        lines.append(
            f"{role}: {LAYER_KO[row.layer]} {row.ganji} — "
            f"천간 {row.ganji[0]}({row.stem_role or '역할 미상'}·"
            f"{_STATE_KO[row.stem_state.value]}) / "
            f"지지 {row.ganji[1]}({row.branch_role or '역할 미상'}·"
            f"{_STATE_KO[row.branch_state.value]}) → {_STATE_KO[row.state.value]}"
        )
    lines.append(
        f"배경 종합: {_BACKGROUND_KO.get(summary.background_state.value, '미상')} · "
        f"{unit} 상태: {_STATE_KO[summary.target_state.value]} "
        f"(분류 코드 {summary.hierarchy_summary.value} — 이 코드만 보고 서술하지 말고 "
        "위 층별 근거를 함께 쓸 것)"
    )
    return lines


# ── P3 슬롯 상태 렌더 (V2 ACTIVE일 때만 호출) ────────────────────────────────

_SLOT_STATUS_KO = {
    "FAVORABLE_DOMINANT": "유리 우세",
    "ADVERSE_DOMINANT": "불리 우세",
    "MIXED_BALANCED": "유리·불리 균형",
    "VOLATILITY_ONLY": "변동성만 있음(길흉 미판정)",
    "DIRECTION_UNRESOLVED": "양방향 효과 있음(크기 배분 보류)",
    "LOCAL_FAVORABLE_ONLY": "국소 유리(상위 운의 지지는 없음)",
    "LOCAL_ADVERSE_ONLY": "국소 불리(상위 운의 부정 지지는 없음)",
    "NEUTRAL": "중립",
    "NO_SIGNAL": "관련 신호 없음",
}
_CATEGORY_KO = {
    "work": "일·직업", "money": "재물", "relationship": "관계·연애",
    "health": "건강", "decision": "의사결정",
}


#: 상태별 사용자 문구 후보 — LLM이 그대로 써도 되는 표현(정책 문장 아님).
_USER_SUMMARY_HINT = {
    "FAVORABLE_DOMINANT": "유리한 신호가 우세",
    "ADVERSE_DOMINANT": "부담이 되는 신호가 우세",
    "MIXED_BALANCED": "유리·불리가 비슷하게 맞물림",
    "VOLATILITY_ONLY": "방향보다 변동·기복이 두드러짐",
    "DIRECTION_UNRESOLVED": "양쪽으로 작용하는 신호가 함께 있음",
    "LOCAL_FAVORABLE_ONLY": "정리·보완·부담 축소에 상대적으로 유리",
    "LOCAL_ADVERSE_ONLY": "국소적인 마찰·조정 사항이 늘어남",
    "NEUTRAL": "특별히 기울지 않음",
    "NO_SIGNAL": "관련 신호 없음",
}
#: 상태별 서술 정책 — **지시 영역 전용**. 사용자 문장 후보에 넣지 않는다.
_NARRATIVE_POLICY = {
    "LOCAL_FAVORABLE_ONLY": (
        "장기·지배적 호전으로 확대 금지(상위 운의 지지가 없음)"
    ),
    "LOCAL_ADVERSE_ONLY": (
        "장기 악화·지배적 불리 흐름으로 확대 금지(상위 운의 부정 지지가 없음). "
        "다만 주의점을 삭제하지도 말 것 — 범위를 제한하는 것이지 '문제 없음'이 아니다. "
        "무엇이 불편한가 · 어느 범위까지인가 · 무엇을 확인·조절할 것인가 순으로 서술"
    ),
    "VOLATILITY_ONLY": "'관련 신호가 없다'로 서술 금지",
    "DIRECTION_UNRESOLVED": "'관련 신호가 없다'로 서술 금지",
}


#: LOCAL_ADVERSE_ONLY의 도메인별 문구 후보 — 관계·직업·판단의 마찰 양상이 다르다.
_LOCAL_ADVERSE_HINT_BY_CATEGORY = {
    "relationship": "말의 뉘앙스·기대 차이로 마찰이 생기기 쉬움",
    "work": "일정·업무 분담·전달 과정에서 부담이 커질 수 있음",
    "decision": "피로하거나 조건을 일부 놓치기 쉬움",
    "money": "지출·조건 확인에서 어긋남이 생기기 쉬움",
    "health": "컨디션 기복과 피로가 두드러질 수 있음",
}


def render_v2_slot_status(scoring) -> list[str]:
    """분야별 상태 — 사용자 문구 후보와 서술 정책을 **분리해** 전달한다.

    정책 문장('~ 서술 금지')이 사용자 문구 후보와 같은 줄에 있으면 LLM이 그대로
    답변에 옮겨 적을 수 있다. 그래서 표시 라벨·문구 후보와 정책을 다른 항목으로
    나누고, 정책은 대괄호 지시 영역에만 둔다(2026-07-27 데굴님 지적).
    """
    rows = [
        (category, status) for category, status in sorted(scoring.slot_status.items())
        if status.narrative_eligible
    ]
    if not rows:
        return []
    lines = [
        "[분야별 상태 — 엔진 확정값. 아래 '문구 후보'만 사용자 문장에 쓰고, "
        "'서술 정책'은 지침일 뿐이니 답변에 옮겨 적지 말 것]"
    ]
    policies: list[str] = []
    for category, status in rows:
        key = status.status.value
        label = _SLOT_STATUS_KO.get(key, key)
        hint = _USER_SUMMARY_HINT.get(key, "")
        if key == "LOCAL_ADVERSE_ONLY":
            hint = _LOCAL_ADVERSE_HINT_BY_CATEGORY.get(category, hint)
        note = f"{_CATEGORY_KO.get(category, category)}: {label}"
        if hint:
            note += f" · 문구 후보: {hint}"
        if status.has_opposing_signals:
            note += " · 반대 방향 신호도 함께 있음"
        if status.has_unallocated_opposing_signals:
            note += " · 방향을 수치로 배분하지 않은 혼재 관계 있음"
        lines.append(note)
        policy = _NARRATIVE_POLICY.get(key)
        if policy:
            policies.append(f"- {_CATEGORY_KO.get(category, category)}: {policy}")
        if status.has_opposing_signals:
            policies.append(
                f"- {_CATEGORY_KO.get(category, category)}: "
                "'전적으로 불리·유리'로 단정 금지"
            )
    if policies:
        lines.append("[서술 정책 — 지침. 이 문장들을 답변에 그대로 쓰지 말 것]")
        lines += policies
    return lines
