"""주 호칭 정합 감사(2026-11-06 데굴님 승인) — 재호출 없는 결정론 교정.

실답(web-mw4qaqc3-mx3muj): '다음주 로또사기 좋은 날' 질문에 창(11/8~11/14)·추천일은 맞게 잡고도
본문이 "이번 주에는 … 이번 주는 그러한 보조적인 힘이"처럼 **'이번 주'로 다섯 번** 불렀다.
프롬프트 [택일 결과] 블록의 호칭 고정 문장(2026-10-04)은 중간 블록이라 밀렸다.

규칙:
  ① 교정은 **답의 호칭이 질문보다 앞선 주를 가리킬 때만** — '다음 주' 질문의 '이번 주·금주',
     '다다음 주' 질문의 '이번 주·다음 주'. 질문한 창은 미래 창이고 후보도 그 창의 날만 받았으므로
     앞선 주 호칭은 정당할 수 없다.
  ② 질문이 '이번 주'인데 답이 '다음 주'라 쓴 것 같은 **뒤 주 호칭은 교정하지 않고 센다**
     ("다음 주에 다시 물어보세요" 같은 정당한 전방 지칭일 수 있다).
  ③ 문장에 창 밖 날짜(예: '11월 7일')나 과거 단서('이미 지났', '오늘')가 있으면 그 문장은 건드리지
     않는다 — 실제로 다른 주를 말하는 문장일 수 있다.
  ④ '이번주'(붙여쓰기)·'이번 주말'·'이번 주 중반'도 같은 주를 가리키므로 같이 바꾼다. '주식·주제·
     주문'처럼 '주'가 다른 낱말의 머리인 경우와 '금주(禁酒)하세요'는 제외한다.
로그 `week_label_fixed`(교정) / `week_label_forward_ref`(②, 로그 전용).
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

#: 주 호칭 → 오늘 기준 일 오프셋(time_parser._week_word 와 같은 표).
WEEK_LABEL_OFFSETS: dict[str, int] = {"이번 주": 0, "금주": 0, "다음 주": 7, "다다음 주": 14}

#: 답변 속 주 호칭 — '다다음'을 '다음'보다 먼저. 뒤에는 주 단위 표현에 올 수 있는 꼬리만 허용해
#: '다음 주제·이번 주식·다음 주자·이번 주문' 같은 다른 낱말을 제외한다.
_WEEK_TAIL = (
    r"(?=$|[\s,.!?:;)\]'\"」』]|말|중|간|에|는|은|의|를|도|엔|와|과|나|랑|만|가|이|면|로|라|처럼|보다"
    r"|부터|까지|내내|동안|부로|째)"
)
_WEEK_WORD_RE = re.compile(r"(?P<word>다다음\s*주|다음\s*주|이번\s*주)" + _WEEK_TAIL)
#: '금주' — 禁酒(금주하세요·금주를)와 구분해 주 단위 조사·꼬리가 붙은 경우만.
_GEUMJU_RE = re.compile(r"(?P<word>금주)(?=[에는은의엔]|부터|까지|말|중|간|동안|내내)")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_DATE_RE = re.compile(r"(?:(?P<month>\d{1,2})\s*월\s*)?(?P<day>\d{1,2})\s*일(?![0-9])")
#: 다른 주를 실제로 말하는 문장의 단서 — 이런 문장의 호칭은 판단하지 않는다.
_OTHER_WEEK_CUE_RE = re.compile(r"이미\s*지|지났|지난|끝났|마감됐|오늘")


class WeekLabelAudit(BaseModel):
    """감사 결과 — `text` 는 교정본, `fixes` 는 '이번 주→다음 주' 기록, `forward_refs` 는 ② 관측."""

    text: str
    fixes: list[str]
    forward_refs: list[str]


def _normalize_label(word: str) -> str:
    """'이번주'·'다음  주' → 표 키('이번 주'·'다음 주')."""
    if word == "금주":
        return "금주"
    return re.sub(r"\s*주$", " 주", word)


def _sentence_dates_outside(sentence: str, start: date, end: date) -> bool:
    """문장에 명시된 날짜 중 창 밖인 것이 있는가.

    '11월 7일'은 창의 연도로, 달 없는 '7일'은 창이 걸친 달들 중 어느 하나라도 창 안이면 안으로 본다.
    """
    months = sorted({start.month, end.month})
    year = start.year
    for m in _DATE_RE.finditer(sentence):
        day = int(m.group("day"))
        if m.group("month"):
            cand_months = [int(m.group("month"))]
        else:
            cand_months = months
        inside = False
        for mon in cand_months:
            # 연말 걸침(12월→1월)이면 시작 달 이전 달은 종료 연도로 본다.
            y = year if mon >= start.month else end.year
            try:
                d = date(y, mon, day)
            except ValueError:
                continue
            if start <= d <= end:
                inside = True
                break
        if not inside:
            return True
    return False


def audit_week_labels(
    answer: str, asked_label: str | None, start: str | None, end: str | None,
) -> WeekLabelAudit:
    """질문의 주 호칭과 다른 답변 호칭을 바로잡는다.

    Args:
        answer: LLM 답변.
        asked_label: 질문의 주 호칭(TimeRange.week_label — '이번 주'|'다음 주'|'다다음 주').
        start: 질문 창 시작일(ISO). 창 밖 날짜 문장 보호에 쓴다.
        end: 질문 창 종료일(ISO).

    Returns:
        교정본과 기록. 호칭이 없거나 창이 불완전하면 원문 그대로.
    """
    if not answer or not asked_label or asked_label not in WEEK_LABEL_OFFSETS:
        return WeekLabelAudit(text=answer, fixes=[], forward_refs=[])
    try:
        w_start, w_end = date.fromisoformat(start or ""), date.fromisoformat(end or "")
    except ValueError:
        return WeekLabelAudit(text=answer, fixes=[], forward_refs=[])
    asked_offset = WEEK_LABEL_OFFSETS[asked_label]
    fixes: list[str] = []
    forward_refs: list[str] = []

    def _fix_sentence(sentence: str) -> str:
        if _OTHER_WEEK_CUE_RE.search(sentence) or _sentence_dates_outside(sentence, w_start, w_end):
            return sentence

        def _sub(m: re.Match[str]) -> str:
            word = m.group("word")
            label = _normalize_label(word)
            offset = WEEK_LABEL_OFFSETS[label]
            if offset < asked_offset:
                fixes.append(f"{word}→{asked_label}")
                return asked_label
            if offset > asked_offset:
                forward_refs.append(word)
            return word

        sentence = _WEEK_WORD_RE.sub(_sub, sentence)
        return _GEUMJU_RE.sub(_sub, sentence)

    # 문장 경계(구두점+공백·줄바꿈)를 보존하며 문장 단위로 판단한다.
    parts = re.split(r"((?<=[.!?])\s+|\n+)", answer)
    rebuilt = [part if i % 2 else _fix_sentence(part) for i, part in enumerate(parts)]
    return WeekLabelAudit(text="".join(rebuilt), fixes=fixes, forward_refs=forward_refs)


def week_label_closing_directive(asked_label: str, start: str, end: str) -> str:
    """프롬프트 말미 고정용 주 호칭 지시 — 중간 [택일 결과] 블록의 같은 문장이 밀리는 결함 보완.

    Args:
        asked_label: 질문의 주 호칭.
        start: 창 시작일(ISO).
        end: 창 종료일(ISO).
    """
    return (
        f"[주 호칭 — 말미 고정] 사용자가 '{asked_label}'라고 부른 기간은 {start} – {end}이다. "
        f"답 전체에서 이 기간은 반드시 '{asked_label}'로만 부른다"
        + (
            " — '이번 주'·'금주'·'이번 주말'로 바꿔 부르면 질문과 다른 주를 말하는 오답이 된다."
            if asked_label != "이번 주"
            else "."
        )
    )
