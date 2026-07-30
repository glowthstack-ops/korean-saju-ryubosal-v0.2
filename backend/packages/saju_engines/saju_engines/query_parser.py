"""룰 기반 Query Parser (v2.2 Phase 3 T3.1·T3.6, docs/03 B1·B2 + docs/08 전수 패턴).

자연어 → ParsedMessage(intents[]). 운영에서는 경량 LLM 1회 호출(JSON 강제)이 1차이고
본 모듈은 **룰 기반 폴백 + LLM 출력 검증 기준**이다(T3.1). LLM 클라이언트 연동은
llm_guard를 통과하는 별도 어댑터에서 수행한다.

지원 패턴(docs/08): 질문 유형 Q1~Q14 분류 · 다중 intent(B4/B5) · 인라인 생년월일(A6) ·
관계어/별칭 대상(A2/A9) · 출력 형식(B14) · 조건/방위(B7/D2-1) · 단답 후속 슬롯 상속(B2,
prev_intent 주입 시) · 시점 18패턴(time_parser 위임).

대상 모호 시 추측 금지(절대 원칙 7) — companion 식별자 매핑은 Subject Manager(Phase 4)
가 담당하고, 여기서는 관계어 라벨만 추출한다.
"""

from __future__ import annotations

import re
from datetime import date

from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, EVENT_WORDS
from saju_shared_types.events import EventKey
from saju_shared_types.intent import (
    ChainedStep,
    CompanionRelationType,
    Constraints,
    Domain,
    Granularity,
    InlineBirth,
    IntentJson,
    OutputFormat,
    OutputStyle,
    ParsedMessage,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
    TimeConstraintRole,
    TimeRange,
    TimeScope,
)

from .time_parser import parse_time_with_constraints

# ── 어휘 사전 (실로그 기반 — docs/08 D) ──────────────────────────

_DOMAIN_WORDS: dict[Domain, list[str]] = {
    Domain.CAREER: [
        "이직", "취업", "직장", "승진", "퇴사", "직업", "사업", "창업", "회사",
        # 이직 **유입 경로** 어휘(2026-07-30 실사용 미탐지: '어제 들어온 헤드헌터
        # 제안은 받는게 맞을까?'가 general→too_broad로 빠졌다). '이직'이라는 낱말이
        # 없으면 domain이 비어 시점도 없는 결정 질문이 범위 좁힘 안내로 떨어진다.
        # event_forms의 '스카우트·이직 제의'가 파서 어휘에는 없던 누락.
        "헤드헌터", "헤드헌팅", "스카우트", "전직",
        # 채용 절차·보상 어휘 — 같은 누락으로 묶여 있던 것들. 라우팅만 바꾸며
        # 합격·연봉 결과 단정은 기존 승부 단정 금지 가드가 그대로 담당한다.
        "경력직", "이력서", "면접", "연봉", "커리어",
    ],
    Domain.WEALTH: [
        "재물", "돈", "투자", "유산", "로또", "횡재", "주식", "문서운", "분양",
        # 재산·보안 어휘(2026-07-23 사고수 확장): 도난·분실·사기·피싱 질문이
        # general로 떨어지지 않고 재물 도메인→위험 노출(finance) 경로로 연결된다.
        "도난", "분실", "소매치기", "절도", "사기", "피싱", "해킹",
        # 차입·부채 흐름도 재물 도메인(2026-07-12 실사용: '대출 시 어떤 흐름'이
        # general→too_broad로 빠지던 결함). 상환·이자 등 파생어는 대출/빚이 포괄.
        "대출", "융자", "빚", "부채",
    ],
    Domain.RELOCATION: [
        "이사", "이동수", "이주",
        "사무실 이전", "사업장 이전", "사무실 이사", "사업장 이사",
        "오피스 이전", "점포 이전", "상가 이전",
        # 지역 추천형(공간 질문) — '어디서 살까·살 곳·지역 추천' 류도 거주·지역 도메인으로
        # 감지한다(2026-06-26: '서울 살 곳 추천'이 general로 떨어져 직전 날짜·이사의도를 과잉
        # 승계하던 결함). 타 도메인 오염을 피해 거주·추천 의미가 분명한 구(句)만 등재.
        "살면 좋은", "살기 좋은", "살 곳", "살 만한", "거주지",
        "어디서 살", "어디 살", "어느 지역", "어느 동네", "지역 추천", "동네 추천",
    ],
    Domain.RELATIONSHIP: [
        "연애", "결혼", "재혼", "이혼", "별거", "파혼", "이별", "궁합", "재회", "배우자", "인연",
        # '관계·사이'도 관계 도메인으로 감지(2026-07-01: 'ㄱㄱ과 나는 어떤 관계일까?'가 도메인
        # 미감지로 직전 이사 스레드를 과승계하던 결함). query_type 감지가 이미 쓰는 신호와 일치.
        "관계", "사이",
        # 궁합·비교형 '잘 맞아/어울려'도 관계 도메인(P3b — '지민이랑 민수는 잘 맞아?'가 도메인
        # 미감지로 too_broad에 빠지던 문제). 대상 2명 비교의 관계 질의를 실행 경로로 통과시킨다.
        "잘 맞", "안 맞", "어울리",
    ],
    # 수명·사망 어휘(2026-07-23): 거부하지 않고 HEALTH로 흡수 — 사용자 제시
    # 나이대 창 기준으로 건강·에너지 흐름을 풀되, 사망 단정은 출력 가드
    # (report_checks·health_vulnerability 디스클레이머)가 차단한다.
    # '쇠락' 같은 다의어(건강·재물 등)는 키워드로 도메인을 단정하지 않는다
    # — 후속 턴이면 대화 승계(직전 턴 도메인)가 결정한다(2026-07-23).
    # 사고수 어휘(2026-07-23): 사고·안전 질문은 건강·안전 도메인으로 흡수 —
    # 위험 노출 경로(HEALTH→health_safety)와 사고수 디렉티브가 이어받는다.
    # '사고'는 매수('집을 사고 싶어')·'사고방식' 등 동형어가 많아 경계 정규식
    # (_SAGO_BOUNDARY_RE)으로만 인정한다.
    Domain.HEALTH: ["건강", "수술", "몸", "수명", "사망", "장수", "죽음",
                    "죽을", "죽는", "노쇠", "기력", "체력",
                    "사고", "횡액", "다치", "다칠", "부상", "낙상", "골절"],
    Domain.EDUCATION: ["학업", "시험", "합격", "공부", "입시", "자격증", "선행"],
}

