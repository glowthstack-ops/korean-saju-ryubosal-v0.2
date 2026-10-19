"""택일 답변 결정론 감사 2종(2026-10-19 데굴님 승인) — 회피 구간·마무리 질문 뒤 문장.

① 회피 구간: 실답(web-mvf73q3h)이 엔진 회피일(10/19·21·22·23·24)을
   "10월 19일부터 24일까지는 … 피하라"로 묶어 그 사이 **엔진 추천일 10/20** 까지
   피하라고 했다. 답의 'A일부터 B일까지' 회피 구간에 추천·무난 일이 끼면 구간을
   엔진 회피일 목록으로 다시 쓴다(추천일이 없으면 손대지 않는다).
② 마무리 질문 뒤 문장: 시스템 규칙 8(물음표 문장은 마지막 하나)인데 질문 뒤에
   "여기서부터 다음 운이 풀릴 것으로 보입니다" 같은 문장이 붙었다. 마지막 질문 뒤의
   짧은 꼬리(2문장·150자 이하)만 지운다.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

_AVOID_CUE_RE = re.compile(r"피하|피해|회피|미루|조심|삼가|자제|좋지\s*않")
_RANGE_RE = re.compile(
    r"(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일\s*(?:부터|~|∼|-)\s*"
    r"(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일\s*(?:까지)?(는|은|에는|에|사이는|사이에는|사이)?"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class DateAnswerAudit(BaseModel):
    """감사 결과."""

    text: str
    rewritten: list[str]


def _ko_day_list(days: list[date]) -> str:
    """같은 달은 월을 한 번만 — '10월 19일, 21일, 22일'."""
    parts: list[str] = []
    prev_month: int | None = None
    for d in days:
        parts.append(f"{d.month}월 {d.day}일" if d.month != prev_month else f"{d.day}일")
        prev_month = d.month
    return ", ".join(parts)


def rewrite_avoid_ranges(
    answer: str,
    recommended: list[str],
    avoid: list[str],
    year: int,
) -> DateAnswerAudit:
    """회피 구간에 추천일이 끼면 그 구간을 회피일 목록으로 바꾼다.

    Args:
        answer: LLM 답변.
        recommended: 엔진 추천·무난 일자(ISO).
        avoid: 엔진 회피일(ISO).
        year: 월·일만 적힌 날짜의 연도(택일 창 시작 연도).
    """
    if not answer or not recommended or not avoid:
        return DateAnswerAudit(text=answer, rewritten=[])
    rec = {date.fromisoformat(d) for d in recommended}
    avo = sorted(date.fromisoformat(d) for d in avoid)
    rewritten: list[str] = []
    out_sents: list[str] = []

    def _fix(sent: str) -> str:
        if not _AVOID_CUE_RE.search(sent):
            return sent
        def _sub(m: re.Match[str]) -> str:
            m1 = int(m.group(1)) if m.group(1) else None
            d1 = int(m.group(2))
            m2 = int(m.group(3)) if m.group(3) else m1
            d2 = int(m.group(4))
            if m1 is None or m2 is None:
                return m.group(0)
            try:
                lo, hi = date(year, m1, d1), date(year, m2, d2)
            except ValueError:
                return m.group(0)
            if hi < lo or not any(lo <= r <= hi for r in rec):
                return m.group(0)
            inside = [a for a in avo if lo <= a <= hi]
            if not inside:
                return m.group(0)
            particle = m.group(5) or ""
            tail = "은" if particle in ("는", "은", "사이는") else ("에는" if particle else "")
            rewritten.append(m.group(0).strip())
            return _ko_day_list(inside) + tail
        return _RANGE_RE.sub(_sub, sent)

    for para in answer.split("\n"):
        fixed = " ".join(_fix(s) for s in _SENTENCE_SPLIT_RE.split(para)) if para else para
        out_sents.append(fixed)
    if not rewritten:
        return DateAnswerAudit(text=answer, rewritten=[])
    return DateAnswerAudit(text="\n".join(out_sents), rewritten=rewritten)


def strip_after_closing_question(answer: str) -> DateAnswerAudit:
    """마지막 질문 문장 뒤의 짧은 꼬리를 지운다(규칙 8 — 물음표 문장이 맨 끝)."""
    if not answer or "?" not in answer:
        return DateAnswerAudit(text=answer, rewritten=[])
    body = answer.rstrip()
    q_end = body.rfind("?")
    raw_tail = body[q_end + 1:]
    tail = raw_tail.strip()
    if not tail:
        return DateAnswerAudit(text=answer, rewritten=[])
    # 질문과 같은 문단에 이어 붙은 문장만 대상 — 줄을 바꾼 고지
    # ('※ 관계 신호는 시험(beta) 관측치예요') 같은 시스템 마감 줄은 지우지 않는다
    # (2026-10-19 통합 테스트로 확인).
    if "\n" in raw_tail or tail.startswith("※"):
        return DateAnswerAudit(text=answer, rewritten=[])
    tail_sents = [s for s in _SENTENCE_SPLIT_RE.split(tail) if s.strip()]
    # 마지막 질문이 답 끝부분(뒤 400자 안)에 있고 꼬리가 짧을 때만 — 본문 중간 질문은 대상 아님.
    if len(tail) > 150 or len(tail_sents) > 2 or len(body) - q_end > 400:
        return DateAnswerAudit(text=answer, rewritten=[])
    return DateAnswerAudit(text=body[: q_end + 1], rewritten=[tail[:80]])
