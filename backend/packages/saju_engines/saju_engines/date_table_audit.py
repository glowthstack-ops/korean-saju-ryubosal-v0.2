"""택일 표 인용 감사(2026-11-16 데굴님 승인) — 로그 전용(답변 불변).

실답(web-mwj26i50): '이번주중 로또사기 좋은 날' 질문에 乙未일(천간 편관·기신, 지지 비견)을
"가장 추천하는 날 … 비견의 기운이 들어와 힘을 실어주는 날"이라고 썼다. 프롬프트에는
'기신 · 십성 편관/비견'이 실려 있었다 — 불리한 천간을 빼고 지지 십성만 골라 쓴 것이다.

같은 유형을 실답에서 세기 위한 관측 감사다. 두 가지를 본다.

  ① 천간 누락(stem_omitted): 표의 날을 말하는 문장이 그날 **지지 십성은 말하고 천간 십성은
     말하지 않았는데**, 그 천간이 기신·구신이다.
  ② 등급 올림(grade_raised): 표에서 [추천]이 아닌 날을 말하는 문장에 추천 표현이 있다
     ('추천하기 어렵다'·'추천 등급' 같은 부정·메타 표현은 제외).

문장을 고치지 않는다 — 어느 십성을 어떻게 덧붙일지는 문맥에 달려 결정론 교정이 문장을 깨기
쉽다. 발생을 줄이는 쪽은 표 사유(천간·지지 십성 병기)·등급 기준 줄·말미 지시가 맡고, 이 감사는
그 뒤에도 남는 건수를 로그(`date_table_audit`)로 남겨 실답 검수의 근거로 쓴다.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from saju_shared_types.llm_input import DateSelectionBlock

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_MONTH_DAY_RE = re.compile(r"(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일(?![0-9])")
_DAY_ONLY_RE = re.compile(r"(?<![0-9월]\s)(?<![0-9])(?P<day>\d{1,2})\s*일(?![0-9])")
_UNFAVORABLE = frozenset({"기신", "구신"})
#: 추천으로 올려 말한 표현 — 부정·메타 표현(_RECOMMEND_NEG_RE)에 걸리는 문장은 제외한다.
_RECOMMEND_RE = re.compile(r"추천|가장\s*좋은\s*날|제일\s*좋은\s*날|으뜸")
_RECOMMEND_NEG_RE = re.compile(
    r"추천(?:하기|드리기|하긴|드리긴)\s*(?:는\s*)?어렵|추천(?:하지|드리지)\s*않|추천\s*등급|"
    r"추천(?:일|할\s*만한\s*날)(?:은|이)?\s*(?:없|아니)|추천(?:은|이)\s*아니"
)


class DateTableAudit(BaseModel):
    """감사 결과 — 두 목록 모두 'YYYY-MM-DD: 문장 앞부분' 꼴(로그용)."""

    stem_omitted: list[str]
    grade_raised: list[str]

    @property
    def clean(self) -> bool:
        """관측된 위반이 없는가."""
        return not (self.stem_omitted or self.grade_raised)


def _sentence_dates(sentence: str, by_md: dict[tuple[int, int], str],
                    by_day: dict[int, str], by_weekday: dict[str, str]) -> set[str]:
    """문장이 가리키는 표의 날(ISO) — '11월 17일' > '17일' > '화요일' 순으로 본다."""
    found: set[str] = set()
    for m in _MONTH_DAY_RE.finditer(sentence):
        iso = by_md.get((int(m.group("month")), int(m.group("day"))))
        if iso:
            found.add(iso)
    if found:
        return found
    for m in _DAY_ONLY_RE.finditer(sentence):
        iso = by_day.get(int(m.group("day")))
        if iso:
            found.add(iso)
    if found:
        return found
    for weekday, iso in by_weekday.items():
        if f"{weekday}요일" in sentence:
            found.add(iso)
    return found


def audit_date_table_answer(answer: str, block: DateSelectionBlock | None) -> DateTableAudit:
    """답변이 택일 표의 등급·십성을 바꿔 말했는지 본다(로그 전용).

    Args:
        answer: 후처리를 마친 답변 본문.
        block: 그 턴에 실린 택일 블록. None 이거나 십성 필드가 빈 표(등급 기준을 쓰지 않는
            목적)는 감사하지 않는다.

    Returns:
        DateTableAudit — 관측된 문장 목록(없으면 둘 다 빈 목록).
    """
    empty = DateTableAudit(stem_omitted=[], grade_raised=[])
    if block is None or not answer or not block.grade_notes:
        return empty
    rows = [r for r in block.rows if r.stem_ten_god and r.branch_ten_god]
    if not rows:
        return empty

    row_by_iso = {r.date: r for r in rows}
    by_md: dict[tuple[int, int], str] = {}
    day_count: dict[int, int] = {}
    weekday_count: dict[str, int] = {}
    for r in rows:
        d = date.fromisoformat(r.date)
        by_md[(d.month, d.day)] = r.date
        day_count[d.day] = day_count.get(d.day, 0) + 1
        weekday_count[r.weekday] = weekday_count.get(r.weekday, 0) + 1
    # 일(日) 숫자·요일은 표 안에서 한 날만 가리킬 때에만 쓴다(한 달 창에서는 요일이 겹친다).
    by_day = {
        date.fromisoformat(r.date).day: r.date
        for r in rows if day_count[date.fromisoformat(r.date).day] == 1
    }
    by_weekday = {r.weekday: r.date for r in rows if weekday_count[r.weekday] == 1}

    stem_omitted: list[str] = []
    grade_raised: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(answer):
        sentence = sentence.strip()
        if not sentence:
            continue
        dates = _sentence_dates(sentence, by_md, by_day, by_weekday)
        if len(dates) != 1:
            continue  # 여러 날을 한 문장에 묶으면 어느 날의 십성·등급인지 가릴 수 없다
        row = row_by_iso[next(iter(dates))]
        head = f"{row.date}: {sentence[:60]}"
        if (
            row.stem_role in _UNFAVORABLE
            and row.stem_ten_god != row.branch_ten_god
            and row.branch_ten_god in sentence
            and row.stem_ten_god not in sentence
        ):
            stem_omitted.append(head)
        if (
            row.recommendation != "recommended"
            and _RECOMMEND_RE.search(sentence)
            and not _RECOMMEND_NEG_RE.search(sentence)
        ):
            grade_raised.append(head)
    return DateTableAudit(stem_omitted=stem_omitted, grade_raised=grade_raised)
