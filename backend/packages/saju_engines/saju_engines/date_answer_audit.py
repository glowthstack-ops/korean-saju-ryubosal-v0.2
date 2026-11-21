"""택일 답변 결정론 감사 2종(2026-10-19 데굴님 승인) — 회피 구간·마무리 질문.

① 회피 구간: 실답(web-mvf73q3h)이 엔진 회피일(10/19·21·22·23·24)을
   "10월 19일부터 24일까지는 … 피하라"로 묶어 그 사이 **엔진 추천일 10/20** 까지
   피하라고 했다. 답의 'A일부터 B일까지' 회피 구간에 추천·무난 일이 끼면 구간을
   엔진 회피일 목록으로 다시 쓴다(추천일이 없으면 손대지 않는다).
② 마무리 질문 제거(2026-11-21 데굴님 "… 같은 추가질문은 더이상 하지 않도록 해줘"):
   시스템 규칙 8 이 '답을 질문으로 끝내지 않는다'로 바뀌었다. 지시만으로는 모델이 가끔
   어기므로, 답의 마지막 본문 문단 끝부분(뒤 3문장)에 남은 질문 문장을 지운다. 질문 뒤에
   붙은 평서문(정리·행동 문장)은 남긴다 — 종전 감사(2026-10-19)는 반대로 질문을 남기고
   그 뒤 꼬리 문장을 지웠다(그때는 규칙 8 이 '물음표 문장은 마지막 하나'였다).
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


#: 문장 끝 물음표(닫는 따옴표·괄호가 뒤따라도 질문으로 본다).
_QUESTION_END_RE = re.compile(r"[?？][\"'”’)\]]*$")
_CLOSING_SPLIT_RE = re.compile(r"(?<=[.!?。？])\s+")
#: 마지막 본문 문단에서 질문을 찾는 범위(뒤에서부터 문장 수) — 본문 중간 질문은 대상이 아니다.
_CLOSING_TAIL_SENTENCES = 3
#: 질문을 지우고 남는 본문이 이보다 짧으면 손대지 않는다 — 답 전체가 짧은 확인 질문인 경우다.
_MIN_REMAINING_CHARS = 80
_NOTICE_PREFIX = "※"


def strip_closing_question(answer: str) -> DateAnswerAudit:
    """답 끝부분의 질문 문장을 지운다(규칙 8 — 답을 질문으로 끝내지 않는다).

    마지막 본문 문단(끝의 빈 줄·`※` 고지 줄은 건너뛴다)의 뒤 3문장 안에서 물음표로 끝나는
    문장만 지우고, 그 사이·뒤의 평서문은 그대로 둔다. 문단이 질문뿐이면 문단째 지운다.

    Args:
        answer: LLM 답변(앞 단계 후처리를 마친 본문).

    Returns:
        `text` = 질문을 지운 답변, `rewritten` = 지운 질문 문장(없으면 빈 목록 — 원문 유지).
    """
    if not answer or ("?" not in answer and "？" not in answer):
        return DateAnswerAudit(text=answer, rewritten=[])
    lines = answer.rstrip().split("\n")
    idx = len(lines) - 1
    while idx >= 0 and (
        not lines[idx].strip() or lines[idx].lstrip().startswith(_NOTICE_PREFIX)
    ):
        idx -= 1
    if idx < 0:
        return DateAnswerAudit(text=answer, rewritten=[])
    sents = [x for x in _CLOSING_SPLIT_RE.split(lines[idx].strip()) if x.strip()]
    cut = max(0, len(sents) - _CLOSING_TAIL_SENTENCES)
    kept_tail = [x for x in sents[cut:] if not _QUESTION_END_RE.search(x.strip())]
    removed = [x for x in sents[cut:] if _QUESTION_END_RE.search(x.strip())]
    if not removed:
        return DateAnswerAudit(text=answer, rewritten=[])
    paragraph = " ".join(sents[:cut] + kept_tail)
    head = lines[:idx] + ([paragraph] if paragraph else [])
    while head and not head[-1].strip():
        head.pop()
    if len("\n".join(head).strip()) < _MIN_REMAINING_CHARS:
        return DateAnswerAudit(text=answer, rewritten=[])
    notice = lines[idx + 1:]
    while notice and not notice[0].strip():
        notice.pop(0)
    out = head + ([""] + notice if notice else [])
    return DateAnswerAudit(text="\n".join(out), rewritten=[x[:80] for x in removed])
