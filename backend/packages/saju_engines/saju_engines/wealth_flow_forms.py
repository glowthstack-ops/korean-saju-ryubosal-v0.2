"""재물 입출 형태 — 후보별 '들어오는/나가는 방식' 서술층 (2026-11-07 데굴님 "금전운도 들어오거나
나가는 방식이 중요해").

재물 후보(wealth_change·windfall)의 근거 신호와 같은 기간의 동반 후보로 **가능한 형태**를 통설
기준으로 붙인다. 들어오는 쪽: 정기 소득(정재)·투자/거래 자산 증식(편재)·활동 성과 수입(식상생재)·
횡재(windfall)·
묶였던 돈 회수(재성 합 풀림)·문서/계약 자산(재+관+인). 나가는 쪽: 병원비(건강 후보 동반)·주거비(이사
후보 동반)·가족 지출(부모·자녀 궁위 발동)·빌려주거나 떼임(비겁 운·군겁쟁재)·투자 손실(편재 흉)·
고정 수입 감소(정재 흉). 점수·판정·순위 무관 — 서술 재료이며 '그럴 수 있다'로만 쓴다(금액·종목
금지).
"""

from __future__ import annotations

from collections.abc import Iterable

from saju_shared_types.events import EventCandidate

from .context_reducer import overview_cluster_key

WEALTH_EVENT_KEYS = frozenset({"wealth_change", "windfall"})
#: 동반 후보 판정 하한(같은 기간의 건강·이사 후보).
COMPANION_MIN = 50
WEALTH_FORM_LEGEND = (
    "(재물 입출 형태 읽는 법: 근거 신호·동반 후보로 고른 '들어오거나 나가는 방식'의 통설 후보다. "
    "확정이 아니며 금액·종목·당첨은 쓰지 않는다. 한 후보에 여러 형태가 있으면 '…이나 …처럼'으로 "
    "묶어 쓸 것.)"
)

_INFLOW_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ZHENGCAI",), "정기 소득(급여·고정 수입)이 늘거나 안정되는 결"),
    (("PIANCAI",), "투자·거래·유동 자산이 불어나거나 외부 기회로 들어오는 결"),
    (
        ("SHISHEN", "SHANGGUAN", "식상생재", "식상 보강"),
        "활동·성과로 버는 수입(부업·성과급·판매)의 결",
    ),
    (
        ("SAME_GOD_HAP_WEALTH", "VOID_COMBINE_RELEASE", "VOID_FILL"),
        "묶여 있던 돈이 풀리는 결(빌려준 돈·보증금·미수금 회수)",
    ),
    (
        ("TRI_WEALTH_AUTHORITY_RESOURCE", "ZHENGYIN", "PIANYIN"),
        "문서·계약을 통한 자산(계약금·부동산·정산)의 결",
    ),
)
_OUTFLOW_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("BIJIAN", "JIECAI", "PEER", "군겁쟁재", "비겁쟁재"),
        "빌려주거나 떼이기 쉬운 돈(보증·대여·분배)의 결 — 군겁쟁재 통설",
    ),
    (("PIANCAI",), "투자 손실·과소비·거래 지출의 결"),
    (("ZHENGCAI",), "고정 수입이 줄거나 생활 지출이 느는 결"),
)
_FAMILY_PALACE_TOKENS = ("year_pillar", "month_pillar", "hour_pillar")


def _tokens(c: EventCandidate) -> str:
    return " ".join(str(e) for e in c.evidence_path)


def wealth_form_notes(
    c: EventCandidate, peers: Iterable[EventCandidate] | None = None,
) -> list[str]:
    """재물 후보 1건의 입출 형태 목록(없으면 빈 목록).

    같은 기간 동반 후보(건강·이사)로 지출 형태를 보강한다.
    """
    key = str(c.event_key)
    if key not in WEALTH_EVENT_KEYS:
        return []
    tokens = _tokens(c)
    direction = overview_cluster_key(c)[1]
    notes: list[str] = []
    if key == "windfall":
        notes.append("횡재(공돈·환급·경품·예상 밖 수입)의 결 — 소액·재미로")
    if direction != "neg":
        for needles, text in _INFLOW_RULES:
            if any(n in tokens for n in needles) and text not in notes:
                notes.append(text)
    if direction != "pos":
        for needles, text in _OUTFLOW_RULES:
            if any(n in tokens for n in needles) and text not in notes:
                notes.append(text)
        if "REL_" in tokens and any(p in tokens for p in _FAMILY_PALACE_TOKENS):
            notes.append("가족(부모·자녀 자리)에게 쓰는 비용의 결")
        for p in peers or ():
            if str(p.period) != str(c.period) or p.score < COMPANION_MIN:
                continue
            pk = str(p.event_key)
            if pk == "health_attention":
                notes.append("병원비·치료비 지출의 결(같은 시기 건강 후보 동반)")
            elif pk == "relocation":
                notes.append("주거비(이사·월세·보증금 상승) 지출의 결(같은 시기 이사 후보 동반)")
    return list(dict.fromkeys(notes))


def wealth_form_lines(
    cands: Iterable[EventCandidate], peers: Iterable[EventCandidate] | None = None,
) -> list[str]:
    """[재물 입출 형태] 블록 — 재물 후보가 하나라도 형태를 가지면 헤더 + 후보별 줄."""
    peers_list = list(peers or [])
    rows: list[str] = []
    for c in cands:
        notes = wealth_form_notes(c, peers_list)
        if not notes:
            continue
        label = "횡재" if str(c.event_key) == "windfall" else "재물 변화"
        rows.append(f"- {c.period} {label}: " + " / ".join(notes))
    if not rows:
        return []
    return [
        "[재물 입출 형태 — 후보별 가능한 방식(근거 신호·동반 후보 기준 통설, 확정 아님. "
        "금액·종목·당첨 금지)]",
        *rows,
    ]


__all__ = [
    "COMPANION_MIN",
    "WEALTH_EVENT_KEYS",
    "WEALTH_FORM_LEGEND",
    "wealth_form_lines",
    "wealth_form_notes",
]