# 이벤트 키워드 — 21키 EventKeyV2 기준(진급·평가·오디션·대회·고시·자격증 포함, Phase 7).
_EVENT_WORDS = EVENT_WORDS

# 관계어 → 동반자 관계(A2 — companion_id 매핑은 Subject Manager 몫).
_RELATION_WORDS: dict[str, CompanionRelationType] = {
    "엄마": CompanionRelationType.PARENT_CHILD, "아빠": CompanionRelationType.PARENT_CHILD,
    "부모": CompanionRelationType.PARENT_CHILD, "아들": CompanionRelationType.PARENT_CHILD,
    "딸": CompanionRelationType.PARENT_CHILD, "자녀": CompanionRelationType.PARENT_CHILD,
    "남편": CompanionRelationType.SPOUSE, "아내": CompanionRelationType.SPOUSE,
    "신랑": CompanionRelationType.SPOUSE, "와이프": CompanionRelationType.SPOUSE,
    "남자친구": CompanionRelationType.LOVER, "여자친구": CompanionRelationType.LOVER,
    "동업": CompanionRelationType.BUSINESS_PARTNER,
    "친구": CompanionRelationType.FRIEND,
}

_DIRECTIONS = ["남동", "남서", "북동", "북서", "동", "서", "남", "북"]
# 시군구 지명 구(句) — 선택적 시도 접두 + 시/군/구('서울 중구', '고양시 일산동구').
_REGION_PHRASE = r"(?:[가-힣]{2,}\s+)?[가-힣]{1,}(?:특별자치시|시|군|구)"
# 시도·광역 단축명 — 지역 추천 스코프('서울 내', '경기도에서') 포착용(2026-06-26).
_SIDO = "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"

# 용어 교육(Q11) 어휘 — "X가 무슨 뜻"과 결합.
_TERM_WORDS = ["공망", "용신", "희신", "기신", "구신", "한신", "격", "십성", "대운",
               "신살", "지장간", "식신격", "편인격"]


# 사무실/사업장 이전 신호 — relocation_kind=office 판정용(R4). 집 이사(일지)와 달리 월주 중심.
_OFFICE_RELOCATION_WORDS = (
    "사무실 이전", "사업장 이전", "사무실 이사", "사업장 이사",
    "오피스 이전", "점포 이전", "상가 이전",
)


def _detect_relocation_kind(text: str) -> str:
    """이사 종류 — 사무실/사업장 이전 신호가 있으면 office, 아니면 home(R4)."""
    return "office" if any(w in text for w in _OFFICE_RELOCATION_WORDS) else "home"


# 괄호 주석('은행 대출(남편) - 인테리어') — 괄호 안 인물 언급은 역할·귀속 표기이지 풀이 대상
# 지정이 아니다(2026-07-22 실로그: '(남편)'이 대상으로 채택돼 본인 배제 companion_only로
# 빠짐 → 첨부 칩 부부 질문이 need_subject 거부). 대상 스캔 전용 치환 — 인라인 생년월일
# ('동생(1998.07.23 여자)')은 원문에서 계속 파싱한다.
_PAREN_ANNOTATION_RE = re.compile(r"[(（][^)）]*[)）]")


def strip_parenthetical(text: str) -> str:
    """대상 스캔용 텍스트 — 괄호 주석 구간을 공백으로 치환한다."""
    return _PAREN_ANNOTATION_RE.sub(" ", text)


