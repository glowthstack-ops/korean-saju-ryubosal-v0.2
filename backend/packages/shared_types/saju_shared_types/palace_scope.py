"""궁위(宮位) 의미 표 — 연·월·일·시주 자리의 뜻 단일 원천(SSOT, 2026-11-21 데굴님 승인).

같은 네 자리의 뜻이 소비처마다 따로 적혀 있었다(명식 구조 블록의 육친 자리역할, 신살 발췌의 자리
라벨, 궁위 관계망, 반복 구조의 궁위 안내). 문구는 소비처의 쓰임에 맞춰 조금씩 달라야 해서 하나로
합치지 않고, **한 표의 열**로 모아 둔다 — 자리의 뜻을 고칠 때 한곳만 보면 된다.

`relation_scope`(인연 범위)는 2026-11-21 에 더한 열이다. 그 자리의 글자가 '누구와의 일'로 드러나기
쉬운지를 가늠하는 보조 단서다(연주 = 넓고 얕은 공적 관계, 월주 = 사회생활의 핵심 인맥, 일주 = 사적
으로 깊은 관계, 시주 = 내가 이끄는 아랫사람). 조상·부모·나와 배우자·자식이라는 기본 배속은 통설이고,
대중·해외 인연·부하·후배·제자까지 넓힌 대응은 현대 통변의 확장이라 **서술 보조로만** 쓴다 — 점수·
판정·사건 종류에 쓰지 않고, '연주에 있으니 윗사람' 같은 고정 등식으로도 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PalaceKey = Literal["year", "month", "day", "hour"]

#: 궁위 표준 순서(연 → 시).
PALACE_KEYS: tuple[PalaceKey, ...] = ("year", "month", "day", "hour")


@dataclass(frozen=True)
class PalaceMeaning:
    """궁위 1자리의 뜻 — 소비처별 라벨(열)과 인연 범위.

    Attributes:
        key: 자리 키(year/month/day/hour).
        pillar_ko: 기둥 이름(연주·월주·일주·시주).
        kin_role: 육친 자리역할 — 명식 구조 블록 `궁성:` 칸(천간/지지 가족 궁).
        sinsal_label: 신살 발췌의 자리 라벨 — 대상·시기 축(궁성론).
        network_label: 궁위 관계망의 자리 라벨 — 관계 영역 축.
        repetition_label: 반복 구조(지지 반복·자형)의 궁위 안내 라벨 — 지지 기준.
        relation_scope: 인연 범위 — 그 자리가 가리키기 쉬운 사람의 범위(보조 단서).
    """

    key: PalaceKey
    pillar_ko: str
    kin_role: str
    sinsal_label: str
    network_label: str
    repetition_label: str
    relation_scope: str


PALACE_TABLE: dict[PalaceKey, PalaceMeaning] = {
    "year": PalaceMeaning(
        key="year", pillar_ko="연주",
        kin_role="천간 조부 · 지지 조모(뿌리·조상궁)",
        sinsal_label="연주(조상·고향·초년)",
        network_label="연주(조상·가문·사회 배경)",
        repetition_label="연지(조상·사회 배경)",
        relation_scope="넓고 얕은 공적 관계 — 대중·윗사람(어르신·스승)·먼 곳(해외)의 인연",
    ),
    "month": PalaceMeaning(
        key="month", pillar_ko="월주",
        kin_role="천간 부친 · 지지 모친(부모·사회궁)",
        sinsal_label="월주(부모·직장·사회·청년 — 작용력 최대)",
        network_label="월주(부모·형제·성장환경)",
        repetition_label="월지(사회·직장)",
        relation_scope="사회생활의 핵심 인맥 — 직장 동료·상사, 부모·형제",
    ),
    "day": PalaceMeaning(
        key="day", pillar_ko="일주",
        kin_role="천간 자신 · 지지 배우자(나·배우자궁)",
        sinsal_label="일주(나·배우자·장년)",
        network_label="일지(배우자·친밀관계)",
        repetition_label="일지(배우자·몸)",
        relation_scope="사적으로 깊은 관계 — 배우자·연인·가장 가까운 친구",
    ),
    "hour": PalaceMeaning(
        key="hour", pillar_ko="시주",
        kin_role="천간 아들 · 지지 딸(자녀·결과궁)",
        sinsal_label="시주(자녀·내면·말년)",
        network_label="시주(자식·후대·결과)",
        repetition_label="시지(자녀·지향·투자)",
        relation_scope="내가 이끌어 주는 아랫사람 — 자녀·부하 직원·후배·제자",
    ),
}

#: 인연 범위 사용 규칙 — 궁위별 인연 범위를 LLM 입력에 싣는 곳이 함께 싣는다.
PALACE_SCOPE_RULE = (
    "[궁위 인연 범위 — 보조 단서] 그 자리의 글자·신살·관계가 '누구와의 일'로 드러나기 쉬운지 "
    "가늠하는 참고로만 쓴다. 사람을 특정할 근거가 따로 없으면 '~쪽 사람과의 일일 수 있다' 정도로만 "
    "말하고, '연주에 있으니 윗사람'처럼 고정 등식으로 단정하지 말 것. 길흉·사건 종류·시기는 "
    "이 줄이 정하지 않는다."
)


def palace_column(column: str) -> dict[str, str]:
    """표의 한 열을 `{자리 키: 문구}` 로 꺼낸다(소비처의 기존 dict 대체).

    Args:
        column: `PalaceMeaning` 필드명(kin_role·sinsal_label·network_label·repetition_label·
            relation_scope·pillar_ko).
    """
    return {key: str(getattr(PALACE_TABLE[key], column)) for key in PALACE_KEYS}


def palace_scope_legend() -> str:
    """인연 범위 한 줄 범례 — '연주=… / 월주=… / 일주=… / 시주=…'."""
    return " / ".join(
        f"{PALACE_TABLE[key].pillar_ko}={PALACE_TABLE[key].relation_scope}" for key in PALACE_KEYS
    )


__all__ = [
    "PALACE_KEYS",
    "PALACE_SCOPE_RULE",
    "PALACE_TABLE",
    "PalaceKey",
    "PalaceMeaning",
    "palace_column",
    "palace_scope_legend",
]
