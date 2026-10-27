"""성립 불가 간지 관계 주장 감사 — 결정론 교정.

2026-10-27 데굴님: "이런 오류는 풀이 신뢰도를 크게 낮출 수 있어."

발단: 실답 "일간인 戊(무)토와 운의 壬(임)수가 합을 이루어" — 戊의 천간합은 癸이고 戊·壬은 극이다.
입력에는 丁壬合만 있었다. 기존 관계 감사(`relation_claim_audit`)는 엔진이 판정한 관계를 뒤집는
서술만 보고, 총운 경로에서만 돈다 — 표에 없는 관계를 지어낸 문장은 어느 경로에서도 걸리지 않았다.

판정은 **관계 표 자체**로만 한다(엔진 상수 SSOT). 두 간지 글자가 연결어(와·과·쉼표·가운뎃점)로
이어지고 바로 뒤에 관계어(합·충·형·파·해·원진)가 오는데 그 쌍이 그 관계 표에 없으면 위반이다.
정밀도 우선 — 천간·지지 혼합 쌍과 지장간 '암합'은 학파·해석 폭이 있어 보지 않고, 일상어
('합니다'·'충분'·'형성'·'파악'·'해요')는 관계어로 보지 않는다. 위반 문장은 재호출 없이 지운다
(사실 오류를 알고 전달하지 않는다 — fail-open 금지).
"""

from __future__ import annotations

import re

from pydantic import BaseModel
from saju_manse_analysis.sinsal.sinsal_catalog import WONJIN

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    DIRECTIONAL_COMBINATIONS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    STEM_CLASHES,
    STEM_COMBINATIONS,
    THREE_HARMONY,
)
from saju_shared_types.enums import Branch, Stem

from .relation_claim_audit import split_sentences

_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
#: '음+오행' 한글 별칭 → 글자. '신금'은 辛·申 모두라 모호해 제외한다.
_KO_ALIAS: dict[str, str] = {
    "갑목": "甲", "을목": "乙", "병화": "丙", "정화": "丁", "무토": "戊", "기토": "己",
    "경금": "庚", "임수": "壬", "계수": "癸",
    "자수": "子", "축토": "丑", "인목": "寅", "묘목": "卯", "진토": "辰", "사화": "巳",
    "오화": "午", "미토": "未", "유금": "酉", "술토": "戌", "해수": "亥",
}
_MENTION = re.compile(
    rf"(?P<h>[{_STEMS}{_BRANCHES}])(?:\([가-힣]{{1,2}}\))?[木火土金水목화토금수]?"
    rf"|(?P<k>{'|'.join(_KO_ALIAS)})"
)
#: 두 글자 사이 연결어 — 이 중 하나가 있어야 '두 글자의 관계' 주장으로 본다.
_CONNECTOR = re.compile(r"와|과|·|,|↔|및")
_GAP_MAX = 10
#: 두 번째 글자 뒤 관계어까지 허용 거리(조사·'서로' 정도).
_TAIL_MAX = 8
_KEYWORD = re.compile(
    r"(천간합|육합|삼합|반합|방합|공합|암합|합|合|충돌|충|沖|冲|삼형|자형|상형|형|刑|파|破|육해|害|원진)"
)
#: 관계어로 보지 않는 일상어 — 관계어 바로 뒤 글자로 거른다.
_NOT_RELATION_NEXT: dict[str, str] = {
    "합": "니", "충": "분전족실만격당", "형": "성태편식제", "파": "악도트장생랑",
}
#: 두 번째 글자와 관계어 사이에 허용하는 말 — 조사·'서로'·'만나' 정도. 괄호·접속('이나') 등이 끼면
#: 관계어가 다른 구의 것이다(실측 오탐: '사해충(亥·巳)이나 해해자형(亥·亥)' 의 '자형').
_TAIL_PREFIX_OK = re.compile(r"^(?:\s|이|가|은|는|의|도|끼리|서로|사이|에|만나|서)*$")
#: 묶음 관계어 — 셋 이상을 나열한 문장의 같은 글자 쌍은 판정하지 않는다
#: ('巳와 申, 월운의 申이 삼형').
_GROUP_KEYWORDS = frozenset({"삼합", "방합", "삼형"})
_NEGATION = re.compile(r"않|아니|없|못")
_NEGATION_WINDOW = 12


class ImpossibleRelationClaim(BaseModel):
    """성립 불가 관계 주장 1건."""

    sentence_index: int
    sentence: str
    pair: str  # '戊壬'
    relation: str  # 문장에 쓰인 관계어('합')


def _char_of(m: re.Match[str]) -> str:
    return m.group("h") or _KO_ALIAS[m.group("k")]


def _same_group(a: str, b: str, groups: list[frozenset[Branch]]) -> bool:
    return any({Branch(a), Branch(b)} <= set(g) for g in groups)


_TRINES = [g for g, _el, _c in THREE_HARMONY]
_DIRECTIONS = [g for g, _el in DIRECTIONAL_COMBINATIONS]