# 1인칭 복수 주어('우리가/우리는/우리 둘/우리 부부/저희가') — 동반자 언급과 결합하면 본인도
# 대상에 포함하는 신호(2026-07-22 실로그: '우리가 주의할 점은?'+남편 첨부가 본인 배제된
# companion_only로 빠져 출생정보 확인 오류). '우리 남편/우리 집' 같은 소유격(조사 없는 명사
# 연결)과 '우리가게'는 매칭되지 않는다. 파서(_detect_subjects)와 대화 계층(resolve_subjects)
# 공용 — 단일 출처.
INCLUSIVE_WE_RE = re.compile(
    r"우리(?:가(?!게)|는|도|를|한테|에게|끼리|\s*둘|\s*부부|\s*커플)"
    r"|저희(?:가|는|도|를|한테|에게)"
)

# '사이' 경계 가드(2026-07-22) — '사이드프로젝트/사이트/사이즈' 등 외래어 속 부분문자열이
# 관계 도메인으로 오검출돼 스레드 도메인을 오염시키던 결함(too_broad 제안이 '연애운'으로 빠짐).
# '사이' 뒤가 문말·비한글(공백/문장부호)·조사류·'좋'일 때만 관계어로 인정한다
# ('우리 사이', '사이가 좋아질까', '사이는 어때', '사이좋게').
_SAI_BOUNDARY_RE = re.compile(r"사이(?=$|[^가-힣]|[가는도를에로야냐니좋였일인])")

# '사고' 경계 가드(2026-07-23) — 事故(사고수)와 매수 연결형('집을 사고 싶어', '주식을
# 사고 팔고')·'사고방식/사고력' 동형어를 구분한다. 문말·구두점, 사고 직결 조사·어휘
# (사고수/사고운/사고가/사고를/사고는/사고날/사고로/사고 위험), 공백 뒤 사고 문맥어
# (위험·걱정·조심·주의·날·난·당·안·없)일 때만 사고수 어휘로 인정한다.
# chat 계층의 사고수 디렉티브 감지도 이 정규식을 단일 출처로 쓴다.
ACCIDENT_SAGO_RE = re.compile(
    r"사고(?=$|[^\s가-힣]|[수운가를는날로없]|위험|당"
    r"|\s+(?:위험|걱정|조심|주의|날|난|당|안|없))"
)


def _domain_word_position(text: str, word: str) -> int:
    """도메인 어휘의 본문 내 첫 위치(-1=없음) — '사이'·'사고'만 경계 매칭, 나머지는 부분문자열."""
    if word == "사이":
        m = _SAI_BOUNDARY_RE.search(text)
        return m.start() if m else -1
    if word == "사고":
        m = ACCIDENT_SAGO_RE.search(text)
        return m.start() if m else -1
    return text.find(word)


def _detect_domains(text: str) -> list[Domain]:
    """본문에서 등장 순서대로 도메인 추출(B5 다중 도메인 결합)."""
    found: list[tuple[int, Domain]] = []
    for domain, words in _DOMAIN_WORDS.items():
        positions = [p for w in words if (p := _domain_word_position(text, w)) >= 0]
        if positions:
            found.append((min(positions), domain))
    return [d for _pos, d in sorted(found)]


def _detect_event(text: str) -> EventKey | None:
    """가장 먼저 등장하는 이벤트 키."""
    found: list[tuple[int, EventKey]] = []
    for key, words in _EVENT_WORDS.items():
        positions = [text.find(w) for w in words if w in text]
        if positions:
            found.append((min(positions), key))
    return min(found)[1] if found else None


def _parse_inline_births(text: str) -> list[SubjectRef]:
    """인라인 생년월일(A6/A7) — '91년 10월 31일 오후 3시 부천' / '1998.07.23 여자'."""
    out: list[SubjectRef] = []
    # 'YY[YY]년 M월 D일 [오전/오후 H시] [지명]' 형태.
    for m in re.finditer(
        r"(?:음력\s*)?(\d{2,4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:생)?"
        r"(?:\s*(오전|오후)?\s*(\d{1,2})시(?:\s*(\d{1,2})분)?)?",
        text,
    ):
        year = int(m.group(1))
        year += 1900 if year >= 30 and year < 100 else (2000 if year < 30 else 0)
        hour = None
        if m.group(5):
            h = int(m.group(5)) + (12 if m.group(4) == "오후" and int(m.group(5)) < 12 else 0)
            minute = int(m.group(6) or 0)
            hour = f"{h:02d}:{minute:02d}"
        calendar = "lunar" if "음력" in text[: m.start() + 3] else "solar"
        gender = "F" if re.search(r"여자|여성", text) else (
            "M" if re.search(r"남자|남성|남자친구", text) else None
        )
        birth_date = f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        out.append(SubjectRef(
            kind=SubjectKind.INLINE_TEMP,
            label=f"{birth_date} {'여' if gender == 'F' else '남' if gender == 'M' else '?'}",
            inline_birth=InlineBirth(
                date=birth_date, time=hour, calendar_type=calendar, gender=gender,
            ),
        ))
    # 'YYYY.MM.DD 여자/남자' 형태(A7).
    for m in re.finditer(r"(\d{4})\.(\d{2})\.(\d{2})\s*(여자|남자)?", text):
        birth_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        gender = {"여자": "F", "남자": "M"}.get(m.group(4) or "")
        out.append(SubjectRef(
            kind=SubjectKind.INLINE_TEMP,
            label=f"{birth_date} {'여' if gender == 'F' else '남' if gender == 'M' else '?'}",
            inline_birth=InlineBirth(date=birth_date, gender=gender),
        ))
    return out


