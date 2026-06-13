"""두 명식 궁합(宮合) 엔진 — 관계운 상대(궁합) 모드.

확정 신호 세트(2026-06-14 사용자 승인): **일주 상호작용**(일간 천간합 / 일지 육합·충·형·파·해·
복음), **십성 관계**(본인↔상대 일간 십성), **용신 상호보완**(상대 오행이 본인 용·희신을 채우는가
vs 기·구신을 강화하는가). 모두 엔진이 계산한 사실이며 LLM은 서술만 한다(CLAUDE.md 1조).

방향(보완/마찰/중립) 배정과 전반 톤은 reviewed:false 초안 — 전문가 감수 전 가중·판정 미보장
(CLAUDE.md 9·10). 관계 신살 교차는 본 세트에서 제외(사용자 확정).
"""

from __future__ import annotations

from saju_shared_types.compatibility import (
    CompatDirection,
    CompatibilityReport,
    CompatSignal,
    CompatSignalKind,
)
from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.llm_input import UsefulGods
from saju_shared_types.manse_result import ManseV2Result

# 십성별 관계 작용 방향(reviewed:false). 정관·정재·정인·식신=안정/생조 → 보완,
# 편관·상관·겁재=긴장/소모 → 마찰, 비견·편재·편인=중립.
_TEN_GOD_DIRECTION: dict[str, CompatDirection] = {
    "정관": CompatDirection.HARMONY,
    "정재": CompatDirection.HARMONY,
    "정인": CompatDirection.HARMONY,
    "식신": CompatDirection.HARMONY,
    "편관": CompatDirection.FRICTION,
    "상관": CompatDirection.FRICTION,
    "겁재": CompatDirection.FRICTION,
    "비견": CompatDirection.NEUTRAL,
    "편재": CompatDirection.NEUTRAL,
    "편인": CompatDirection.NEUTRAL,
}


def _is_punishment(a: Branch, b: Branch) -> bool:
    """두 지지가 형(刑) 관계인지 — 삼형 부분쌍 또는 무례지형(子卯)."""
    if frozenset({a, b}) in PUNISHMENT_MUTUAL:
        return True
    return any({a, b} <= triple for triple in PUNISHMENT_TRIPLES if a != b)


def _day_branch_signal(a: Branch, b: Branch) -> CompatSignal | None:
    """본인·상대 일지 사이의 합충형파해·복음 신호(우선순위: 합>충>형>파>해)."""
    pair = frozenset({a, b})
    elem = SIX_COMBINATIONS.get(pair)
    if elem is not None:
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_SIX, label="일지 육합",
            detail=f"본인 일지 {a.value} ↔ 상대 일지 {b.value} 육합(化{elem.value})",
            direction=CompatDirection.HARMONY,
        )
    if pair in BRANCH_CLASHES:
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_CLASH, label="일지 충",
            detail=f"본인 일지 {a.value} ↔ 상대 일지 {b.value} 충(沖)",
            direction=CompatDirection.FRICTION,
        )
    if a == b:
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_DUPLICATE, label="일지 복음",
            detail=f"본인·상대 일지가 같은 {a.value}(복음) — 닮음과 동시에 자기투영",
            direction=(
                CompatDirection.FRICTION if a in SELF_PUNISHMENT
                else CompatDirection.NEUTRAL
            ),
        )
    if _is_punishment(a, b):
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_PUNISH, label="일지 형",
            detail=f"본인 일지 {a.value} ↔ 상대 일지 {b.value} 형(刑)",
            direction=CompatDirection.FRICTION,
        )
    if pair in BRANCH_BREAKS:
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_BREAK, label="일지 파",
            detail=f"본인 일지 {a.value} ↔ 상대 일지 {b.value} 파(破)",
            direction=CompatDirection.FRICTION,
        )
    if pair in BRANCH_HARMS:
        return CompatSignal(
            kind=CompatSignalKind.DAY_BRANCH_HARM, label="일지 해",
            detail=f"본인 일지 {a.value} ↔ 상대 일지 {b.value} 해(害)",
            direction=CompatDirection.FRICTION,
        )
    return None


def _yongsin_signals(
    self_dm: Stem, partner_dm: Stem,
    self_useful: UsefulGods, partner_useful: UsefulGods,
) -> list[CompatSignal]:
    """상대 일간 오행이 본인 용·희신/기·구신에 해당하는지(양방향)."""
    out: list[CompatSignal] = []
    pairs = [
        (partner_dm, self_useful, "상대", "본인"),
        (self_dm, partner_useful, "본인", "상대"),
    ]
    for dm, useful, giver, taker in pairs:
        elem = STEM_ELEMENT[dm].value
        if elem in set(useful.yongsin) | set(useful.heesin):
            out.append(CompatSignal(
                kind=CompatSignalKind.YONGSIN_SUPPORT, label="용신 보완",
                detail=f"{giver} 일간 오행 {elem}이(가) {taker}의 용·희신을 채워줌",
                direction=CompatDirection.HARMONY,
            ))
        elif elem in set(useful.gisin) | set(useful.gusin):
            out.append(CompatSignal(
                kind=CompatSignalKind.YONGSIN_BURDEN, label="기신 강화",
                detail=f"{giver} 일간 오행 {elem}이(가) {taker}의 기·구신을 키움",
                direction=CompatDirection.FRICTION,
            ))
    return out


