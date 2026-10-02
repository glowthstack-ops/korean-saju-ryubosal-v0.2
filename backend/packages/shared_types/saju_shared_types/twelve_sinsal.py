"""12신살(十二神殺) 삼합국 상대위치 표 + 삼재(三災) 단계 — 공용 원천 규칙(SSOT).

기준 지지(연지·일지 등)의 삼합국에서 고지(辰戌丑未 멤버) 다음 지지를 겁살로 놓고
子→亥 순서로 12신살을 순회한다. 삼합 3멤버는 같은 표를 공유한다.

| 삼합국 | 겁 | 재 | 천 | 지 | 년 | 월 | 망신 | 장성 | 반안 | 역마 | 육해 | 화개 |
|--------|----|----|----|----|----|----|------|------|------|------|------|------|
| 寅午戌 | 亥 | 子 | 丑 | 寅 | 卯 | 辰 | 巳   | 午   | 未   | 申   | 酉   | 戌   |
| 巳酉丑 | 寅 | 卯 | 辰 | 巳 | 午 | 未 | 申   | 酉   | 戌   | 亥   | 子   | 丑   |
| 申子辰 | 巳 | 午 | 未 | 申 | 酉 | 戌 | 亥   | 子   | 丑   | 寅   | 卯   | 辰   |
| 亥卯未 | 申 | 酉 | 戌 | 亥 | 子 | 丑 | 寅   | 卯   | 辰   | 巳   | 午   | 未   |

이 표 하나를 세 소비처가 공유한다(2026-09-20 데굴님 결정 — 표 불일치 원천 차단):
- 공간 축: 출생 연지 기준 12방위 신살(`saju_engines.sinsal_direction`).
- 시간 축: 세운 지지 기준 삼재 단계 — 역마살=들삼재 / 육해살=눌삼재 / 화개살=날삼재.
- 관계 축: 상대 지지의 12신살 상대위치(`saju_engines.relationship_relative_sinsal`).

명칭 표준은 **년살(年殺, 도화살)** 이다 — '연살' 표기는 쓰지 않는다(2026-09-20 정규화).
삼재는 흉운 점수가 아니라 12신살의 3년짜리 시간 상태(sequence)다. 점수 파이프라인에
넣지 않고 맥락 신호로만 쓴다(docs/18 §4).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .constants import THREE_HARMONY
from .enums import Branch

#: 12지지 표준 순서(子→亥).
BRANCH_ORDER: tuple[Branch, ...] = (
    Branch.JA, Branch.CHUK, Branch.IN, Branch.MYO, Branch.JIN, Branch.SA,
    Branch.O, Branch.MI, Branch.SIN, Branch.YU, Branch.SUL, Branch.HAE,
)

#: 12신살 표준 순서(겁살→화개살). 년살은 '연살'이 아니라 '년살'로 고정한다.
TWELVE_SINSAL_ORDER: tuple[str, ...] = (
    "겁살", "재살", "천살", "지살", "년살", "월살",
    "망신살", "장성살", "반안살", "역마살", "육해살", "화개살",
)

#: 한자 표기(사용자 노출 병기용).
TWELVE_SINSAL_HANJA: dict[str, str] = {
    "겁살": "劫殺", "재살": "災殺", "천살": "天殺", "지살": "地殺", "년살": "年殺",
    "월살": "月殺", "망신살": "亡身殺", "장성살": "將星殺", "반안살": "攀鞍殺",
    "역마살": "驛馬殺", "육해살": "六害殺", "화개살": "華蓋殺",
}

#: 통용 별칭 — 년살은 도화살, 재살은 수옥살로도 불린다(서비스 노출은 병기).
TWELVE_SINSAL_ALIAS: dict[str, str] = {"년살": "도화살", "재살": "수옥살"}

_GOJI = {Branch.JIN, Branch.SUL, Branch.CHUK, Branch.MI}


def _build_base_maps() -> dict[Branch, dict[Branch, str]]:
    """THREE_HARMONY(멤버, 합화오행, 왕지)에서 기준 지지 → {대상 지지: 12신살명} 표를 만든다."""
    maps: dict[Branch, dict[Branch, str]] = {}
    for members, _elem, _wangji in THREE_HARMONY:
        goji = next(b for b in members if b in _GOJI)
        start = (BRANCH_ORDER.index(goji) + 1) % 12
        table = {BRANCH_ORDER[(start + k) % 12]: TWELVE_SINSAL_ORDER[k] for k in range(12)}
        for base in members:
            maps[base] = table
    return maps


#: 기준 지지 → {대상 지지: 12신살명}. 삼합 3멤버는 같은 dict 객체를 공유한다.
BASE_MAPS: dict[Branch, dict[Branch, str]] = _build_base_maps()


def trine_group_label(base: Branch) -> str:
    """기준 지지가 속한 삼합국 라벨(예: 申 → '申子辰'). 표기 순서는 생지·왕지·고지."""
    for members, _elem, wangji in THREE_HARMONY:
        if base in members:
            goji = next(b for b in members if b in _GOJI)
            saengji = next(b for b in members if b not in (wangji, goji))
            return f"{saengji}{wangji}{goji}"
    raise ValueError(f"삼합국을 찾을 수 없는 지지: {base}")


def relative_twelve_sinsal(base: Branch, target: Branch) -> str:
    """기준 지지(base)의 삼합국에서 대상 지지(target)가 놓인 12신살명을 반환한다."""
    return BASE_MAPS[base][target]


def branch_of_sinsal(base: Branch, sinsal: str) -> Branch:
    """기준 지지의 삼합국에서 해당 12신살이 놓이는 지지(역조회)."""
    for branch, name in BASE_MAPS[base].items():
        if name == sinsal:
            return branch
    raise ValueError(f"알 수 없는 12신살명: {sinsal}")


# ── 삼재(三災) ────────────────────────────────────────────────────────────────


class SamjaeStage(StrEnum):
    """삼재 3단계 — 내부 enum. 사용자 노출은 들삼재/눌삼재/날삼재 한글 라벨을 쓴다."""

    ENTER = "enter"  # 들삼재 = 역마살 세운
    STAY = "stay"  # 눌삼재 = 육해살 세운
    EXIT = "exit"  # 날삼재 = 화개살 세운


#: 12신살 → 삼재 단계. 역·육·화 3개만 삼재이며 나머지는 해당 없음(None).
SAMJAE_BY_SINSAL: dict[str, SamjaeStage] = {
    "역마살": SamjaeStage.ENTER,
    "육해살": SamjaeStage.STAY,
    "화개살": SamjaeStage.EXIT,
}

SAMJAE_LABEL_KO: dict[SamjaeStage, str] = {
    SamjaeStage.ENTER: "들삼재",
    SamjaeStage.STAY: "눌삼재",
    SamjaeStage.EXIT: "날삼재",
}

#: 단계별 핵심 신호(맥락 신호 전용 — 흉운 점수 아님). 사전(docs/18 §4)과 동일 문구.
SAMJAE_THEME_KO: dict[SamjaeStage, str] = {
    SamjaeStage.ENTER: "변화의 시작 — 진입·이동·환경 전환",
    SamjaeStage.STAY: "변화 과정의 마찰과 적응 — 얽힘·조정·피로",
    SamjaeStage.EXIT: "수렴·정리·마무리 — 내면화·정착",
}


class SamjaeQuality(StrEnum):
    """삼재 작용 품질(quality) — 진행 단계(stage)와 직교하는 축(docs/18 §4-2).

    복(bok)=삼재 변화가 명식에 유리하게 작용할 조건이 우세 / 평(normal)=방향성 약함·혼재 /
    악(ak)=삼재 변화와 불리 신호가 중첩. '복=대길'·'악=사고 확정'이 아니다.
    """

    BOK = "bok"
    NORMAL = "normal"
    AK = "ak"


SAMJAE_QUALITY_LABEL_KO: dict[SamjaeQuality, str] = {
    SamjaeQuality.BOK: "복삼재",
    SamjaeQuality.NORMAL: "평삼재",
    SamjaeQuality.AK: "악삼재",
}


class SamjaeEvidence(BaseModel):
    """복/평/악 판정 근거 1건 — LLM이 '삼재인데 왜 좋다고 하나'에 답할 재료.

    signal은 내부 신호명(annual_luck/daewoon_luck/clash_note/ten_god_balance/event_direction/
    alignment)이며 사용자 문장에는 note(한글)만 쓴다.
    """

    signal: str
    effect: Literal["positive", "negative", "neutral"]
    contribution: float  # quality_score 기여분(부호 포함) — 내부 수치, 프롬프트 미노출
    note: str  # 한글 근거 문구(기존 엔진 라벨 재사용)


class SamjaeDomainGrade(BaseModel):
    """도메인별 삼재 작용 등급 — 그 해 사건 후보의 길흉 방향 합성(후보 있는 도메인만)."""

    domain: str  # career/wealth/relationship/relocation/health/education(EVENT_DOMAIN 어휘)
    domain_ko: str
    grade: Literal["favorable", "mixed", "caution"]
    net: float  # (유리 점수합 − 불리 점수합) / 전체합 ∈ [-1, 1]


class SamjaeInfo(BaseModel):
    """세운 1건의 삼재 상태 — LuckPillar(period_type=year) 카드·프롬프트 표시용.

    stage(들/눌/날)는 12신살 표에서 결정론적으로 나오고, quality(복/평/악)·strength·overlap은
    `saju_engines.samjae_quality`가 기존 운 판정값을 합성해 채운다(없으면 None — 하위호환).

    Attributes:
        stage: 삼재 단계(enter/stay/exit).
        label_ko: 들삼재/눌삼재/날삼재.
        sinsal: 근거 12신살명(역마살/육해살/화개살).
        sequence_index: 3년 흐름 내 순번(1~3).
        theme_ko: 단계 핵심 신호 한 줄(맥락 신호 — 길흉 판정 아님).
        basis: 산출 근거(출생 연지 삼합국 + 세운 지지). 입춘 기준 세운과 동일 경계.
        quality: 복/평/악(미평가=None).
        quality_label: 복삼재/평삼재/악삼재.
        quality_score: −1~+1 합성 점수(서비스 캘리브레이션 상수 기반 — 명리 수치 아님).
        strength: 작용 강도 0~1, strength_label: 약/중/강.
        stage_quality_phrase: 단계×품질 9칸 표현(사전).
        evidence: 판정 근거 목록.
        domains: 도메인별 등급(후보 있는 도메인만).
        overlap: 겹삼재 종류(daewoon=대운 지지도 삼재권 / natal_clash=세운 지지↔원국 지지 충).
        overlap_label: 겹삼재 한글 라벨(없으면 None).
        event_signal_included: 사건 후보 항이 합성에 포함됐는가 — **내부 플래그**, 프롬프트·
            화면 문구에 노출하지 않는다(2026-09-20 데굴님 지시).
    """

    stage: SamjaeStage
    label_ko: str
    sinsal: str
    sequence_index: int
    theme_ko: str
    basis: str
    quality: SamjaeQuality | None = None
    quality_label: str | None = None
    quality_score: float | None = None
    strength: float | None = None
    strength_label: str | None = None
    stage_quality_phrase: str | None = None
    evidence: list[SamjaeEvidence] = Field(default_factory=list)
    domains: list[SamjaeDomainGrade] = Field(default_factory=list)
    overlap: list[str] = Field(default_factory=list)
    overlap_label: str | None = None
    event_signal_included: bool = False


def samjae_for(year_branch: Branch, transit_branch: Branch) -> SamjaeInfo | None:
    """출생 연지 삼합국 기준으로 세운 지지가 삼재 3년 중 어느 단계인지 판정한다.

    Args:
        year_branch: 원국 년주 지지(입춘 기준 — 띠가 아니라 만세력 年支).
        transit_branch: 세운 지지(입춘 기준 세운 간지의 지지).

    Returns:
        삼재 단계 정보. 역마·육해·화개 세운이 아니면 None(삼재 아님).
    """
    sinsal = relative_twelve_sinsal(year_branch, transit_branch)
    stage = SAMJAE_BY_SINSAL.get(sinsal)
    if stage is None:
        return None
    return SamjaeInfo(
        stage=stage,
        label_ko=SAMJAE_LABEL_KO[stage],
        sinsal=sinsal,
        sequence_index={SamjaeStage.ENTER: 1, SamjaeStage.STAY: 2, SamjaeStage.EXIT: 3}[stage],
        theme_ko=SAMJAE_THEME_KO[stage],
        basis=(
            f"연지 {year_branch}({trine_group_label(year_branch)}) 기준 "
            f"세운 {transit_branch}={sinsal}"
        ),
    )


def samjae_branches(year_branch: Branch) -> tuple[Branch, Branch, Branch]:
    """출생 연지 삼합국의 삼재 3년 지지(들→눌→날 순)."""
    return (
        branch_of_sinsal(year_branch, "역마살"),
        branch_of_sinsal(year_branch, "육해살"),
        branch_of_sinsal(year_branch, "화개살"),
    )