def _valid(a: str, b: str, kw: str) -> bool | None:
    """그 쌍이 그 관계로 성립하는가. 판정 대상이 아니면 None."""
    if kw == "암합":
        return None
    a_stem, b_stem = a in _STEMS, b in _STEMS
    if a_stem != b_stem:
        return None  # 천간·지지 혼합 — 해석 폭이 있어 보지 않는다
    if a_stem:
        pair_s = frozenset({Stem(a), Stem(b)})
        if kw in ("합", "合", "천간합"):
            return a != b and pair_s in STEM_COMBINATIONS
        if kw in ("충", "沖", "冲", "충돌"):
            return a != b and frozenset({a, b}) in STEM_CLASHES
        return False  # 육합·삼합·형·파·해·원진은 지지 관계다
    pair_b = frozenset({Branch(a), Branch(b)})
    if a == b and kw in _GROUP_KEYWORDS:
        return None
    if a == b:
        return kw in ("형", "刑", "자형") and Branch(a) in SELF_PUNISHMENT
    if kw in ("합", "合"):
        return (
            pair_b in SIX_COMBINATIONS
            or _same_group(a, b, _TRINES) or _same_group(a, b, _DIRECTIONS)
        )
    if kw == "육합":
        return pair_b in SIX_COMBINATIONS
    if kw in ("삼합", "반합", "공합"):
        return _same_group(a, b, _TRINES)
    if kw == "방합":
        return _same_group(a, b, _DIRECTIONS)
    if kw in ("충", "沖", "冲", "충돌"):
        return pair_b in BRANCH_CLASHES
    if kw in ("형", "刑", "상형", "삼형"):
        return pair_b in PUNISHMENT_MUTUAL or _same_group(a, b, PUNISHMENT_TRIPLES)
    if kw == "자형":
        return False
    if kw in ("파", "破"):
        return pair_b in BRANCH_BREAKS
    if kw in ("육해", "害"):
        return pair_b in BRANCH_HARMS
    if kw == "원진":
        return pair_b in WONJIN
    return None


def _relation_keyword(tail: str) -> tuple[str, int] | None:
    """두 번째 글자 뒤 짧은 꼬리에서 관계어를 찾는다(다른 간지 언급이 끼면 None)."""
    m = _KEYWORD.search(tail[: _TAIL_MAX + 4])
    if m is None or m.start() > _TAIL_MAX:
        return None
    if _MENTION.search(tail[: m.start()]):
        return None  # '申과 巳가 합' — 관계 주체가 바뀌었다
    if not _TAIL_PREFIX_OK.match(tail[: m.start()]):
        return None
    kw = m.group(1)
    nxt = tail[m.end() : m.end() + 1]
    if kw in _NOT_RELATION_NEXT and nxt and nxt in _NOT_RELATION_NEXT[kw]:
        return None
    if _NEGATION.search(tail[m.end() : m.end() + _NEGATION_WINDOW]):
        return None  # '합이 아니라 극' — 부정 문맥
    return kw, m.end()


def find_impossible_relation_claims(text: str) -> list[ImpossibleRelationClaim]:
    """답변에서 관계 표에 없는 두 간지 관계 주장을 찾는다.

    Args:
        text: 답변 원문.

    Returns:
        위반 목록(문장 순). 없으면 빈 목록.
    """
    out: list[ImpossibleRelationClaim] = []
    for sent in split_sentences(text):
        s = sent.text
        mentions = list(_MENTION.finditer(s))
        for m1, m2 in zip(mentions, mentions[1:], strict=False):
            gap = s[m1.end() : m2.start()]
            if len(gap) > _GAP_MAX or not _CONNECTOR.search(gap) or _KEYWORD.search(gap):
                continue
            found = _relation_keyword(s[m2.end() :])
            if found is None:
                continue
            a, b = _char_of(m1), _char_of(m2)
            ok = _valid(a, b, found[0])
            if ok is False:
                out.append(ImpossibleRelationClaim(
                    sentence_index=sent.index, sentence=s.strip(), pair=f"{a}{b}",
                    relation=found[0],
                ))
                break  # 한 문장은 한 번만 센다
    return out


def strip_impossible_relation_claims(text: str) -> tuple[str, list[ImpossibleRelationClaim]]:
    """위반 문장을 지운 답변과 위반 목록(재호출 없음).

    문장 단위로 지우고 남은 공백·빈 문단을 정리한다. 위반이 없으면 원문 그대로.
    """
    claims = find_impossible_relation_claims(text)
    if not claims:
        return text, []
    drop = {c.sentence_index for c in claims}
    pieces: list[str] = []
    pos = 0
    for sent in split_sentences(text):
        if sent.index in drop:
            pieces.append(text[pos : sent.start])
            pos = sent.end
            # 지운 문장 뒤 같은 줄 공백은 함께 지운다(줄바꿈은 문단 경계라 남긴다).
            while pos < len(text) and text[pos] == " ":
                pos += 1
    pieces.append(text[pos:])
    out = "".join(pieces)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, claims


__all__ = [
    "ImpossibleRelationClaim",
    "find_impossible_relation_claims",
    "strip_impossible_relation_claims",
]
