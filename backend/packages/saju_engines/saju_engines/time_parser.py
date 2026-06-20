"""시점 표현 파서 — 18패턴 (v2.2 Phase 3 T3.7, docs/08 C차원 전수).

실측: extracted_period 누락률 79% — 시점은 대부분 텍스트에서 직접 파싱해야 한다.
C1(무시점)~C18(분석 단위 지정)을 모두 처리하며, 패턴 ID는 docs/08과 동일하게 쓴다.

결정론: 같은 (텍스트, 기준일) → 같은 TimeRange. 기준일(today)은 호출 측이 주입한다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from saju_manse_analysis.luck.luck_calendar import shift_month_label

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
# C3.5 요일 — Python weekday()(월=0 … 일=6). '다음주 월요일'은 특정 일운(주 전체 아님).
_WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
# C13 인생 단계 어휘.
_LIFE_STAGES = {
    "초년": "초년", "중년": "중년", "말년": "말년", "노후": "말년",
    "평생": "평생", "일생": "평생",
}
_HALF = {"상반기": ("01", "06"), "하반기": ("07", "12")}


def parse_time(
    text: str,
    today: date,
    birth_year: int | None = None,
    current_month_label: str | None = None,
) -> tuple[TimeRange | None, TimeScope]:
    """텍스트에서 시점 표현을 파싱한다 (C1~C18).

    Args:
        text: 사용자 발화 원문.
        today: 기준일(상대 표현 해석용 — 호출 측 주입).
        birth_year: 나이↔연도 변환용 출생 연도(C12, 없으면 나이만 기록).
        current_month_label: 오늘이 속한 절기 월운 라벨(YYYY-MM). 주입 시 '이번 달'·
            '다음 달'·미래/과거 롤링 창의 기준 달을 절기 기준으로 잡는다. 미주입 시
            양력 ``today.month`` 폴백(절기 경계 직전 구간에서 한 달 어긋날 수 있음).

    Returns:
        (TimeRange | None, TimeScope). 무시점(C1)이면 (None, TIMELESS) —
        분야별 기본 기간 적용은 Broad Query Rewriter 몫.
    """
    # 절기 기준 '당월' 라벨 — 주입 없으면 양력 폴백(경계 직전 한 달 어긋남 감수).
    this_month = current_month_label or f"{today.year}-{today.month:02d}"
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
        end_label = this_month  # 현재(절기) 달 포함
        start_label = shift_month_label(end_label, -(months - 1))
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=start_label, end=end_label,
            urgency=urgency,
        ), TimeScope.PAST

    # C8a 미래 상대 기간 — "향후 5년", "앞으로 N개월(간)", "다가오는 3년"(2026-06-14).
    # 현재 달부터 N×12(년)/N(개월) 롤링 미래 창. '앞으로 5년 이사운 월별' 등에서 N을
    # 살린다(기존 C8 offset·롤링 12개월 고정이 N을 무시해 2026만 답하던 결함 수정).
    m = re.search(r"(향후|앞으로|다가오는)\s*(\d+)\s*(개월|달|년)", text)
    if m:
        n, unit = int(m.group(2)), m.group(3)
        months = n * 12 if unit == "년" else n
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=this_month,
            end=shift_month_label(this_month, months - 1), urgency=urgency,
        ), (TimeScope.LONG_TERM if months > 24 else TimeScope.MID_TERM)

    # C8c 미래 상대 시작 앵커 — "1년 이후(부터)", "6개월 후", "2년 뒤"(2026-06-18 추가).
    # '현재 계약 1년 뒤부터 다음 이사 언제'처럼 미래의 특정 시점'부터' 탐색을 시작한다. C8의
    # '~안에/이내'(현재~N 구간)와 달리 '~이후/후/뒤'는 그 시점부터 미래 개방이므로 start를
    # 미래로 앵커한다(미앵커 시 open_when=과거 회고로 오분류돼 과거 달이 답으로 나오던 결함 수정).
    m = re.search(r"(\d+)\s*(개월|달|년)\s*(?:이후|후|뒤)(?:\s*부터)?", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        months = n * 12 if unit == "년" else n
        start_label = shift_month_label(this_month, months)
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=f"{start_label}-01", urgency=urgency,
        ), (TimeScope.LONG_TERM if months > 24 else TimeScope.MID_TERM)

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

    # C3.5 요일 — '다음주 월요일'·'이번주 금요일'·'월요일'은 단일 일운(주 전체 아님).
    wd = re.search(r"(?:(이번|다음|금)\s*주\s*)?([월화수목금토일])요일", text)
    if wd:
        week_word, day_ch = wd.group(1), wd.group(2)
        monday = today - timedelta(days=today.weekday())
        if week_word == "다음":
            monday += timedelta(days=7)
        target = monday + timedelta(days=_WEEKDAYS[day_ch])
        # 주 지정어 없이 지난 요일이면 다가오는 같은 요일로(예: 오늘이 화요일인데 '월요일').
        if week_word is None and target < today:
            target += timedelta(days=7)
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=target.isoformat(), end=target.isoformat(), urgency=urgency,
        ), TimeScope.DATE_LEVEL

    # C4b 한 주(롤링 7일) — '한주간/일주일/앞으로·다음·향후·이번 한 주'는 오늘부터 7일 창.
    #     ('이번 주/다음 주/금주'는 아래 C4가 월~일 캘린더 주로 처리한다.) 과거형(지난/저번/
    #     최근)은 제외 — 그 경우는 과거 롤링/회고 규칙이 잡는다. '다음 한주간'이 '다음\s*주'에
    #     안 걸려 '시점 미지정'으로 새던 결함 수정(2026-06-20 데굴님 — 월운이 지난달로 노출).
    if re.search(r"한\s*주\s*간|한\s*주|일\s*주\s*일", text) and not re.search(
        r"지난|저번|최근|지지난", text
    ):
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=today.isoformat(), end=(today + timedelta(days=6)).isoformat(),
            urgency=urgency,
        ), TimeScope.SHORT_TERM

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

    # C5b 특정 일자(+이후/부터) — "7월 4일 이후(로)", "8월 1일부터", "2026년 7월 4일 이후".
    # 택일(E10)의 시작 앵커. '이후/부터'면 개방형(end=None — 호출 측이 탐색 윈도우 결정),
    # 없으면 단일 일운. C5 월 규칙이 'N월 N일'을 가드로 제외해 날짜가 통째 소실되던 결함 수정
    # (2026-06-16 사용자 지적 — "7월 4일 이후 이사일"이 6월 답으로 축소). C11(외부 일정 앵커:
    # 투표일·면접 등)·C9(데드라인 'M월까지')는 앞서 매칭되므로 충돌하지 않는다.
    m = re.search(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(이후로?|부터)?", text)
    if m:
        yr_explicit = m.group(1)
        yr = int(yr_explicit) if yr_explicit else today.year + (1 if "내년" in text else 0)
        mo, dy = int(m.group(2)), int(m.group(3))
        try:
            anchor_d: date | None = date(yr, mo, dy)
        except ValueError:  # 2월 30일 등 비정상 날짜는 무시(다음 규칙으로 통과)
            anchor_d = None
        if anchor_d is not None:
            # 연도 미지정인데 이미 지난 날짜면 내년으로(미래 택일 의도). 명시 연도는 그대로 존중.
            if yr_explicit is None and "내년" not in text and anchor_d < today:
                anchor_d = date(yr + 1, mo, dy)
            # '시간대'(C17) 동반이면 시진 단위 — 단, 날짜 앵커는 유지(로또 실행 패키지 등).
            # '이후/부터'면 개방형(end=None) — 시진 단위는 특정일 고정이라 단일 앵커.
            open_ended = m.group(4) is not None and not hour_level
            return TimeRange(
                type="absolute",
                granularity=Granularity.HOUR if hour_level else Granularity.DAY,
                start=anchor_d.isoformat(),
                end=None if open_ended else anchor_d.isoformat(),
                urgency=urgency,
            ), TimeScope.SHORT_TERM

    # C5 월 단위 — "5월", "이번달", "다음 달". 당해 연도 기준(실로그 B2 "5월은 어때?"가
    # 6월 발화에서도 같은 해 5월과의 비교 맥락) — "내년" 명시 시에만 +1.
    # 다중 월 비교("8월과 10월 중 언제가 나아?")는 두 달을 모두 잡아 min~max 구간으로 스팬한다
    # — 첫 달만 잡혀 한쪽만 후보·근거가 붙던 비대칭 비교 결함을 차단(2026-06-16 사용자 지적).
    months_found = re.findall(r"(\d{1,2})\s*월", text)
    if months_found and not re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text):
        ym = re.search(r"(20\d{2})\s*년", text)
        year = int(ym.group(1)) if ym else today.year + (1 if "내년" in text else 0)
        month_nums = sorted({int(x) for x in months_found if 1 <= int(x) <= 12})
        if len(month_nums) >= 2:  # 다중 시점 비교 — 양 끝 달 포함 구간(둘 다 후보·근거 확보)
            return TimeRange(
                type="absolute", granularity=Granularity.MONTH,
                start=f"{year}-{month_nums[0]:02d}", end=f"{year}-{month_nums[-1]:02d}",
                urgency=urgency,
            ), TimeScope.MID_TERM
        key = f"{year}-{month_nums[0]:02d}"
        return TimeRange(
            type="absolute", granularity=Granularity.MONTH,
            start=key, end=key, urgency=urgency,
        ), TimeScope.SHORT_TERM
    # C5.0 올해 남은 달 — "올해 남은 달들", "남은 개월", "연말까지". 당월(절기)~연말 월별 스팬.
    # '이번달' 단수 규칙(아래)이 먼저 잡아 당월만 답하던 결함 차단(2026-06-16 사용자 지적).
    # 연말 고정 종료라 미래 롤링(C8a 향후 N개월)과 구분되며, '내년'은 연 규칙(C6)에 양보.
    if "내년" not in text and re.search(
        r"남은\s*(?:달|개월|기간)|올해\s*남은|연말\s*까지|올해\s*말\s*까지", text
    ):
        cur_year = int(this_month[:4])
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=this_month, end=f"{cur_year}-12", urgency=urgency,
        ), TimeScope.MID_TERM
    if re.search(r"이번\s*달|이달", text):
        key = this_month  # 절기 기준 당월(주입 없으면 양력 폴백)
        return TimeRange(
            type="relative", granularity=Granularity.MONTH, start=key, end=key,
            urgency=urgency,
        ), TimeScope.SHORT_TERM
    if re.search(r"다음\s*달|내달", text):
        key = shift_month_label(this_month, 1)  # 당월(절기)의 다음 달
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
    if "내후년" in text:
        year_key = str(today.year + 2)
        return TimeRange(
            type="relative", granularity=Granularity.YEAR, start=year_key, end=year_key,
            urgency=urgency,
        ), TimeScope.MID_TERM

    # C6b 축약 연도 — "27년", "28년의 이사운"(2026-06-14). 2자리 연도를 20NN으로 해석
    # (사주 미래 질의 편향: 00~69→2000년대, 70~99→1900년대 생년/과거). 앞에 숫자가 없고
    # (4자리 연도의 일부 제외) 뒤에 기간 어미(후·뒤·동안·간·내·째·차)가 없을 때만 — 'N년 후/간'
    # 같은 기간 표현과 충돌 방지(그건 C8/C8a가 처리).
    m = re.search(r"(?<!\d)(\d{2})\s*년(?!\s*(?:후|뒤|동안|간|내|째|차))", text)
    if m:
        yy = int(m.group(1))
        year_key = str(2000 + yy if yy <= 69 else 1900 + yy)
        return TimeRange(
            type="absolute", granularity=Granularity.YEAR, start=year_key, end=year_key,
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


def bucket_to_range(
    label: str, today: date, current_month_label: str | None = None
) -> tuple[TimeRange | None, TimeScope]:
    """시점 버킷(TimeBucketClassifier 출력) → 결정론 TimeRange. today 기준 계산.

    합성 버킷(rolling_week·rolling_month·this_month·next_month·this_year·next_year)만
    범위를 만들고, vague_future·past_retro·timeless·미등록은 (None, TIMELESS)로 둔다(합성하지
    않고 다운스트림이 처리 — 막연 미래/과거 회고/구조 질문 경로 보존). 규칙 파서가 시점을 못
    잡았을 때만 호출되는 보조 경로다(rules-first).
    """
    this_month = current_month_label or f"{today.year}-{today.month:02d}"
    if label == "rolling_week":
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=today.isoformat(), end=(today + timedelta(days=6)).isoformat(),
        ), TimeScope.SHORT_TERM
    if label == "rolling_month":
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=today.isoformat(), end=(today + timedelta(days=30)).isoformat(),
        ), TimeScope.MID_TERM
    if label == "this_month":
        return TimeRange(
            type="relative", granularity=Granularity.MONTH,
            start=this_month, end=this_month,
        ), TimeScope.SHORT_TERM
    if label == "next_month":
        key = shift_month_label(this_month, 1)
        return TimeRange(
            type="relative", granularity=Granularity.MONTH, start=key, end=key,
        ), TimeScope.SHORT_TERM
    if label == "this_year":
        year_key = str(today.year)
        return TimeRange(
            type="relative", granularity=Granularity.YEAR, start=year_key, end=year_key,
        ), TimeScope.MID_TERM
    if label == "next_year":
        year_key = str(today.year + 1)
        return TimeRange(
            type="relative", granularity=Granularity.YEAR, start=year_key, end=year_key,
        ), TimeScope.MID_TERM
    return None, TimeScope.TIMELESS