def _detect_subjects(text: str) -> tuple[list[SubjectRef], SubjectMode]:
    """대상 추출(A1~A9 부분) — 관계어/별칭/인라인. 기본 self."""
    subjects: list[SubjectRef] = []
    exclude_self = bool(re.search(r"나를\s*제외", text))
    # 괄호 주석은 대상 지정이 아니다 — 관계어·별칭 스캔은 괄호 제거본으로(인라인 생년월일은 원문).
    scan_text = strip_parenthetical(text)

    for m in re.finditer(r"(\d+)\s*호", scan_text):  # A9 별칭("1호")
        subjects.append(SubjectRef(
            kind=SubjectKind.COMPANION, label=f"{m.group(1)}호",
        ))
    for word in _RELATION_WORDS:
        # 경계: 조사·비한글·문말('남편, 잘 지낼까'의 쉼표 등). '남편감' 합성어는 제외(뒤가
        # 일반 한글). 뒤가 아예 없는 문말도 인정(2026-07-22 경계 보정).
        if re.search(rf"{word}(?=$|[^가-힣]|의|이랑|과|와|은|는)", scan_text):
            subjects.append(SubjectRef(kind=SubjectKind.COMPANION, label=word))
            break
    subjects += _parse_inline_births(text)

    pairwise = bool(re.search(r"궁합|나랑\s*(?:잘\s*)?맞|내\s*사주가\s*잘\s*맞", text))
    ranking = bool(re.search(r"누구야|누가\s|순위|등수|1등부터", text))
    group = bool(re.search(r"종합해서|둘\s*다|모두|우리\s*가족|함께", text))
    inclusive_we = bool(INCLUSIVE_WE_RE.search(text))

    if exclude_self:
        mode = SubjectMode.COMPARE_EXCLUDE_SELF
    elif ranking and (len(subjects) >= 2 or "포함" in text):
        mode = SubjectMode.RANKING
    elif pairwise and subjects:
        mode = SubjectMode.PAIRWISE
        subjects.insert(0, SubjectRef(kind=SubjectKind.SELF, label="본인"))
    elif (group or inclusive_we) and subjects:
        mode = SubjectMode.GROUP_AGGREGATE
        subjects.insert(0, SubjectRef(kind=SubjectKind.SELF, label="본인"))
    elif subjects:
        mode = SubjectMode.SINGLE  # 동반자 단독(A2)
    else:
        subjects = [SubjectRef(kind=SubjectKind.SELF, label="본인")]
        mode = SubjectMode.SINGLE
    return subjects, mode


