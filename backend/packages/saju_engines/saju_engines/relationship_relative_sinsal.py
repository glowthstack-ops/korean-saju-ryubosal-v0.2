"""12신살 상대위치법 (Relative Sinsal Relationship, P2, 2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §4. 기준 지지(년지=사회 관계 / 일지=친밀 관계)의 삼합국을
기준으로 상대 지지가 어느 12신살 위치에 놓이는지 계산한다. **A→B와 B→A를 모두 계산해 비대칭
체감**을 설명하며, 승패·서열이 아니라 관계 역학 경향으로만 쓴다. 점수·confidence·favorability·후보를
변경하지 않는다(explanation-first). 단일 글자살·일반 신살 카탈로그(`sinsal_catalog.py`)와 구분한다.

12신살 상대위치 매핑: base의 삼합국 → 겁살 = 고지(辰戌丑未)+1지지부터 12지지 연속 배정
(장성=왕지 · 지살=생지 · 화개=고지 검증).
"""

from __future__ import annotations

from saju_shared_types.enums import Branch
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.relative_sinsal import RelativeSinsalResult
from saju_shared_types.twelve_sinsal import BASE_MAPS, BRANCH_ORDER, TWELVE_SINSAL_ORDER

# 12지지 순서·12신살 표는 공용 SSOT(saju_shared_types.twelve_sinsal)에서 가져온다 —
# 방위(공간)·삼재(시간)·관계 세 소비처가 같은 표를 공유한다(2026-09-20). 기존 이름은 호환 별칭.
_BRANCH_ORDER: list[Branch] = list(BRANCH_ORDER)
_TWELVE_SINSAL: list[str] = list(TWELVE_SINSAL_ORDER)

# 12신살 → (노출 tier, 관계 역학 문구). internal은 노출하지 않는다(관계 낙인 방지).
_SINSAL_READING: dict[str, tuple[str, str]] = {
    "장성살": ("expose", "상대가 강하거나 주도성이 느껴지는 관계"),
    "반안살": ("expose", "안정감·기댈 곳·조력이 되는 관계"),
    "천살": ("expose", "상대가 크게 느껴지거나 부담·거리감이 생기기 쉬운 관계"),
    "년살": ("expose", "상대가 눈에 띄고 매력·표현이 살아나는 관계"),
    "망신살": ("expose", "관계에서 노출감·민감함·체면 이슈가 생기기 쉬운 위치"),
    "육해살": ("expose", "소모·지체·돌봄이 따르는 관계"),
    "화개살": ("expose", "고독·정신·예술 결이 겹치는 관계"),
    "지살": ("movement", "자리·터전의 결이 얽히는 관계"),
    "역마살": ("movement", "이동·활동의 결이 얽히는 관계"),
    "겁살": ("internal", ""),
    "재살": ("internal", ""),
    "월살": ("internal", ""),
}


# base 지지 → {target 지지: 12신살명} — 공용 표 별칭(테스트·외부 참조 호환).
_BASE_MAPS: dict[Branch, dict[Branch, str]] = BASE_MAPS


def get_relative_sinsal(base: Branch, target: Branch) -> RelativeSinsalResult:
    """기준 지지(base)의 삼합국에서 상대 지지(target)가 놓인 12신살 상대위치를 반환한다.

    Args:
        base: 기준 지지(년지=사회 / 일지=친밀).
        target: 상대 지지.

    Returns:
        RelativeSinsalResult — 12신살명·노출 tier·중립 관계 문구.
    """
    sinsal = _BASE_MAPS[base][target]
    tier, reading = _SINSAL_READING[sinsal]
    return RelativeSinsalResult(
        base_branch=base.value, target_branch=target.value,
        sinsal=sinsal, tier=tier, relationship_reading=reading,
    )


def relative_sinsal_lines(
    self_chart: ManseV2Result, partner_chart: ManseV2Result,
    self_label: str = "본인", partner_label: str = "상대",
) -> list[str]:
    """[12신살 상대위치] — 두 사람의 년지(사회)·일지(친밀) 기준 상대 12신살을 양방향으로 서술한다.

    노출 tier(expose·movement)만 문구화하고 internal(겁살·재살·월살)은 생략한다. 승패·서열이 아니라
    비대칭 관계 역학 경향으로만 서술하도록 안내한다(점수 미개입).

    Args:
        self_chart / partner_chart: 두 명식(pillars 필수).
        self_label / partner_label: 표시용 라벨.

    Returns:
        LLM 입력 지시문 목록(노출 대상 없으면 빈 목록).
    """
    sp, pp = self_chart.pillars, partner_chart.pillars
    if sp is None or pp is None or sp.day is None or pp.day is None:
        return []
    body: list[str] = []
    contexts = [("친밀(일지)", sp.day, pp.day)]
    if sp.year is not None and pp.year is not None:
        contexts.append(("사회(연지)", sp.year, pp.year))
    for ctx, self_pil, partner_pil in contexts:
        sb, pb = Branch(self_pil.branch), Branch(partner_pil.branch)
        for actor, subject, base, target in (
            (self_label, partner_label, sb, pb),   # self가 상대를 느끼는 결(base=self)
            (partner_label, self_label, pb, sb),   # 상대가 self를 느끼는 결
        ):
            r = get_relative_sinsal(base, target)
            if r.tier in ("expose", "movement") and r.relationship_reading:
                body.append(
                    f"- [{ctx}] {actor} → {subject} 체감: {r.sinsal} — {r.relationship_reading}"
                )
    if not body:
        return []
    return [
        "[12신살 상대위치 — 상대가 나에게 어떤 결로 느껴지는지(비대칭). 우열 판정이 아니라 관계 "
        "역학 경향으로만 서술하고 단정하지 말 것]",
        *body,
    ]
