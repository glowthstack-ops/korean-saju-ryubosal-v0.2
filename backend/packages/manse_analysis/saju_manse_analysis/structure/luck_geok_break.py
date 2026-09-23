"""運破格 판정 — 운 십성이 원국 격(格)의 상신(相神)을 손상하는가, 원국에 구응(救應)이 있는가.

배경(2026-09-18 데굴님 승인, 전문가 참고 기준): '파격'은 원국 격국 평가(geokguk_eval)에만 있었고
운이 격을 깨는 경우는 이름이 없었다. 『자평진전』 성패·구응 논의대로 **방해 구조와 이를 조절하는
구조를 함께** 본다 — 파격 십성이 운으로 들어와도 원국에 구응 십성이 있으면 '경향'으로만 표기한다.

이 모듈은 판정만 한다(가중치는 소비처: event_engine_v2 favorability 감점). 점수·순위 불변.
격별 파격·구응 표는 geokguk_eval._detect_failures의 원국 규칙(상관견관·관살혼잡·비겁쟁재·
재극인·편인도식·재생살)을 운 유입 관점으로 옮긴 것이며, 여기 없는 격(건록·양인·특수격)은 판정하지
않는다(보수적).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# 격신(格神) 십성 → [(파격 십성 집합, 구응 십성 집합, 구조 이름)] — 규칙표 SSOT.
_BREAK_RULES: dict[str, list[tuple[frozenset[str], frozenset[str], str]]] = {
    "정관": [
        (frozenset({"상관"}), frozenset({"정인", "편인", "정재", "편재"}), "상관견관"),
        (frozenset({"편관"}), frozenset({"식신", "정인", "편인"}), "관살혼잡"),
    ],
    "편관": [
        (frozenset({"정관"}), frozenset({"식신", "정인", "편인"}), "관살혼잡"),
        (frozenset({"정재", "편재"}), frozenset({"식신", "정인", "편인"}), "재생살"),
    ],
    "정재": [
        (frozenset({"비견", "겁재"}), frozenset({"정관", "편관", "식신", "상관"}), "비겁쟁재"),
    ],
    "편재": [
        (frozenset({"비견", "겁재"}), frozenset({"정관", "편관", "식신", "상관"}), "비겁쟁재"),
    ],
    "정인": [(frozenset({"정재", "편재"}), frozenset({"비견", "겁재", "정관", "편관"}), "재극인")],
    "편인": [(frozenset({"정재", "편재"}), frozenset({"비견", "겁재", "정관", "편관"}), "재극인")],
    "식신": [(frozenset({"편인"}), frozenset({"정재", "편재"}), "편인도식")],
    "상관": [(frozenset({"정관"}), frozenset({"정인", "편인", "정재", "편재"}), "상관견관")],
}


@dataclass(frozen=True)
class LuckGeokBreak:
    """운 파격 판정 1건."""

    geok: str  # 원국 격 이름('정재격')
    breaker: str  # 운으로 들어온 파격 십성('겁재')
    pattern: str  # 구조 이름('비겁쟁재')
    rescued: bool  # 원국에 구응 십성이 있는가(있으면 '경향'으로만)
    rescue_evidence: str  # 구응 십성 목록 또는 '구응 없음'


def geok_break(
    geok_name: str | None,
    luck_ten_gods: Iterable[str],
    natal_ten_gods: Iterable[str],
) -> list[LuckGeokBreak]:
    """순수 판정 — (격 이름, 운 십성들, 원국 십성들) → 운 파격 목록(없으면 빈 목록).

    Args:
        geok_name: 원국 주격 이름('정재격' 등). None·미등록 격이면 빈 목록.
        luck_ten_gods: 그 시점 운 천간·지지(본기) 십성.
        natal_ten_gods: 원국 천간(일간 제외)·지지 본기 십성.
    """
    if not geok_name or not geok_name.endswith("격"):
        return []
    rules = _BREAK_RULES.get(geok_name[:-1])
    if not rules:
        return []
    luck = list(dict.fromkeys(luck_ten_gods))
    natal = set(natal_ten_gods)
    out: list[LuckGeokBreak] = []
    for breakers, rescuers, pattern in rules:
        hit = next((g for g in luck if g in breakers), None)
        if hit is None:
            continue
        present = sorted(natal & rescuers)
        out.append(LuckGeokBreak(
            geok=geok_name, breaker=hit, pattern=pattern,
            rescued=bool(present),
            rescue_evidence="·".join(present) if present else "구응 없음",
        ))
    return out
