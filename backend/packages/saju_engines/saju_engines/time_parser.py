"""시점 표현 파서 — 18패턴 (v2.2 Phase 3 T3.7, docs/08 C차원 전수).

실측: extracted_period 누락률 79% — 시점은 대부분 텍스트에서 직접 파싱해야 한다.
C1(무시점)~C18(분석 단위 지정)을 모두 처리하며, 패턴 ID는 docs/08과 동일하게 쓴다.

결정론: 같은 (텍스트, 기준일) → 같은 TimeRange. 기준일(today)은 호출 측이 주입한다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from saju_shared_types.intent import (
    AgeRange,
    AnchorDate,
    Granularity,
    LabeledRange,
    TimeRange,
    TimeScope,
)

# C3 일 단위 상대어 — 글피(+3일)까지 사전 등재(docs/08 C3).
_DAY_WORDS = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}
# C13 인생 단계 어휘.
_LIFE_STAGES = {
    "초년": "초년", "중년": "중년", "말년": "말년", "노후": "말년",
    "평생": "평생", "일생": "평생",
}
_HALF = {"상반기": ("01", "06"), "하반기": ("07", "12")}


def parse_time(
    text: str, today: date, birth_year: int | None = None
) -> tuple[TimeRange | None, TimeScope]:
    """텍스트에서 시점 표현을 파싱한다 (C1~C18).

    Args:
        text: 사용자 발화 원문.
        today: 기준일(상대 표현 해석용 — 호출 측 주입).
        birth_year: 나이↔연도 변환용 출생 연도(C12, 없으면 나이만 기록).

    Returns:
        (TimeRange | None, TimeScope). 무시점(C1)이면 (None, TIMELESS) —
        분야별 기본 기간 적용은 Broad Query Rewriter 몫.
    """
    # C16 즉시성 수식 — 다른 패턴과 결합 가능하므로 먼저 추출.
    urgency = "asap" if re.search(r"빠를\s*수록|최대한\s*빨리|빨리\s*좋", text) else None

    # C17 시진(時) 단위 — "시간대" 요청.
    hour_level = bool(re.search(r"시간대|몇\s*시에", text))

    # C18 분석 단위 지정 — "월로 따지면", "일운보다 월운".
    override = re.search(r"(대운|연|월|일|주)\s*(?:운)?\s*(?:으로|로)\s*(?:따지|보)", text)

    # C9 데드라인 — "YYYY년 M월까지 (완료)".
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*까지", text)
    if m:
        deadline = f"{m.group(1)}-{int(m.group(2)):02d}"
        return TimeRange(
            type="deadline", granularity=Granularity.MONTH,
            deadline=deadline, end=deadline, urgency=urgency,
        ), TimeScope.MID_TERM

    # C10 연도 범위 묶음 — "26-27 / 28-30 / 31-33년".
    pairs = re.findall(r"(\d{2})\s*[-~]\s*(\d{2})", text)
    if len(pairs) >= 2 and "년" in text:
        ranges = [
            LabeledRange(
                label=f"{a}-{b}", start=f"20{a}", end=f"20{b}",
            )
            for a, b in pairs
        ]
        return TimeRange(
            type="user_ranges", granularity=Granularity.YEAR, ranges=ranges,
            urgency=urgency,
        ), TimeScope.LONG_TERM

    # C11 외부 일정 앵커 — "투표일이 6월 3일", "발표는 6월 4일".
    m = re.search(r"(투표일|개표|발표|시험일?|면접)[은는이]?\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        label, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
        anchor = AnchorDate(label=label, date=f"{year}-{month:02d}-{day:02d}")
        return TimeRange(
            type="anchor_based", granularity=Granularity.DAY,
            anchor_dates=[anchor], urgency=urgency,
        ), TimeScope.DATE_LEVEL

    # C12 나이 기반 — "20살 전까지", "말년은 몇살부터".
    m = re.search(r"(\d{1,3})\s*살\s*(전까지|까지|부터|이후)", text)
    if m:
        age_num = int(m.group(1))
        suffix = m.group(2)
        age = (
            AgeRange(to_age=age_num) if suffix in ("전까지", "까지")
            else AgeRange(from_age=age_num)
        )
        start = end = None
        if birth_year is not None:  # 나이↔연도 변환(세는나이 모호 → 만나이 기준 산출)
            year = birth_year + age_num
            start, end = (None, str(year)) if age.to_age else (str(year), None)
        return TimeRange(
            type="age_based", granularity=Granularity.YEAR, age=age,
            start=start, end=end, urgency=urgency,
        ), TimeScope.LIFE_STAGE

    # C13 인생 단계.
    for word, stage in _LIFE_STAGES.items():
        if word in text:
            return TimeRange(
                type="relative", granularity=Granularity.DAEWOON,
                life_stage=stage, urgency=urgency,
            ), TimeScope.LIFE_STAGE

    # C14 대운 단위.
    if re.search(r"(다음|이번|현재)\s*대운|대운\s*교운", text):
        return TimeRange(
            type="relative", granularity=Granularity.DAEWOON, urgency=urgency,
        ), TimeScope.DAEWOON_UNIT

    # C15 과거 개방형(역검증) — "언제인지 맞춰봐", "왜 힘들었을까".
    if re.search(r"맞춰\s*봐|왜\s*힘들었|언제인지\s*맞", text):
        return TimeRange(
            type="open_when", granularity=Granularity.YEAR, urgency=urgency,
        ), TimeScope.PAST

    # C8b 과거 상대 기간 — "지난 1년(내)", "최근 6개월", "지난 반년"(2026-06-12 추가).
    # 현재 달 포함 직전 N개월 창(미래 롤링과 대칭). '재취업한 달은 언제' 류 과거 회고용.
    m = re.search(r"(지난|최근)\s*(\d+)?\s*(개월|달|년|반년)", text)
    # 숫자 없는 '지난달/지난해' 단수 표현은 별개 의미 — 이 규칙은 N 명시·반년만 처리.
    if m and (m.group(2) or m.group(3) == "반년"):
        n_raw, unit = m.group(2), m.group(3)
        months = (
            6 if unit == "반년"
            else int(n_raw) * (12 if unit == "년" else 1)
        )
        end_y, end_m = today.year, today.month
        idx = (end_y * 12 + end_m - 1) - (months - 1)
        start_y, start_m = idx // 12, idx % 12 + 1
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=f"{start_y}-{start_m:02d}", end=f"{end_y}-{end_m:02d}",
            urgency=urgency,
        ), TimeScope.PAST

    # C8 상대 기간 — "6개월 안에", "3개월 이내", "1년 안으로", "향후 30년".
    m = re.search(r"(\d+)\s*(개월|달|년)\s*(안에|이내|안으로|이내에)?", text)
    if m and (m.group(3) or re.search(r"향후|앞으로", text)):
        n, unit = int(m.group(1)), m.group(2)
        days = n * 30 if unit in ("개월", "달") else n * 365
        scope = TimeScope.SHORT_TERM if days <= 200 else (
            TimeScope.MID_TERM if days <= 800 else TimeScope.LONG_TERM
        )
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            end_offset_days=days, start=today.isoformat(), urgency=urgency,
        ), scope

    # C3 일 단위 상대어 (글피 포함).
    for word, offset in _DAY_WORDS.items():
        if word in text:
            target = today + timedelta(days=offset)
            return TimeRange(
                type="relative", granularity=Granularity.DAY,
                start=target.isoformat(), end=target.isoformat(), urgency=urgency,
            ), TimeScope.DATE_LEVEL

    # C4 주 단위.
    if re.search(r"이번\s*주|다음\s*주|금주", text):
        offset = 7 if re.search(r"다음\s*주", text) else 0
        monday = today - timedelta(days=today.weekday()) + timedelta(days=offset)
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=monday.isoformat(), end=(monday + timedelta(days=6)).isoformat(),
            urgency=urgency,
        ), TimeScope.SHORT_TERM

    # C7 반기 (특정월보다 먼저 — "하반기"가 월 표현과 혼동되지 않게).
    for word, (m1, m2) in _HALF.items():
        if word in text:
            ym = re.search(r"(20\d{2})\s*년", text)
            year = int(ym.group(1)) if ym else today.year + (1 if "내년" in text else 0)
            return TimeRange(
                type="absolute", granularity=Granularity.MONTH,
                start=f"{year}-{m1}", end=f"{year}-{m2}", urgency=urgency,
            ), TimeScope.MID_TERM

    # C5 월 단위 — "5월", "이번달", "다음 달". 당해 연도 기준(실로그 B2 "5월은 어때?"가
    # 6월 발화에서도 같은 해 5월과의 비교 맥락) — "내년" 명시 시에만 +1.
    m = re.search(r"(\d{1,2})\s*월", text)
    if m and not re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text):
        month = int(m.group(1))
        ym = re.search(r"(20\d{2})\s*년", text)
        year = int(ym.group(1)) if ym else today.year + (1 if "내년" in text else 0)
        key = f"{year}-{month:02d}"
        return TimeRange(
            type="absolute", granularity=Granularity.MONTH,
            start=key, end=key, urgency=urgency,
        ), TimeScope.SHORT_TERM
    if re.search(r"이번\s*달|이달", text):
        key = f"{today.year}-{today.month:02d}"
        return TimeRange(
            type="relative", granularity=Granularity.MONTH, start=key, end=key,
            urgency=urgency,
        ), TimeScope.SHORT_TERM
    if re.search(r"다음\s*달|내달", text):
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        key = f"{nxt.year}-{nxt.month:02d}"
        return TimeRange(
            type="relative", granularity=Granularity.MONTH, start=key, end=key,
            urgency=urgency,
        ), TimeScope.SHORT_TERM

    # C6 연 단위 — "올해", "내년", "2027년".
    m = re.search(r"(20\d{2})\s*년", text)
    if m:
        year_key = m.group(1)
        return TimeRange(
            type="absolute", granularity=Granularity.YEAR, start=year_key, end=year_key,
            urgency=urgency,
        ), TimeScope.MID_TERM
    if "올해" in text or "금년" in text:
        year_key = str(today.year)
        return TimeRange(
            type="relative", granularity=Granularity.YEAR, start=year_key, end=year_key,
            urgency=urgency,
        ), TimeScope.MID_TERM
    if "내년" in text:
        year_key = str(today.year + 1)
        return TimeRange(
            type="relative", granularity=Granularity.YEAR, start=year_key, end=year_key,
            urgency=urgency,
        ), TimeScope.MID_TERM

    # C2 개방형 "언제".
    if "언제" in text:
        granularity = Granularity.HOUR if hour_level else Granularity.MONTH
        return TimeRange(
            type="open_when", granularity=granularity, urgency=urgency,
        ), TimeScope.MID_TERM

    # C17/C18 단독 — 시간대/단위 지정만 있는 경우.
    if hour_level:
        return TimeRange(
            type="relative", granularity=Granularity.HOUR, urgency=urgency,
        ), TimeScope.HOUR_LEVEL
    if override:
        unit = {"대운": Granularity.DAEWOON, "연": Granularity.YEAR,
                "월": Granularity.MONTH, "일": Granularity.DAY,
                "주": Granularity.DAY}[override.group(1)]
        return TimeRange(
            type="relative", granularity=unit, granularity_override=True,
            urgency=urgency,
        ), TimeScope.MID_TERM

    # C1 무시점 — 분야 기본 기간은 Rewriter가 적용.
    return None, TimeScope.TIMELESS
