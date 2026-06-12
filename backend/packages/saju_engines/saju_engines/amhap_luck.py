"""운(運) 암합 탐지 — 운 글자와 원국 지장간의 은밀한 합 (v2.2.1, 2026-06-12 사용자 자료).

운에서 오는 암합은 '드러나지 않은 결합' — 비밀 계약·숨은 연애·물밑 협력을 뜻한다.
두 형태를 탐지한다:
  ① 명암합(통근암합): 운 '천간' + 원국 지지의 '지장간'이 천간합 (예: 운 丁 + 원국 亥중 壬 → 정임합)
  ② 지장간암합: 운 '지지'의 지장간 + 원국 지지의 지장간이 천간합 (예: 운 寅 + 원국 丑)

각 암합에 궁성(연-대외/월-사회·직장/일-사생활·배우자/시-취미·자식·투자)과
십성(지장간이 일간에게 무엇인지)을 매칭한다. 일지 암합이 가장 비중이 크다.

암합은 보조 자료다(단독 결론 금지) — 이벤트 점수에 약하게만 기여하고, 풀이에서는
'물밑·비공식' 뉘앙스의 참고로만 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.constants import (
    STEM_COMBINATIONS,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

# 궁성 — 암합이 일어나는 무대(2026-06-12 사용자 자료).
_PALACE_STAGE = {
    "year": "연지(대외·먼 배경)",
    "month": "월지(사회·직장·부모형제)",
    "day": "일지(사생활·배우자) — 비중 가장 큼",
    "hour": "시지(취미·자식·투자)",
}
_PALACE_WEIGHT = {"day": 1.0, "month": 0.8, "hour": 0.7, "year": 0.6}


def _combines(a: str, b: str) -> bool:
    """두 천간이 천간합(五合)을 이루는가."""
    try:
        return frozenset({Stem(a), Stem(b)}) in STEM_COMBINATIONS
    except ValueError:
        return False


@dataclass(frozen=True)
class LuckAmhap:
    """운 암합 1건 — 보조 자료(단독 결론 금지)."""

    kind: str  # 'myeong'(명암합) | 'jijang'(지장간암합)
    palace: str  # year/month/day/hour
    stage: str  # 궁성 무대 설명
    luck_char: str  # 운에서 온 글자(천간 또는 지지)
    natal_hidden: str  # 합에 참여한 원국 지장간
    ten_god: str  # natal_hidden이 일간에게 갖는 십성
    weight: float  # 궁성 비중(0~1)

    def describe(self) -> str:
        """프롬프트용 한 줄(보조 표기)."""
        return (
            f"{self.luck_char}↔{self.natal_hidden} 암합({self.ten_god}) · "
            f"{self.stage}"
        )


def detect_luck_amhap(
    luck_stem: str, luck_branch: str, pillars: FourPillarsResult
) -> list[LuckAmhap]:
    """운 간지 1개와 원국 4지지 지장간의 암합 목록(보조 자료).

    Args:
        luck_stem, luck_branch: 운 간지(한자).
        pillars: 원국 4기둥(지장간·일간 보유).

    Returns:
        탐지된 운 암합 목록(없으면 빈 목록). 일지 우선 정렬.
    """
    day_master = Stem(pillars.day_master)
    try:
        luck_branch_hidden = [h[0].value for h in hidden_stems_for(Branch(luck_branch))]
    except ValueError:
        luck_branch_hidden = []

    out: list[LuckAmhap] = []
    for palace in ("year", "month", "day", "hour"):
        pillar = getattr(pillars, palace)
        if pillar is None:
            continue
        try:
            natal_hidden = [h[0].value for h in hidden_stems_for(Branch(pillar.branch))]
        except ValueError:
            continue
        stage = _PALACE_STAGE[palace]
        pw = _PALACE_WEIGHT[palace]
        # ① 명암합: 운 천간 + 원국 지장간.
        for nh in natal_hidden:
            if _combines(luck_stem, nh):
                out.append(LuckAmhap(
                    kind="myeong", palace=palace, stage=stage,
                    luck_char=luck_stem, natal_hidden=nh,
                    ten_god=str(ten_god(day_master, Stem(nh))), weight=pw,
                ))
        # ② 지장간암합: 운 지지 지장간 + 원국 지장간.
        for lh in luck_branch_hidden:
            for nh in natal_hidden:
                if _combines(lh, nh):
                    out.append(LuckAmhap(
                        kind="jijang", palace=palace, stage=stage,
                        luck_char=luck_branch, natal_hidden=nh,
                        ten_god=str(ten_god(day_master, Stem(nh))), weight=pw * 0.8,
                    ))
    # 일지(비중 큼) 우선, 명암합 우선.
    out.sort(key=lambda a: (-a.weight, a.kind != "myeong"))
    return out
