"""횡재 관점 일진 라벨(2026-11-16 데굴님 승인) — 서술 전용 층(점수·등급·순위 불변).

배경(실답 web-mwj26i50): '이번주중 로또사기 좋은 날' 답이 乙未일(천간 편관·기신, 지지 비견)을
"비견의 기운이 들어와 힘을 실어주는 날"이라며 가장 추천했다. 택일 표에는 '재물 신호 기반'이라는
빈 사유만 실려 있었고, 그날의 십성이 횡재와 어떤 관계인지는 LLM이 지어냈다.

이 모듈은 그날 일진의 천간·지지 십성을 **횡재 관점에서 무엇으로 읽는지**를 엔진이 정해 준다.
라벨은 세 갈래뿐이다(근거 정리 = doc/v2_2/WINDFALL_SIGNAL_REVIEW.md).

  ① 편재 = 횡재 유입 표지. 재성 오행이 기신·구신이면 부담을, 용신·희신이면 유리함을 병기한다.
     (三命通會 論偏財 "乃衆人之財" — 편재는 여럿의 재물, 운을 많이 타는 목돈.)
  ② 식상 = 재물로 이어지는 통로(식상생재). 편재와 같은 날 들어오면 통로와 유입이 이어진다.
  ③ 비겁·인성 = 일간 강약에 따라 갈린다.
     - 신약: 재물을 감당하는 조건(비겁)·일간을 받치는 조건(인성). 유입 표지가 아니다.
       (재다신약은 비겁 운에 발한다는 다수설 — "行運遇比劫則發". 대운 단위 이야기다.)
     - 신강: 비겁은 재물이 나뉘는 분탈 경계. (三命通會 "切忌有姊妹兄弟分奪".)
     - 중화: 비겁은 유입 표지가 아니라고만 적는다.

정재·관성에는 라벨을 붙이지 않는다(승인 범위 밖). 일진 단위의 횡재 판정은 자료 근거가 약해
(블로그 두 곳) 점수에는 쓰지 않는다 — 여기서 만드는 문장은 표의 사유 칸에 실리는 해설이다.
"""

from __future__ import annotations

from .pattern_conditions import WEAK_BANDS

_WEALTH_WINDFALL = "편재"
_OUTPUT_GODS = frozenset({"식신", "상관"})
_PEER_GODS = frozenset({"비견", "겁재"})
_RESOURCE_GODS = frozenset({"정인", "편인"})
_UNFAVORABLE = frozenset({"기신", "구신"})
_FAVORABLE = frozenset({"용신", "희신"})

BODY_STRONG = "strong"
BODY_WEAK = "weak"
BODY_NEUTRAL = "neutral"


def body_side(band: str, gate_passed: bool) -> str:
    """신강약 밴드 → 횡재 관점 일간 쪽(strong / weak / neutral).

    신강 판정은 재물 그릇 분류(`wealth_capacity._is_strong`)와 같은 기준이고, 신약 판정은 구조
    패턴의 일간 감당 조건(`pattern_conditions.WEAK_BANDS`)과 같다 — 같은 프롬프트에 실리는
    [원국 횡재 그릇]·구조 블록과 말이 어긋나지 않게 한다.

    Args:
        band: 신강약 7단계 밴드(`force_analysis.strength.band`).
        gate_passed: 강신 게이트 통과 여부(`strong_chart_gate.passed`).

    Returns:
        ``BODY_STRONG`` / ``BODY_WEAK`` / ``BODY_NEUTRAL``.
    """
    if gate_passed or ("강" in band and "약" not in band):
        return BODY_STRONG
    if band in WEAK_BANDS:
        return BODY_WEAK
    return BODY_NEUTRAL


def _seat(stem_hit: bool, branch_hit: bool) -> str:
    """십성이 든 자리 표기 — 천간 / 지지 / 천간·지지."""
    if stem_hit and branch_hit:
        return "천간·지지"
    return "천간" if stem_hit else "지지"


def windfall_day_lens(
    *,
    stem_ten_god: str,
    branch_ten_god: str,
    body: str,
    wealth_role: str | None,
) -> list[str]:
    """일진 천간·지지 십성을 횡재 관점 라벨 문장으로 옮긴다.

    Args:
        stem_ten_god: 일진 천간 십성.
        branch_ten_god: 일진 지지(본기) 십성.
        body: ``body_side`` 결과(strong / weak / neutral).
        wealth_role: 재성 오행의 역할(용신/희신/한신/기신/구신). 모르면 None.

    Returns:
        라벨 문장 목록(해당 십성이 없으면 빈 목록). 순서는 편재 → 식상 → 비겁 → 인성.
    """
    notes: list[str] = []
    gods = (stem_ten_god, branch_ten_god)

    wealth_hit = _WEALTH_WINDFALL in gods
    if wealth_hit:
        seat = _seat(stem_ten_god == _WEALTH_WINDFALL, branch_ten_god == _WEALTH_WINDFALL)
        text = f"편재({seat}) — 횡재 유입 표지"
        if wealth_role in _UNFAVORABLE:
            text += (
                f"이지만 이 명식에서 재성은 {wealth_role}이라 투기 충동·예상 밖 지출 쪽 부담을 "
                "함께 본다"
            )
        elif wealth_role in _FAVORABLE:
            text += f"이고 재성이 {wealth_role}이라 유리한 방향으로 작동한다"
        notes.append(text)

    output_stem, output_branch = (g in _OUTPUT_GODS for g in gods)
    if output_stem or output_branch:
        text = f"식상({_seat(output_stem, output_branch)}) — 재물로 이어지는 통로(식상생재)"
        if wealth_hit:
            text += "이며 편재와 한 날에 들어와 통로와 유입이 이어진다"
        notes.append(text)

    peer_stem, peer_branch = (g in _PEER_GODS for g in gods)
    if peer_stem or peer_branch:
        seat = _seat(peer_stem, peer_branch)
        if body == BODY_WEAK:
            notes.append(
                f"비겁({seat}) — 신약 원국에서는 들어온 재물을 감당하는 조건이다"
                "(횡재 유입 표지는 아니다)"
            )
        elif body == BODY_STRONG:
            notes.append(
                f"비겁({seat}) — 신강 원국에서는 재물이 나뉘는 쪽이다(횡재 유입 표지가 아니다)"
            )
        else:
            notes.append(f"비겁({seat}) — 횡재 유입 표지가 아니다(편재를 나누는 쪽)")

    resource_stem, resource_branch = (g in _RESOURCE_GODS for g in gods)
    if (resource_stem or resource_branch) and body == BODY_WEAK:
        notes.append(
            f"인성({_seat(resource_stem, resource_branch)}) — 신약 원국에서 일간을 받치는 "
            "조건이다(횡재 유입 표지는 아니다)"
        )
    return notes