def _detect_query_type(text: str, subjects_mode: SubjectMode) -> QueryType:
    """질문 유형 분류(docs/03 B1 — 우선순위 고정 룰)."""
    # Q14 — 메타/탐침·로또 번호·악의 (B11/G4/G5/G6). '모델'은 AI/시스템 맥락일 때만 거부 —
    # '유료화 모델'·'롤모델'·직업이 '모델'인 사용자 등 일반 '모델' 언급 오분류 방지(2026-07-02).
    if re.search(
        r"프롬프트|시스템\s*(?:룰|프롬프트|지시문?)|rag에|\bcot\b|"
        r"\bgpt\b|\bllm\b|claude|gemini|지피티|"
        r"(?:어떤|무슨|어느)\s*(?:ai|모델)|"
        r"(?:ai|언어|기반|생성형?)\s*모델|모델\s*(?:명|이름)|"
        r"모델(?:은|는|이|가)?\s*(?:뭐|무엇|무슨|어떤|알려|공개|밝|써|쓰|사용|이야|인가|니)",
        text, re.IGNORECASE,
    ):
        return QueryType.OUT_OF_SCOPE
    # 로또 번호·특정 종목 픽은 거부(절대원칙 8). 단 '주식운/로또운/투자 시기' 등 흐름·시기
    # 질문은 통과시켜 생활형 횡재로 자유롭게 풀이한다(2026-06-20 개정 — 픽만 거부).
    if re.search(
        r"로또\s*번호|번호.*찍어|종목\s*(?:추천|찍|골라)|매수\s*종목|"
        r"(?:어떤|무슨)\s*(?:주식|코인|종목)\s*(?:살|사|매수|골라|추천|좋)",
        text,
    ):
        return QueryType.OUT_OF_SCOPE
    # Q12 — 이의/정정 (B9/B10/A10): 직전 답변 참조 신호가 있어야 한다("vs ... 맞아?"는 Q7).
    if re.search(r"아니야\s*\?|틀렸|헷갈려|다시\s*체크|라던데\s*맞아|했잖아", text):
        return QueryType.FEEDBACK_CORRECTION
    # Q11 — 용어 교육 (B12): 용어 + 뜻/뭐야. 단 소유격("내 용신")은 본인 명식 → Q8.
    is_term = any(w in text for w in _TERM_WORDS)
    if (
        is_term
        and re.search(r"무슨\s*뜻|뜻이|뭐야|장점과\s*단점", text)
        and not re.search(r"내\s*(용신|격국|일간|사주)", text)
    ):
        return QueryType.TERMINOLOGY_EDUCATION
    # Q13 — 감정 토로 (B13): 질문 없이 서사/감정.
    if re.search(r"스트레스|힘들[어다]|고장나서|우울", text) and "?" not in text:
        return QueryType.EMOTIONAL_SUPPORT
    # Q6 — 비교(궁합/승부/랭킹).
    if subjects_mode in (
        SubjectMode.PAIRWISE, SubjectMode.COMPARE_EXCLUDE_SELF, SubjectMode.RANKING,
    ):
        return QueryType.COMPARISON
    if re.search(
        r"당선|승부|누가\s*이길|궁합|중에?\s*누가|누가\s*더|합이\s*좋은|랑\s*잘\s*맞",
        text,
    ):
        return QueryType.COMPARISON
    # Q7 — 선택지 비교 (B6).
    if re.search(
        r"\bvs\b|중에\s*뭐가|어떤\s*게\s*(?:나|맞)|도전해\s*\?"
        r"|까\s*말까|까[,\s]+[가-힣]{1,4}까",
        text,
    ):
        return QueryType.DECISION_SUPPORT
    # Q4 — 택일.
    if re.search(r"손없는\s*날", text):
        return QueryType.DATE_RECOMMENDATION
    date_words = re.search(r"좋은\s*날|어떤\s*날|날짜|길일|좋을지|적당한\s*달|좋은.*시간대", text)
    if date_words and re.search(
        r"이사|계약|결혼|수술|개업|로또|매매|사무실|사업장|점포|상가|오피스", text
    ):
        return QueryType.DATE_RECOMMENDATION
    # 특정 시점에 계약/이사 등을 '해도 될지' 평가하는 질문도 택일로 본다
    # ('7월 4일에 계약·이사… 잘한 결정일까?'). 막연한 '이사 어때'는 제외(시점 표지 필요).
    eval_words = re.search(
        r"잘한\s*결정|잘\s*한\s*건가|괜찮을까|괜찮나|괜찮아|괜찮은가"
        r"|해도\s*(?:될까|되나|좋을까|괜찮)|날\s*잡아도|어떨까", text)
    date_act = re.search(r"이사|계약|결혼|수술|개업|매매|입주|등기|잔금|이전", text)
    date_marker = re.search(r"\d{1,2}\s*[월일]|오늘|내일|모레", text)
    if eval_words and date_act and date_marker:
        return QueryType.DATE_RECOMMENDATION
    # Q10 — 개운/보완 (D-3).
    if re.search(r"조심해야|보완|개운|비방|피해야|주의해야", text):
        return QueryType.REMEDY
    # Q5 — 과거 설명/역검증 (C15).
    if re.search(
        r"왜.{0,8}힘들었|맞춰\s*봐|언제인지\s*맞|무슨\s*일이?\s*있었"
        r"|운\s*때문|이유가\s*사주|운이랑\s*관련",
        text,
    ):
        return QueryType.EVENT_EXPLANATION
    # Q3 — 시기 탐색.
    if "언제" in text:
        return QueryType.TIMING_SEARCH
    # Q9 — 특정 인물 분석(관계어 동반)은 명식 구조보다 우선.
    person = (
        r"(?:엄마|아빠|부모|아들|딸|자녀|남편|아내|신랑|와이프"
        r"|남자친구|여자친구|동업|친구|상사|동료)"
    )
    if re.search(person, text) and re.search(
        r"어떤\s*사람|성격|사이|관계|부딪|잘\s*지내", text
    ):
        return QueryType.RELATIONSHIP_ANALYSIS
    # Q8 — 명식 구조 (D2-12 포함). 일주 캐릭터/기질형 + 용희기구한 질문(v2.2.1).
    if re.search(
        r"용신|희신|기신|구신|한신|내\s*사주|mbti|성격|성향|격국|신강|신약|도화|역마살"
        r"|공망|일주|캐릭터|기질|타고난|어떤\s*사람|십성|신살|궁성",
        text,
        re.IGNORECASE,
    ):
        return QueryType.CHART_ANALYSIS
    # Q9 — 관계 분석.
    if re.search(r"사이는\s*어때|부모\s*복|관계는", text):
        return QueryType.RELATIONSHIP_ANALYSIS
    # Q2 — 분야 분석.
    if _detect_domains(text):
        return QueryType.DOMAIN_ANALYSIS
    # Q1 — 종합운.
    return QueryType.FORTUNE_OVERVIEW


def _detect_output_style(text: str) -> OutputStyle:
    """출력 형식 지정(B14)."""
    style = OutputStyle()
    if re.search(r"100점\s*만점|몇\s*점", text):
        style.score_display = "hundred_scale"
    m = re.search(r"1\s*등부터\s*(\d+)\s*등", text)
    if m:
        style.rank_range = int(m.group(1))
        style.format = OutputFormat.RANKED_DATES
    if "동화처럼" in text:
        style.tone_override = "동화"
    if re.search(r"세부적으로|구체적인\s*시기", text):
        style.detail_level = "detailed"
    return style


