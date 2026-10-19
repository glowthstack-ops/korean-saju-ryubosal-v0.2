"""일주 소개 문장 결정론 감사(2026-10-19 데굴님 승인).

규칙(context_reducer `_ILJU_SUMMARY_INSTRUCTION`, 2026-10-12 데굴님 지시): 일주는 '나'다 —
성격·성향을 설명해야 풀이가 이해되는 질문(연애·배우자·대인·적성)에만 인용하고, 총운·시기·택일
답에는 넣지 않는다.
실답(2026-10-19 '이력서 넣기 좋은 날' 2턴)에서 지시문이 있는데도 '己亥 일주는 … 정원사 같은 구조'가
두 답에 모두 들어갔다 — 지시로 막지 못하는 모델 습관은 재호출 없이 결정론으로 걷어낸다.

본문 외 어떤 값도 바꾸지 않는다. 일주를 **운 글자와의 관계**로 언급한 문장(복음·일주와 같은 간지·
일지 충)은 성향 소개가 아니므로 남긴다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from saju_shared_types.intent import Domain, QueryType

#: 일주 문장을 걷어내는 질문 유형 — 총운·시기·택일. 분야 개요는 성향 설명이 필요한 분야
#: (관계·교육=적성)를 뺀 나머지만.
_STRIP_QUERY_TYPES = frozenset({
    QueryType.FORTUNE_OVERVIEW, QueryType.TIMING_SEARCH, QueryType.DATE_RECOMMENDATION,
})
_STRIP_DOMAIN_ANALYSIS_DOMAINS = frozenset({
    Domain.CAREER, Domain.WEALTH, Domain.HEALTH, Domain.RELOCATION, Domain.GENERAL,
})
# 성향 소개 단서 — 일주 언급 + 이 어휘가 같은 문장에 있으면 소개 문장으로 본다.
_TRAIT_CUE_RE = re.compile(
    r"구조|성향|기질|성격|외면|내면|같은|품은|지향|다정|냉철|매력|부드럽|단정|영리|지혜|여유|유머"
)
# 운과의 관계 언급 — 소개가 아니므로 보존.
_LUCK_RELATION_RE = re.compile(r"복음|같은\s*간지|동일|겹치|충돌|충하|합하|일지")
_ILJU_RE = re.compile(r"일주")
# 다음 문장이 소개 문장을 지시어로 받으면('이러한 성향은 …') 지울 때 지시 대상이 사라진다
# (2026-10-19 실답 web-mvf73q3h) — 그때는 지우지 않고 로그만 남긴다.
_REFERENT_START_RE = re.compile(
    r"^\s*(?:이러한|이런|그러한|그런|이|그|이와\s*같은)\s*(?:성향|기질|성격|구조|면|특징|결|모습|기운|경향)"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class IljuMentionAudit(BaseModel):
    """감사 결과 — `text` 는 제거 적용본(대상 아니면 원문)."""

    text: str
    removed: list[str]
    gated: bool
    kept_referenced: list[str] = []


def should_strip(query_type: QueryType | None, domain: Domain | None) -> bool:
    """이 질문 유형·분야의 답에서 일주 소개 문장을 걷어내는가."""
    if query_type is None:
        return False
    if query_type in _STRIP_QUERY_TYPES:
        return True
    return (
        query_type is QueryType.DOMAIN_ANALYSIS
        and (domain or Domain.GENERAL) in _STRIP_DOMAIN_ANALYSIS_DOMAINS
    )


def is_ilju_intro_sentence(sentence: str) -> bool:
    """일주 성향 소개 문장인가(운과의 관계 언급은 제외)."""
    if not _ILJU_RE.search(sentence):
        return False
    if _LUCK_RELATION_RE.search(sentence):
        return False
    return bool(_TRAIT_CUE_RE.search(sentence))


def audit_ilju_mention(
    answer: str, query_type: QueryType | None, domain: Domain | None = None,
) -> IljuMentionAudit:
    """대상 질문 유형이면 일주 소개 문장을 문장 단위로 제거한다(문단 구조 보존).

    Args:
        answer: LLM 답변.
        query_type: 이번 턴 질문 유형(없으면 불변).
        domain: 분야(분야 개요의 가림 판단용).
    """
    gated = should_strip(query_type, domain)
    if not gated or not answer:
        return IljuMentionAudit(text=answer, removed=[], gated=gated)
    removed: list[str] = []
    kept_ref: list[str] = []
    paras = [
        [s for s in _SENTENCE_SPLIT_RE.split(p) if s.strip()] if p.strip() else []
        for p in answer.split("\n")
    ]
    flat = [(pi, si) for pi, sents in enumerate(paras) for si in range(len(sents))]
    drop: set[tuple[int, int]] = set()
    for k, (pi, si) in enumerate(flat):
        sent = paras[pi][si]
        if not is_ilju_intro_sentence(sent):
            continue
        nxt = paras[flat[k + 1][0]][flat[k + 1][1]] if k + 1 < len(flat) else ""
        if _REFERENT_START_RE.search(nxt):
            kept_ref.append(sent.strip()[:80])
            continue
        drop.add((pi, si))
        removed.append(sent.strip()[:80])
    if not removed:
        return IljuMentionAudit(
            text=answer, removed=[], gated=gated, kept_referenced=kept_ref,
        )
    out_paras = [
        " ".join(s.strip() for si, s in enumerate(sents) if (pi, si) not in drop)
        if sents else ""
        for pi, sents in enumerate(paras)
    ]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out_paras)).strip("\n")
    return IljuMentionAudit(text=text, removed=removed, gated=gated, kept_referenced=kept_ref)
