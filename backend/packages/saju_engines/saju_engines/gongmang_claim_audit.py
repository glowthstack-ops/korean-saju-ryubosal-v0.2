"""공망 지목 결정론 감사(2026-10-19 데굴님 승인).

배경(실답 web-mvf73q3h, 2026-10-19): 엔진의 2026-11 己亥 줄에는 '지연·보류'만 있고
공망 신호가 없었는데, 답이 "지지의 정재가 공망의 영향으로 지연을 일으켜"라고 썼다. 亥는 공망
글자(辰巳)가 아니고, 실제 공망 사실은 원국 시지 巳와 현재 대운 壬辰의 辰이었다. 프롬프트의 공망
해석 규칙("발동 신호 없는 시점엔 공망 언급 금지, 다른 지지를 공망으로 지목 금지")만으로
막지 못해 생성 후 문장 단위로 걸러낸다.

판정(문장 단위, 재호출 없음):
- 공망을 **주장**한 문장만 본다(부정 '공망이 아니'·'공망과 상관없' 등은 제외).
- 공망 글자(한자·한글 독음)나 대운·원국 자리(시지·시주 등)를 함께 짚은 문장은 사실 서술로 보고 둔다.
- 그 외에 ①공망이 아닌 지지 글자를 공망으로 지목했거나 ②문단이 가리키는 달·해에 엔진 공망 신호가
  없으면 위반 — 그 문장을 지운다(문단 구조 보존).
- **대운 공망 영향 규칙(2026-10-25 데굴님 결정)**: '대운'과 공망 주장이 한 문장에 있고
  지연·시일·공허·실속·인내 같은 **영향 어휘**가 붙으면 그 문장을 지운다. 현대 통설(2026-10-23)은
  대운 공망의 영향을 보지 않는데, 실답에서 "대운 지지 辰이 공망의 영향권에 있어 결실까지
  시일이 걸린다"가 나왔다.
  대운 지지가 공망 글자라는 **사실만** 말한 문장(영향 어휘 없음)과 원국 공망 자리의 활성
  (살아남·채워짐) 서술은 대상이 아니다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel

_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_BRANCH_KO = dict(zip(_BRANCHES, "자축인묘진사오미신유술해", strict=True))
_GONGMANG_RE = re.compile(r"공망")
_NEGATION_RE = re.compile(
    r"공망(?:이|은|에)?\s*(?:아니|아닌|해당하지\s*않|해당되지\s*않)"
    r"|공망(?:과|이랑|하고|와)?\s*(?:는\s*)?(?:상관|관계)\s*없"
)
_LEGIT_CONTEXT_RE = re.compile(r"대운|원국|시지|시주|일지|월지|연지|년지|명식|타고난")
_DAEWOON_RE = re.compile(r"대운")
#: 대운 공망을 길흉·시기 근거로 쓴 문장의 영향 어휘 — 지연·공허·실속 계열(활성·전실 어휘는 제외).
_DAEWOON_VOID_EFFECT_RE = re.compile(
    r"지연|늦어|늦게|늦춰|시일|더디|미뤄|미루|보류|공허|허무|실속|비어\s*있|흐지부지|무산|인내"
    r"|기다려|기다리|영향권|기대를\s*낮|결실이\s*(?:약|늦|어렵)|헛|빈\s*자리"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MONTH_REF_RES = (
    re.compile(r"((?:19|20)\d{2})\s*년\s*(\d{1,2})\s*월"),
    re.compile(r"((?:19|20)\d{2})-(\d{2})"),
)
_YEAR_REF_RE = re.compile(r"((?:19|20)\d{2})\s*년(?!\s*\d{1,2}\s*월)")


class GongmangClaimAudit(BaseModel):
    """감사 결과 — `text` 는 위반 문장 제거본."""

    text: str
    removed: list[str]


def _branch_mentions(sentence: str) -> set[str]:
    """문장에 나온 지지 한자(한글 독음 병기 '亥(해)' 포함)."""
    return {ch for ch in sentence if ch in _BRANCHES}


def _mentions_void(sentence: str, void: set[str]) -> bool:
    if any(b in sentence for b in void):
        return True
    # 한글 독음 단독('사(巳)' 없이 '시지 사') 표기는 문맥상 모호해 자리어와 함께일 때만 인정.
    return any(f"{_BRANCH_KO[b]}(" in sentence for b in void)


def _period_refs(text: str) -> list[str]:
    """텍스트에 나온 월(YYYY-MM)·연(YYYY) 참조를 등장 순서대로."""
    found: list[tuple[int, str]] = []
    for rx in _MONTH_REF_RES:
        for m in rx.finditer(text):
            found.append((m.start(), f"{m.group(1)}-{int(m.group(2)):02d}"))
    for m in _YEAR_REF_RE.finditer(text):
        found.append((m.start(), m.group(1)))
    return [p for _, p in sorted(found)]


def _asserts_gongmang(sentence: str) -> bool:
    return bool(_GONGMANG_RE.search(sentence)) and not _NEGATION_RE.search(sentence)


def _daewoon_void_effect(sentence: str) -> bool:
    """대운 공망을 지연·공허·실속 근거로 쓴 문장인가(대운 공망 무시 원칙 위반)."""
    return bool(_DAEWOON_RE.search(sentence)) and bool(_DAEWOON_VOID_EFFECT_RE.search(sentence))


def audit_gongmang_claims(
    answer: str,
    void_branches: Iterable[str],
    signal_periods: Iterable[str],
) -> GongmangClaimAudit:
    """공망을 잘못 지목한 문장을 지운다.

    Args:
        answer: LLM 답변.
        void_branches: 원국 공망 지지(일공망, 예: ['辰', '巳']).
        signal_periods: 엔진이 공망 신호(충발·전실·해소)를 표기한 기간 라벨(YYYY-MM·YYYY).
    """
    void = set(void_branches)
    periods = set(signal_periods)
    if not answer or not void or "공망" not in answer:
        return GongmangClaimAudit(text=answer, removed=[])
    removed: list[str] = []
    out_paras: list[str] = []
    for para in answer.split("\n"):
        if "공망" not in para:
            out_paras.append(para)
            continue
        kept: list[str] = []
        seen = ""
        for sent in _SENTENCE_SPLIT_RE.split(para):
            seen = f"{seen} {sent}"
            if not _asserts_gongmang(sent):
                kept.append(sent)
                continue
            if _daewoon_void_effect(sent):  # 대운 공망 영향 서술 — 사실 문맥이어도 지운다
                removed.append(sent.strip()[:80])
                continue
            if _mentions_void(sent, void) or _LEGIT_CONTEXT_RE.search(sent):
                kept.append(sent)
                continue
            wrong_branch = bool(_branch_mentions(sent) - void)
            refs = _period_refs(seen)
            ref = refs[-1] if refs else None
            no_signal = ref is not None and ref not in periods and ref[:4] not in periods
            if wrong_branch or no_signal:
                removed.append(sent.strip()[:80])
            else:
                kept.append(sent)
        out_paras.append(" ".join(s.strip() for s in kept if s.strip()))
    if not removed:
        return GongmangClaimAudit(text=answer, removed=[])
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out_paras)).strip("\n")
    return GongmangClaimAudit(text=text, removed=removed)