def _detect_constraints(text: str) -> Constraints:
    """조건/제약(B7·D2-1·C9·S8)."""
    c = Constraints()
    for d in _DIRECTIONS:
        if f"{d}쪽" in text or f"{d}으로" in text or f"{d}향" in text:
            c.direction = d
            break
    # 현재 거주지(방위 기준점) — "지금 사는 곳은 X", "현재 거주지는 X", "현재는 X에 있는데/사는데".
    m = re.search(
        r"(?:지금\s*사는\s*곳은|현재\s*거주지는?)\s*([가-힣\s]{2,12}?)(?:인데|이야|야|입니다)", text
    )
    if m is None:  # "현재는 고양시 일산동구에 있는데/사는데" 어순(지명이 동사 앞).
        m = re.search(
            r"(?:현재|지금)(?:는|은)?\s*(" + _REGION_PHRASE
            + r")\s*(?:에|에서)\s*(?:있|살|거주|지내)",
            text,
        )
    if m is None:  # "고양시 일산동구에 살고/사는데/거주" — 접두 없이.
        m = re.search(r"(" + _REGION_PHRASE + r")\s*(?:에|에서)\s*(?:살고|사는|거주)", text)
    if m:
        c.location_base = m.group(1).strip()
    # 이사 목적지 지역 — "서울 중구로 이사", "수원시로 가려고"(현재 거주지 location_base와 구분).
    # 지명 구(句)만 포착하고, 등재 시군구 정규화는 사용처(채팅)에서 한다(파서는 순수 유지).
    tr_m = re.search(r"(" + _REGION_PHRASE + r")\s*(?:으로|로|에)\s*(?:이사|이전|옮|가)", text)
    if tr_m is None:  # "이사할집은 서울 중구야" 어순(지명이 '이사' 뒤) — 진술형 포함.
        tr_m = re.search(
            r"(?:이사\s*할\s*(?:집|곳)은?|이사\s*갈\s*(?:집|곳)은?|이사하려는\s*곳은?|"
            r"새\s*집은?|이사는)\s*(" + _REGION_PHRASE + r")",
            text,
        )
    if tr_m:
        c.target_region = tr_m.group(1).strip()
    # 지역 추천 스코프(시도·광역) — "서울 내에 살면 좋은 지역", "경기도에서 살 곳" 등 추천형은
    # 시도 범위를 스코프로 잡는다(2026-06-26: '서울' 질문이 스코프 없이 전국 폴백→광주 추천되던
    # 결함). 시군구 목적지(target_region)가 이미 잡혔으면 건드리지 않는다.
    if c.target_region is None:
        sm = re.search(
            r"(" + _SIDO + r")(?:특별시|광역시|특별자치시|특별자치도|도)?\s*"
            r"(?:내|안|지역|근처|쪽|에서|에)",
            text,
        )
        # 거주·추천 맥락에서만 스코프로 채택(예: '서울에 재물운'은 스코프 아님).
        if sm and re.search(r"살|거주|이사|정착|지역\s*추천|동네|어디", text):
            c.target_region = sm.group(1).strip()
    if re.search(r"한다면|간다면|만난다면|된다면", text):
        cond = re.search(r"([가-힣\d\s.]+?(?:한다면|간다면|만난다면|된다면))", text)
        c.conditional = cond.group(1).strip() if cond else "조건부"
    if re.search(r"되면.*이후\s*운|당선이?\s*되면", text):
        c.branch_scenario = True
    if re.search(r"주말만|주말\s*밖에", text):
        c.reality_constraints.append("주말만 가능")
    # 평일 선호/한정(2026-06-16) — '평일만/주중만'은 주말 제외, '평일(도)'는 평일 우선(주말 허용).
    if re.search(r"평일\s*만|주중\s*만|평일\s*로\s*만", text):
        c.reality_constraints.append("평일만 가능")
    elif re.search(r"평일|주중", text):
        c.reality_constraints.append("평일 선호")
    if re.search(r"손\s*없는\s*날", text):
        c.son_eomneun_nal = True
    m = re.search(r"계약\s*후\s*(\d+)\s*[~-]?\s*(\d+)?\s*개월\s*안에\s*이사", text)
    if m:
        window = f"{m.group(1)}~{m.group(2) or m.group(1)}개월"
        c.chained_schedule = [
            ChainedStep(step="계약"),
            ChainedStep(step="이사", offset_from="계약", window=window),
        ]
    return c


def _has_constraint_signal(c: Constraints) -> bool:
    """제약 정제 후속('평일도 없어?')인지 — 방위/현실제약/손없는날/배제 중 하나라도 있으면 True."""
    return bool(
        c.reality_constraints or c.direction or c.son_eomneun_nal or c.exclude_options
    )