def _summary(harmony: int, friction: int) -> str:
    """보완/마찰 카운트 기반 전반 톤(reviewed:false 휴리스틱)."""
    if harmony >= friction + 2:
        return "상호 보완이 우세한 조합 — 서로를 채워주는 신호가 더 많습니다."
    if friction >= harmony + 2:
        return "마찰 요소가 더 두드러지는 조합 — 함께 다듬어갈 노력이 필요합니다."
    return "보완과 마찰이 함께 있는 조합 — 강점은 살리고 마찰점은 대화로 관리할 영역입니다."


def analyze_compatibility(
    self_result: ManseV2Result,
    partner_result: ManseV2Result,
    self_useful: UsefulGods,
    partner_useful: UsefulGods,
    *,
    self_label: str = "본인",
    partner_label: str = "상대",
) -> CompatibilityReport | None:
    """원국A↔원국B 궁합 신호(일주·십성·용신)를 계산한다.

    Args:
        self_result: 상담자(본인) 만세 결과.
        partner_result: 상대 만세 결과.
        self_useful / partner_useful: 각자의 용희기구한(BirthChartSummary.useful_gods).
        self_label / partner_label: 표시용 라벨.

    Returns:
        CompatibilityReport. 어느 한쪽 명식(pillars)이 없으면 None.
    """
    if self_result.pillars is None or partner_result.pillars is None:
        return None
    self_dm = Stem(self_result.pillars.day_master)
    partner_dm = Stem(partner_result.pillars.day_master)
    self_branch = Branch(self_result.pillars.day.branch)
    partner_branch = Branch(partner_result.pillars.day.branch)

    signals: list[CompatSignal] = []

    # 1) 일간 천간합.
    stem_elem = STEM_COMBINATIONS.get(frozenset({self_dm, partner_dm}))
    if stem_elem is not None and self_dm != partner_dm:
        signals.append(CompatSignal(
            kind=CompatSignalKind.DAY_STEM_COMBINE, label="일간 천간합",
            detail=f"본인 일간 {self_dm.value} ↔ 상대 일간 "
                   f"{partner_dm.value} 천간합(化{stem_elem.value})",
            direction=CompatDirection.HARMONY,
        ))

    # 2) 일지 상호작용.
    branch_sig = _day_branch_signal(self_branch, partner_branch)
    if branch_sig is not None:
        signals.append(branch_sig)

    # 3) 십성 관계(양방향).
    tg_to_partner = ten_god(self_dm, partner_dm).value
    tg_to_self = ten_god(partner_dm, self_dm).value
    signals.append(CompatSignal(
        kind=CompatSignalKind.TEN_GOD_TO_PARTNER, label="상대의 십성",
        detail=f"{self_label} 일간 기준 {partner_label}은(는) {tg_to_partner}",
        direction=_TEN_GOD_DIRECTION.get(tg_to_partner, CompatDirection.NEUTRAL),
    ))
    signals.append(CompatSignal(
        kind=CompatSignalKind.TEN_GOD_TO_SELF, label="나의 십성",
        detail=f"{partner_label} 일간 기준 {self_label}은(는) {tg_to_self}",
        direction=_TEN_GOD_DIRECTION.get(tg_to_self, CompatDirection.NEUTRAL),
    ))

    # 4) 용신 상호보완.
    signals += _yongsin_signals(self_dm, partner_dm, self_useful, partner_useful)

    harmony = sum(1 for s in signals if s.direction is CompatDirection.HARMONY)
    friction = sum(1 for s in signals if s.direction is CompatDirection.FRICTION)
    return CompatibilityReport(
        self_label=self_label,
        partner_label=partner_label,
        self_day=self_result.pillars.day.ganji,
        partner_day=partner_result.pillars.day.ganji,
        signals=signals,
        harmony_count=harmony,
        friction_count=friction,
        summary=_summary(harmony, friction),
    )


def compatibility_lines(report: CompatibilityReport) -> list[str]:
    """궁합 리포트를 LLM 입력 블록으로 직렬화(방향 태그 포함, 사실만)."""
    out = [
        f"[궁합 신호 — 엔진 계산값, {report.self_label} {report.self_day} ↔ "
        f"{report.partner_label} {report.partner_day}]",
        f"보완 {report.harmony_count} · 마찰 {report.friction_count} · {report.summary}",
    ]
    for s in report.signals:
        out.append(f"  - [{s.direction.value}] {s.label}: {s.detail}")
    return out
