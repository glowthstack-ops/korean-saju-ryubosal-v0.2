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
    TimeConstraintItem,
    TimeConstraintRole,
    TimeRange,
    TimeScope,
)

# C3 일 단위 상대어 — 글피(+3일)까지 사전 등재(docs/08 C3).
_DAY_WORDS = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}
#: 같은 어휘를 서술 쪽(프롬프트의 날짜 지칭)에서도 쓴다 — 파싱과 서술이 다른 말을 쓰면
#: 사용자가 '모레'라고 물었는데 답은 '2일 뒤'라고 부르는 어긋남이 생긴다(2026-08-06).
DAY_WORD_OFFSETS: dict[str, int] = _DAY_WORDS
# C3.5 요일 — Python weekday()(월=0 … 일=6). '다음주 월요일'은 특정 일운(주 전체 아님).
_WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
# C13 인생 단계 어휘.
_LIFE_STAGES = {
    "초년": "초년", "중년": "중년", "말년": "말년", "노후": "말년",
    "평생": "평생", "일생": "평생",
}
_HALF = {"상반기": ("01", "06"), "하반기": ("07", "12")}
# C5b 슬래시/대시 날짜 — "6/17", "6-17", "2026-06-17"(선택 연도). 뒤에 숫자·구분자가
# 이어지거나(긴 수열) 기간·범위 단위(월/년/주/개월/시간/살/분/초/%)가 붙으면 제외해
# "8-10월"(월 범위)·"3-4년" 등 오인을 막는다. 일(日)·'에'·'이후/부터'는 허용.
_SLASH_DATE_RE = re.compile(
    r"(?:(20\d{2})\s*[/\-.]\s*)?(\d{1,2})\s*[/\-]\s*(\d{1,2})"
    r"(?![\d/\-.])(?!\s*(?:월|년|주|개월|시간|살|분|초|%))"
    r"\s*(이후로?|부터)?"
)
# 과거시제 표지 — 있으면 연도 미지정 과거 날짜를 '내년 택일'로 밀지 않고 그 해(과거)로 둔다
# ("6/17에 계약했는데" → 2026-06-17). 미래 택일("7월 4일 이사하려고")은 표지가 없어 영향 없음.
_PAST_TENSE_RE = re.compile(r"했|찍었|샀|봤|갔|왔|였|었[어은는을다나]|지났|끝났|난\s*뒤")


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

    # C12 나이 기반(2026-07-23 확장 — 사용자 제시 나이대를 기준 창으로 풀이).
    # ①경계형: "20살 전까지", "40세부터" ②단일/근사형: "88세쯤", "70살에"
    # ③십년대: "60대(초반/중반/후반)" ④한자어: 환갑/칠순/팔순 등.
    # 세는나이 모호 → 만나이 기준 산출(기존 계약 유지), 근사어(쯤/무렵/즈음/
    # 경)는 ±1년 창. birth_year 없으면 AgeRange만 남긴다(하류 확인 질문용).
    m = re.search(r"(\d{1,3})\s*[살세]\s*(전까지|까지|부터|이후)", text)
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

    # C12-b 십년대 — "60대", "60대 초반/중반/후반"(만나이 십년 창).
    m = re.search(r"([1-9]\d?)0\s*대(?!\s*운)\s*(초반|중반|후반)?", text)
    if m:
        base = int(m.group(1)) * 10
        band = m.group(2)
        lo_off, hi_off = {"초반": (0, 3), "중반": (4, 6),
                          "후반": (7, 9)}.get(band, (0, 9))
        # 경계를 지역변수로 유지한다 — AgeRange 의 두 경계는 optional 이고('20살
        # 전까지' 처럼 한쪽만 오는 질의 때문), 모델에서 되읽으면 None 가능성이 붙는다.
        lo_age, hi_age = base + lo_off, base + hi_off
        age = AgeRange(from_age=lo_age, to_age=hi_age)
        start = end = None
        if birth_year is not None:
            start = str(birth_year + lo_age)
            end = str(birth_year + hi_age)
        return TimeRange(
            type="age_based", granularity=Granularity.YEAR, age=age,
            start=start, end=end, urgency=urgency,
        ), TimeScope.LIFE_STAGE

    # C12-c 단일·근사 나이 — "88세쯤", "70살에", "88세" (경계 접미사 없음).
    # 근사어(쯤/무렵/즈음/경)는 ±1년 창, 그 외 단일 연도.
    m = re.search(r"(\d{1,3})\s*[살세](?:\s*(쯤|무렵|즈음|경))?", text)
    if m and 1 <= int(m.group(1)) <= 120:
        age_num = int(m.group(1))
        approx = m.group(2) is not None
        pad = 1 if approx else 0
        lo_age, hi_age = max(0, age_num - pad), age_num + pad
        age = AgeRange(from_age=lo_age, to_age=hi_age)
        start = end = None
        if birth_year is not None:
            start = str(birth_year + lo_age)
            end = str(birth_year + hi_age)
        return TimeRange(
            type="age_based", granularity=Granularity.YEAR, age=age,
            start=start, end=end, urgency=urgency,
        ), TimeScope.LIFE_STAGE

    # C12-d 한자어 나이 — 환갑(60)·칠순(70)·팔순(80)·구순(90), ±1년 창
    # (세는나이/만나이 경계 모호 흡수).
    _HANJA_AGES = {"환갑": 60, "회갑": 60, "칠순": 70, "고희": 70,
                   "팔순": 80, "구순": 90}
    for word, hanja_age in _HANJA_AGES.items():
        if word in text:
            lo_age, hi_age = hanja_age - 1, hanja_age + 1
            age = AgeRange(from_age=lo_age, to_age=hi_age)
            start = end = None
            if birth_year is not None:
                start = str(birth_year + lo_age)
                end = str(birth_year + hi_age)
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

    # C8 상대 기간 — "6개월 안에", "3개월 이내", "1년 안으로", "향후 30년", "12개월 내에는".
    # '내' 단독은 '내내'(3년 내내)를 배제하는 lookahead 가드(2026-07-21 데굴님 실로그:
    # '12개월 내에는 없어?'가 창 미파싱 → too_broad로 빠지던 결함).
    m = re.search(r"(\d+)\s*(개월|달|년)\s*(안에|안으로|이내에|이내|내에|내로|내(?!내))?", text)
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
    # "N월 N일" 우선, 없으면 "6/17"·"6-17"·"2026-06-17" 슬래시/대시 형식(C5b 동일 처리).
    m = re.search(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(이후로?|부터)?", text)
    slash = None if m else _SLASH_DATE_RE.search(text)
    if m or slash:
        g = m or slash
        assert g is not None
        yr_explicit = g.group(1)
        yr = int(yr_explicit) if yr_explicit else today.year + (1 if "내년" in text else 0)
        mo, dy = int(g.group(2)), int(g.group(3))
        open_kw = g.group(4)
        try:
            anchor_d: date | None = date(yr, mo, dy)
        except ValueError:  # 2월 30일 등 비정상 날짜는 무시(다음 규칙으로 통과)
            anchor_d = None
        if anchor_d is not None:
            # 연도 미지정인데 이미 지난 날짜면 내년으로(미래 택일 의도). 단 과거시제 표지가
            # 있으면('계약했는데') 그 해 과거 그대로 둔다. 명시 연도는 항상 존중.
            if (yr_explicit is None and "내년" not in text and anchor_d < today
                    and not _PAST_TENSE_RE.search(text)):
                anchor_d = date(yr + 1, mo, dy)
            # '시간대'(C17) 동반이면 시진 단위 — 단, 날짜 앵커는 유지(로또 실행 패키지 등).
            # '이후/부터'면 개방형(end=None) — 시진 단위는 특정일 고정이라 단일 앵커.
            open_ended = open_kw is not None and not hour_level
            return TimeRange(
                type="absolute",
                granularity=Granularity.HOUR if hour_level else Granularity.DAY,
                start=anchor_d.isoformat(),
                end=None if open_ended else anchor_d.isoformat(),
                urgency=urgency,
            ), TimeScope.SHORT_TERM

    # C8b 상대 일수 범위 — "이후/앞으로/향후 N일", "N일 내에/안에/이내" → 오늘부터 N일 롤링 창.
    #     N월 N일(C5b)은 위에서 이미 처리·반환되므로 여기 도달하지 않는다(날짜 오인 방지). 미래
    #     상대 일수만 잡는다(2026-07-01 데굴님 지적: '이후 10일 내에 로또 좋은 날'이 시점 미파싱으로
    #     직전 하루를 과승계해 택일이 하루만 잡히던 결함). '열흘'(10) 한글수도 허용.
    md = re.search(r"(?:이후|앞으로|향후|다가오는)\s*(\d{1,3})\s*일", text) or re.search(
        r"(\d{1,3})\s*일\s*(?:내에|안에|이내|이내에|안으로)", text
    )
    n_days = int(md.group(1)) if md else 0
    if not n_days and re.search(
        r"열흘\s*(?:내에|안에|이내|안으로)|(?:이후|앞으로|향후)\s*열흘", text
    ):
        n_days = 10
    if 1 <= n_days <= 366:
        return TimeRange(
            type="relative", granularity=Granularity.DAY,
            start=today.isoformat(), end=(today + timedelta(days=n_days)).isoformat(),
            urgency=urgency,
        ), TimeScope.DATE_LEVEL if n_days <= 31 else TimeScope.SHORT_TERM

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


# ── 시간 제약 역할 분류 (2026-07-14 시점 정합 P1) ──────────────────────────
#
# 실측 결함: "2026년 27년은 초딩때라 의미없고 2033년 시험운 합격운이 중요해"에서
# C6이 첫 4자리 연도(2026)만 잡아 배제 대상이 스레드 시점으로 저장·승계됨.
# 처음/마지막 연도의 기계적 선택을 금지하고, 모든 연도 표현을 추출해 술어·접속
# 관계로 역할(target/excluded/comparison/correction/…)을 부여한 뒤 담화상 중심
# 시점을 결정한다. 우선순위: 명시적 정정 > 명시적 요청 대상 > 긍정 절 중심 >
# (승계는 대화 엔진 몫) > 단순 언급.

# 배제 술어 — 연도 그룹 뒤 창(다음 그룹 전까지)에서 탐지. '아니라/말고/됐고'는
# 정정 접속을 겸한다(_CORRECTION_MARK_RE).
_NEG_PRED_RE = re.compile(
    r"의미\s*없|필요\s*없|중요하지\s*않|소용\s*없|상관\s*없[다어고]|빼고|제외|말고"
    r"|아니라|아니고|[은는]\s*됐고|넘어가|안\s*봐도|보지\s*마|이미\s*지났|다\s*지난"
)
# 요청·중요 술어 — 명시적 분석 대상 신호.
_POS_PRED_RE = re.compile(
    r"중요|궁금|봐\s*줘|봐줘|보고\s*싶|알려|어때|결론|기준|중심|봐야|볼래|보자"
    r"|필요해|다시\s*봐|풀어|중점"
)
# 정정 접속 — 앞 그룹 배제 + 뒤 그룹이 정정 시점(correction).
_CORRECTION_MARK_RE = re.compile(r"말고|아니라|아니고|[은는]\s*됐고|까지는\s*아니고")
# 비교 신호 — 복수 그룹이 모두 비교 대상(comparison, 스팬 유지).
_COMPARE_MARK_RE = re.compile(r"비교|둘\s*중|중\s*(?:언제|어디|뭐|누가|어느)|어느\s*(?:해|쪽)|vs")
# 가정 신호 — 그룹 직후 어미('2030년이라면').
_HYPO_TAIL_RE = re.compile(r"^\s*(?:이?라면|이면)")
# 연도 그룹 내부 구분자 — 이것만으로 이어지면 같은 그룹("2026년 27년", "2026, 2027년").
_YEAR_SEP_RE = re.compile(r"^[\s,·~\-과와랑년및]*(?:이랑)?[\s,·~\-과와랑년및]*$")
# 상대 연도 어휘 — 배제/정정 구문에 흔한 '올해 말고 내년' 지원.
_REL_YEAR_WORDS = {"올해": 0, "금년": 0, "내년": 1, "내후년": 2}


def _year_mentions(text: str, today: date) -> list[tuple[int, int, int]]:
    """텍스트의 연 단위 언급을 (연도, 시작, 끝) 목록으로 추출한다.

    4자리 연도(년 선택)·상대 연도 어휘(올해/내년…)는 항상, 2자리 축약 연도('27년')는
    4자리 연도가 앞서 등장한 체인 문맥에서만 잡는다(C6b 오탐 가드 동일 + '생' 제외).
    """
    out: list[tuple[int, int, int]] = []
    # (?!\s*년?\s*생) — '2020년생'·'2020생' 출생 표기 제외(년? 백트래킹으로 가드가
    # 비켜가지 않도록 소비 전에 검사).
    for m in re.finditer(r"(?<!\d)(20\d{2})(?!\d)(?!\s*년?\s*생)\s*년?", text):
        out.append((int(m.group(1)), m.start(), m.end()))
    for word, off in _REL_YEAR_WORDS.items():
        for m in re.finditer(word, text):
            # '내후년'이 '내년'으로 중복 매칭되지 않게 더 긴 어휘 우선(스팬 겹침 제거는 아래).
            out.append((today.year + off, m.start(), m.end()))
    first_full = min((s for _, s, _ in out), default=None)
    if first_full is not None:
        for m in re.finditer(
            r"(?<![\d.])(\d{2})\s*년(?!\s*(?:후|뒤|동안|간|내|째|차|생))", text
        ):
            if m.start() < first_full or m.group(1).startswith("20"):
                continue
            yy = int(m.group(1))
            if any(s <= m.start() < e for _, s, e in out):  # 4자리 연도의 꼬리 재매칭 방지
                continue
            out.append((2000 + yy if yy <= 69 else 1900 + yy, m.start(), m.end()))
    # 스팬 겹침 제거(긴 매칭 우선: '내후년' > '내년') 후 위치순 정렬.
    out.sort(key=lambda t: (t[1], -(t[2] - t[1])))
    dedup: list[tuple[int, int, int]] = []
    for y, s, e in out:
        if dedup and s < dedup[-1][2]:
            continue
        dedup.append((y, s, e))
    return dedup


def extract_time_constraints(text: str, today: date) -> list[TimeConstraintItem]:
    """연 단위 시간 표현을 전수 추출해 담화 역할을 부여한다 (P1).

    처리 순서: ①연도 언급 전수 추출 ②인접 언급의 그룹핑(구분자만 사이에 있으면
    같은 그룹 — "2026년 27년") ③그룹별 술어 창(다음 그룹 전까지) 분석 ④역할 분류
    ⑤같은 연도가 배제·대상 양쪽에 놓이면 나중 긍정이 승리(명시적 재요청 해제).

    Returns:
        위치순 TimeConstraintItem 목록. 연도 언급이 없으면 [].
    """
    mentions = _year_mentions(text, today)
    if not mentions:
        return []
    # ② 그룹핑 — 사이 텍스트가 구분자뿐이면 같은 그룹.
    groups: list[list[tuple[int, int, int]]] = [[mentions[0]]]
    for cur in mentions[1:]:
        prev_end = groups[-1][-1][2]
        if _YEAR_SEP_RE.match(text[prev_end:cur[1]]):
            groups[-1].append(cur)
        else:
            groups.append([cur])
    comparison = bool(_COMPARE_MARK_RE.search(text)) and len(groups) >= 2

    items: list[TimeConstraintItem] = []
    prev_neg_correction = False  # 직전 그룹이 정정 접속으로 배제됐는가
    for gi, grp in enumerate(groups):
        g_start, g_end = grp[0][1], grp[-1][2]
        window_end = groups[gi + 1][0][1] if gi + 1 < len(groups) else len(text)
        window = text[g_end:window_end]
        years = sorted(y for y, _, _ in grp)
        span_text = text[g_start:g_end]
        neg = _NEG_PRED_RE.search(window)
        pos = _POS_PRED_RE.search(window)
        role: TimeConstraintRole
        reason = ""
        if neg and (not pos or neg.start() < pos.start()):
            # 부정 술어가 먼저 — 배제. 창 안 긍정 술어는 다음 그룹 몫일 수 있으나,
            # 창은 다음 그룹 앞에서 끊기므로 이 그룹에 대한 술어만 남는다.
            role = TimeConstraintRole.EXCLUDED
            reason = neg.group(0)
        elif _HYPO_TAIL_RE.match(window):
            role = TimeConstraintRole.HYPOTHETICAL
            reason = "가정 어미"
        elif prev_neg_correction:
            role = TimeConstraintRole.CORRECTION
            reason = "정정 접속 뒤 제시"
        elif comparison:
            role = TimeConstraintRole.COMPARISON
            reason = "비교 구문"
        elif pos:
            role = TimeConstraintRole.TARGET
            reason = pos.group(0)
        else:
            role = TimeConstraintRole.MENTION
        prev_neg_correction = (
            role is TimeConstraintRole.EXCLUDED
            and bool(_CORRECTION_MARK_RE.search(window))
        )
        items.append(TimeConstraintItem(
            role=role, start_year=years[0], end_year=years[-1],
            source_span=span_text, reason=reason,
        ))

    # ⑤ 재요청 해제 — 같은 연도가 EXCLUDED와 (TARGET|CORRECTION) 양쪽이면 긍정이 승리.
    positive_years: set[int] = set()
    for it in items:
        if it.role in (TimeConstraintRole.TARGET, TimeConstraintRole.CORRECTION):
            positive_years.update(range(it.start_year, it.end_year + 1))
    return [
        it for it in items
        if not (
            it.role is TimeConstraintRole.EXCLUDED
            and set(range(it.start_year, it.end_year + 1)) <= positive_years
        )
    ]


def resolve_time_target(items: list[TimeConstraintItem]) -> tuple[int, int] | None:
    """제약 목록에서 담화상 중심 연도 스팬을 결정한다 (P1 우선순위).

    명시적 정정 > 명시적 요청 대상 > 비교(전체 스팬) > 단일 단순 언급.
    배제(EXCLUDED)·가정(HYPOTHETICAL)은 절대 중심 시점이 되지 않는다.
    복수 그룹이 모두 단순 언급이면 None(모호 — 기존 규칙·승계에 양보).
    """
    def _span(role: TimeConstraintRole) -> tuple[int, int] | None:
        ys = [
            y for it in items if it.role is role
            for y in (it.start_year, it.end_year)
        ]
        return (min(ys), max(ys)) if ys else None

    for role in (TimeConstraintRole.CORRECTION, TimeConstraintRole.TARGET):
        span = _span(role)
        if span is not None:
            return span
    span = _span(TimeConstraintRole.COMPARISON)
    if span is not None:
        return span
    mentions = [it for it in items if it.role is TimeConstraintRole.MENTION]
    if len(mentions) == 1:
        return mentions[0].start_year, mentions[0].end_year
    return None


# 현재 날짜/시기 진술 절 — '오늘은 7월 22일이고'·'지금은 7월인데' 류. 날짜가 목적어가 아니라
# 화자의 현재 위치 설명이므로 시점 추출 대상에서 제외한다(연결어미 필수 — '7월 22일 운세'
# 같은 대상 지정과 구분).
_TODAY_DATE_STATEMENT_RE = re.compile(
    r"(?:오늘|지금)은?\s*(?:\d{4}년\s*)?\d{1,2}월(?:\s*\d{1,2}일)?"
    r"(?:이고|이며|인데|이라서|이니까|이라|이야|이잖아|입니다|이에요|이지)"
)


def parse_time_with_constraints(
    text: str,
    today: date,
    birth_year: int | None = None,
    current_month_label: str | None = None,
) -> tuple[TimeRange | None, TimeScope, list[TimeConstraintItem]]:
    """parse_time + 연 단위 제약 해소 — 배제 연도가 시점으로 뽑히는 것을 교정한다.

    기존 18패턴 결과를 유지하되, ①결과가 없거나 ②결과의 연도가 배제 연도이거나
    ③복수 연도 그룹의 중심 스팬과 다르면 연/월 단위에 한해 재조준(retarget)한다.
    나이·구간묶음·데드라인·앵커 등 복합 표현은 손대지 않는다(회귀 0 원칙).

    Returns:
        (TimeRange | None, TimeScope, 제약 목록). 제약 목록은 배제 지속(P2)·LLM
        서술 제한에 쓰인다.
    """
    # 현재 날짜 '진술' 제거 — "오늘은 7월 22일이고 이사는 미래의 일이야"처럼 오늘 날짜를
    # 맥락으로 언급한 절은 분석 대상 시점이 아니다(2026-07-22 실로그: 시제 정정 발화의
    # '7월 22일'이 explicit 시점으로 채택돼 미래 이사 질문이 오늘 일운으로 앵커됨).
    # 진술 절만 제거하므로 "오늘 운세 봐줘"류 순수 '오늘' 요청은 영향 없다.
    text = _TODAY_DATE_STATEMENT_RE.sub(" ", text)
    tr, scope = parse_time(text, today, birth_year, current_month_label)
    items = extract_time_constraints(text, today)
    if not items:
        return tr, scope, items
    excluded_years = {
        y for it in items if it.role is TimeConstraintRole.EXCLUDED
        for y in range(it.start_year, it.end_year + 1)
    }
    target = resolve_time_target(items)
    multi_group = len(items) >= 2

    def _tr_year(t: TimeRange) -> int | None:
        key = t.start or t.end
        return int(key[:4]) if key and key[:4].isdigit() else None

    retargetable = tr is None or (
        tr.type in ("absolute", "relative")
        and tr.granularity in (Granularity.YEAR, Granularity.MONTH)
        and not tr.ranges and tr.age is None and not tr.anchor_dates
    )
    if not retargetable:
        return tr, scope, items
    naive_year = _tr_year(tr) if tr is not None else None
    naive_excluded = naive_year is not None and naive_year in excluded_years
    if target is not None:
        y1, y2 = target
        needs_fix = tr is None or naive_excluded or (
            (multi_group or y1 != y2)  # 복수 그룹 또는 한 그룹 복수 연도 스팬(비교 나열)
            and tr.granularity is Granularity.YEAR
            and (tr.start, tr.end) != (str(y1), str(y2))
        )
        if needs_fix:
            if tr is not None and tr.granularity is Granularity.MONTH and naive_excluded:
                # '2026년 말고 2033년 3월' — 월 유지, 연도만 교체.
                fix = {
                    "start": tr.start and f"{y1}{tr.start[4:]}",
                    "end": tr.end and f"{y1}{tr.end[4:]}",
                }
                return tr.model_copy(update=fix), scope, items
            return TimeRange(
                type="absolute", granularity=Granularity.YEAR,
                start=str(y1), end=str(y2),
                urgency=tr.urgency if tr is not None else None,
            ), TimeScope.MID_TERM, items
    elif naive_excluded:
        # 언급된 연도가 전부 배제 — 시점 미확정으로 되돌린다(승계·재질문 경로가 처리,
        # 승계 시 배제 창 회피는 대화 엔진 가드 몫).
        return None, TimeScope.TIMELESS, items
    return tr, scope, items