def _merge_constraints(prev: Constraints, new: Constraints) -> Constraints:
    """직전 제약에 새 제약을 병합(정제). 주말↔평일 선호는 상호배타라 새 선호가 직전을 대체한다."""
    merged = prev.model_copy(deep=True)
    if new.direction:
        merged.direction = new.direction
    if new.location_base:
        merged.location_base = new.location_base
    if new.target_region:
        merged.target_region = new.target_region
    if new.son_eomneun_nal is not None:
        merged.son_eomneun_nal = new.son_eomneun_nal
    if new.conditional:
        merged.conditional = new.conditional
    rcs = list(merged.reality_constraints)
    if any("평일" in r for r in new.reality_constraints):
        rcs = [r for r in rcs if "주말" not in r]  # 평일 선호 → 직전 주말 제약 해제
    if any("주말" in r for r in new.reality_constraints):
        rcs = [r for r in rcs if "평일" not in r]
    for rc in new.reality_constraints:
        if rc not in rcs:
            rcs.append(rc)
    merged.reality_constraints = rcs
    for ex in new.exclude_options:
        if ex not in merged.exclude_options:
            merged.exclude_options.append(ex)
    return merged


def _split_questions(text: str) -> list[str]:
    """다중 질문(B4) 분리 — 물음표 단위, 의문 없는 조각은 직전에 병합."""
    parts = [p.strip() for p in re.split(r"(?<=\?)", text) if p.strip()]
    if len(parts) <= 1:
        return [text]
    merged: list[str] = []
    for p in parts:
        if p.endswith("?") or not merged:
            merged.append(p)
        else:
            merged[-1] += " " + p
    return merged


def _is_short_followup(text: str) -> bool:
    """단답 후속(B2) — 10자 이하 + 시점/비교 슬롯만."""
    return len(text.replace(" ", "")) <= 10


# 단순 수락 후속 — 직전 답변의 제안·질문에 대한 짧은 동의('그래','응','네','부탁해','정해줘').
# 시점·도메인·이벤트·제약 없이 직전 의도를 그대로 잇는다(직전 제안 수락이 스레드 단절→broad
# 안내로 빠지던 결함 차단, 2026-06-18). 전체가 수락어일 때만(fullmatch) — '네 사주'·'그래?'(반문)
# 같은 비수락은 제외. conversation.link_question(연속성 판별)과 parse_message(상속)가 공용한다.
AFFIRMATION_RE = re.compile(
    r"(?:그래(요|줘)?|그러(자|지|렴)|그렇게(\s*해\s*줘?)?|응+|네+|넵|예+|어+|"
    r"좋아(요)?|좋지|콜|부탁(해|해요|드려요?)?|해\s*줘|정해\s*줘|알려\s*줘|보여\s*줘|"
    r"ㅇㅇ+|ㅇㅋ|오케이?|오키|ok|okay)[!.~ㅎㅋ\s]*",
    re.IGNORECASE,
)


def parse_message(
    text: str,
    today: date,
    prev_intent: IntentJson | None = None,
    birth_year: int | None = None,
    current_month_label: str | None = None,
) -> ParsedMessage:
    """한 메시지를 ParsedMessage로 파싱한다(룰 기반 — LLM 폴백 경로).

    Args:
        text: 사용자 발화.
        today: 기준일(시점 해석).
        prev_intent: 직전 intent — 단답 후속(B2/B3) 슬롯 상속용(Question Linking의
            룰 우선 경로; 전체 연속성 엔진은 Phase 4).
        birth_year: 나이 변환(C12)용 출생 연도.
        current_month_label: 오늘이 속한 절기 월운 라벨(YYYY-MM) — '이번 달'·'다음 달'·
            미래/과거 롤링 창을 절기 기준으로 잡도록 parse_time에 전달(미주입 시 양력 폴백).

    Returns:
        intents 1개 이상을 가진 ParsedMessage(B4 다중 질문 시 복수).
    """
    # B2 단답 후속: 시점 슬롯만 교체, 나머지 직전 intent 상속.
    # 연 단위 다중·부정·정정 표현은 제약 해소를 거친다(2026-07-14 P1 — "2026년 27년은
    # 의미없고 2033년이 중요해"에서 첫 연도가 시점으로 저장되던 결함 교정).
    time_range, time_scope, time_items = parse_time_with_constraints(
        text, today, birth_year, current_month_label
    )
    time_exclusions = [
        it for it in time_items if it.role is TimeConstraintRole.EXCLUDED
    ]
    # B2b 단위 정정 단답('년단위였어') — 시점 자체가 아니라 직전 질문의 기간 단위를
    # 바꾸는 후속(2026-06-12). 직전 intent를 상속하고 granularity만 갱신한다.
    unit_m = re.search(r"([년연월주일])\s*단위", text)
    if prev_intent is not None and _is_short_followup(text) and unit_m and time_range is None:
        gran = {
            "년": Granularity.YEAR, "연": Granularity.YEAR, "월": Granularity.MONTH,
            "주": Granularity.DAY, "일": Granularity.DAY,
        }[unit_m.group(1)]
        new_tr = (
            prev_intent.time_range.model_copy(update={"granularity": gran})
            if prev_intent.time_range is not None
            else TimeRange(type="open_when", granularity=gran)
        )
        inherited = prev_intent.model_copy(update={
            "intent_id": f"{prev_intent.intent_id}+unit",
            "time_range": new_tr,
        })
        return ParsedMessage(intents=[inherited], raw_text=text)
    if (
        prev_intent is not None and time_range is None and unit_m is None
        and AFFIRMATION_RE.fullmatch(text.strip())
    ):
        # B2d 단순 수락 후속('그래','응','부탁해') — 직전 답변의 제안·질문을 수락. 직전 intent를
        # 통째로 이어받아 같은 주제·시점 창을 계속 다룬다(끊겨서 broad 안내로 빠지지 않게).
        inherited = prev_intent.model_copy(update={
            "intent_id": f"{prev_intent.intent_id}+accept",
        })
        return ParsedMessage(
            intents=[inherited], is_follow_up=True, inherited_from=prev_intent.intent_id,
        )
    if (
        prev_intent is not None and _is_short_followup(text) and time_range is not None
        and not _detect_domains(text)  # '2026년 연애운'처럼 새 도메인이 명시되면 prev 복제 금지
    ):
        # 시점만 바뀐 후속('그럼 28년은?') — 직전 intent를 상속하고 시점만 교체.
        # 후속이 단위를 따로 명시하지 않았으면 직전 granularity를 유지한다(월별 맥락 보존,
        # 2026-06-14): '앞으로 5년 이사운 월별로' 뒤 '그럼 28년은?'은 28년을 월단위로 본다.
        if (
            prev_intent.time_range is not None
            and not re.search(r"[년연월주일]\s*단위|월별|일별|연도별|날짜별|매월", text)
        ):
            time_range = time_range.model_copy(
                update={"granularity": prev_intent.time_range.granularity}
            )
        inherited = prev_intent.model_copy(update={
            "intent_id": f"{prev_intent.intent_id}+followup",
            "time_range": time_range,
            "time_scope": time_scope,
            "time_exclusions": time_exclusions,
        })
        return ParsedMessage(
            intents=[inherited], is_follow_up=True, inherited_from=prev_intent.intent_id,
        )

    # B2c 제약 정제 단답('평일도 없어?', '주말 말고') — 시점/도메인/이벤트 없이 직전 질문을
    # 좁히는 후속(2026-06-16). 직전 intent(이사·7월·DATE_RECOMMENDATION 등)를 상속하고 새
    # 제약만 병합해, 후속 택일이 새 질문으로 끊겨 broad 안내로 빠지던 결함을 막는다.
    if (
        prev_intent is not None and time_range is None and unit_m is None
        and len(text.replace(" ", "")) <= 25
        and not _detect_domains(text) and _detect_event(text) is None
    ):
        refine_c = _detect_constraints(text)
        if _has_constraint_signal(refine_c):
            inherited = prev_intent.model_copy(update={
                "intent_id": f"{prev_intent.intent_id}+refine",
                "constraints": _merge_constraints(prev_intent.constraints, refine_c),
            })
            return ParsedMessage(
                intents=[inherited], is_follow_up=True,
                inherited_from=prev_intent.intent_id,
            )

    pieces = _split_questions(text)
    subjects, mode = _detect_subjects(text)
    style = _detect_output_style(text)
    constraints = _detect_constraints(text)

    intents: list[IntentJson] = []
    for idx, piece in enumerate(pieces):
        event_key = _detect_event(piece)
        event_keys: list[EventKey] = []
        # '직장운'은 통상 재직 상태의 이직·입지·승진 문의 — 이직(주축)+승진(동반)으로 본다.
        # 무직·비정규일 때 '취업' 포함 여부는 프로필·맥락을 아는 상위 계층(chat_service)이 보강한다.
        if re.search(r"직장\s*운", piece):
            event_key = EventKey.CAREER_CHANGE
            event_keys = [EventKey.PROMOTION]
        domains = _detect_domains(piece) or _detect_domains(text)
        # 도메인어가 없어도 이벤트가 잡히면 이벤트의 도메인을 따른다 — '취직 언제쯤?'처럼
        # 도메인 단어가 없는 질문이 general로 떨어져 재물운 등 일반 흐름으로 새지 않도록.
        if not domains and event_key is not None:
            domains = [Domain(EVENT_DOMAIN[event_key])]
        piece_time, piece_scope, _ = parse_time_with_constraints(
            piece, today, birth_year, current_month_label
        )
        if piece_time is None:
            piece_time, piece_scope = time_range, time_scope
        intents.append(IntentJson(
            intent_id=f"i{idx + 1}",
            query_type=_detect_query_type(piece, mode),
            subjects=subjects,
            subject_mode=mode,
            relation_type=next(
                (rel for w, rel in _RELATION_WORDS.items() if w in text), None
            ),
            domain=domains[0] if domains else Domain.GENERAL,
            domains=domains[1:],
            event_key=event_key,
            event_keys=event_keys,
            time_scope=piece_scope if piece_time else TimeScope.TIMELESS,
            time_range=piece_time,
            time_exclusions=time_exclusions,
            relocation_kind=_detect_relocation_kind(piece),
            constraints=constraints,
            output=style,
        ))
    return ParsedMessage(
        intents=intents, output_style=style,
        trace={  # P0 — 시점 해소 추적(파싱 계층)
            "extracted_times": [it.model_dump() for it in time_items],
            "resolved_target": (
                (time_range.start, time_range.end) if time_range is not None else None
            ),
        },
    )
