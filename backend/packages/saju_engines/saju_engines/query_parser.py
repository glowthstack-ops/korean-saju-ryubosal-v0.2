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

from saju_shared_types.events import EventKey
from saju_shared_types.intent import (
    ChainedStep,
    CompanionRelationType,
    Constraints,
    Domain,
    InlineBirth,
    IntentJson,
    OutputFormat,
    OutputStyle,
    ParsedMessage,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
    TimeScope,
)

from .time_parser import parse_time

# ── 어휘 사전 (실로그 기반 — docs/08 D) ──────────────────────────

_DOMAIN_WORDS: dict[Domain, list[str]] = {
    Domain.CAREER: ["이직", "취업", "직장", "승진", "퇴사", "직업", "사업", "창업", "회사"],
    Domain.WEALTH: ["재물", "돈", "투자", "유산", "로또", "횡재", "주식", "문서운", "분양"],
    Domain.RELOCATION: ["이사", "이동수", "이주"],
    Domain.RELATIONSHIP: ["연애", "결혼", "재혼", "이별", "궁합", "재회", "배우자", "인연"],
    Domain.HEALTH: ["건강", "수술", "몸"],
    Domain.EDUCATION: ["학업", "시험", "합격", "공부", "입시", "자격증", "선행"],
}

_EVENT_WORDS: dict[EventKey, list[str]] = {
    EventKey.CAREER_CHANGE: ["이직", "취업"],  # 취업(employment)은 taxonomy 부재 — 이직에 잠정 매핑
    EventKey.RESIGNATION: ["퇴사"],
    EventKey.PROMOTION: ["승진"],
    EventKey.BUSINESS_START: ["창업", "개업", "사업 시작"],
    EventKey.MARRIAGE: ["결혼", "재혼"],
    EventKey.RELATIONSHIP_START: ["연애"],
    EventKey.RELATIONSHIP_END: ["이별", "헤어"],
    EventKey.CHILDBIRTH: ["출산", "자녀가 있을지"],
    EventKey.RELOCATION: ["이사"],
    EventKey.CONTRACT: ["계약"],
    EventKey.EXAM: ["시험", "합격"],
    EventKey.WINDFALL: ["로또", "복권", "횡재"],
    EventKey.SURGERY: ["수술"],
}

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

# 용어 교육(Q11) 어휘 — "X가 무슨 뜻"과 결합.
_TERM_WORDS = ["공망", "용신", "희신", "기신", "구신", "한신", "격", "십성", "대운",
               "신살", "지장간", "식신격", "편인격"]


def _detect_domains(text: str) -> list[Domain]:
    """본문에서 등장 순서대로 도메인 추출(B5 다중 도메인 결합)."""
    found: list[tuple[int, Domain]] = []
    for domain, words in _DOMAIN_WORDS.items():
        positions = [text.find(w) for w in words if w in text]
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

    for m in re.finditer(r"(\d+)\s*호", text):  # A9 별칭("1호")
        subjects.append(SubjectRef(
            kind=SubjectKind.COMPANION, label=f"{m.group(1)}호",
        ))
    for word in _RELATION_WORDS:
        if re.search(rf"{word}(?:의|이랑|과|와|은|는|\s)", text):
            subjects.append(SubjectRef(kind=SubjectKind.COMPANION, label=word))
            break
    subjects += _parse_inline_births(text)

    pairwise = bool(re.search(r"궁합|나랑\s*(?:잘\s*)?맞|내\s*사주가\s*잘\s*맞", text))
    ranking = bool(re.search(r"누구야|누가\s|순위|등수|1등부터", text))
    group = bool(re.search(r"종합해서|둘\s*다|모두|우리\s*가족|함께", text))

    if exclude_self:
        mode = SubjectMode.COMPARE_EXCLUDE_SELF
    elif ranking and (len(subjects) >= 2 or "포함" in text):
        mode = SubjectMode.RANKING
    elif pairwise and subjects:
        mode = SubjectMode.PAIRWISE
        subjects.insert(0, SubjectRef(kind=SubjectKind.SELF, label="본인"))
    elif group and subjects:
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
    # Q14 — 메타/탐침·로또 번호·악의 (B11/G4/G5/G6).
    if re.search(r"모델|프롬프트|시스템\s*룰|rag에|cot", text, re.IGNORECASE):
        return QueryType.OUT_OF_SCOPE
    if re.search(r"로또\s*번호|번호.*찍어", text):
        return QueryType.OUT_OF_SCOPE
    # Q12 — 이의/정정 (B9/B10/A10): 직전 답변 참조 신호가 있어야 한다("vs ... 맞아?"는 Q7).
    if re.search(r"아니야\s*\?|틀렸|헷갈려|다시\s*체크|라던데\s*맞아|했잖아", text):
        return QueryType.FEEDBACK_CORRECTION
    # Q11 — 용어 교육 (B12): 용어 + 뜻/뭐야.
    is_term = any(w in text for w in _TERM_WORDS)
    if is_term and re.search(r"무슨\s*뜻|뜻이|뭐야|장점과\s*단점", text):
        return QueryType.TERMINOLOGY_EDUCATION
    # Q13 — 감정 토로 (B13): 질문 없이 서사/감정.
    if re.search(r"스트레스|힘들[어다]|고장나서|우울", text) and "?" not in text:
        return QueryType.EMOTIONAL_SUPPORT
    # Q6 — 비교(궁합/승부/랭킹).
    if subjects_mode in (
        SubjectMode.PAIRWISE, SubjectMode.COMPARE_EXCLUDE_SELF, SubjectMode.RANKING,
    ):
        return QueryType.COMPARISON
    if re.search(r"당선|승부|누가\s*이길", text):
        return QueryType.COMPARISON
    # Q7 — 선택지 비교 (B6).
    if re.search(r"\bvs\b|중에\s*뭐가|어떤\s*게\s*(?:나|맞)|도전해\s*\?", text):
        return QueryType.DECISION_SUPPORT
    # Q4 — 택일.
    date_words = re.search(r"좋은\s*날|어떤\s*날|날짜|길일|좋을지|적당한\s*달|좋은.*시간대", text)
    if date_words and re.search(
        r"이사|계약|결혼|수술|개업|로또|매매", text
    ):
        return QueryType.DATE_RECOMMENDATION
    # Q10 — 개운/보완 (D-3).
    if re.search(r"조심해야|보완|개운|비방|피해야|주의해야", text):
        return QueryType.REMEDY
    # Q5 — 과거 설명/역검증 (C15).
    if re.search(r"왜\s*힘들었|맞춰\s*봐|언제인지\s*맞", text):
        return QueryType.EVENT_EXPLANATION
    # Q3 — 시기 탐색.
    if "언제" in text:
        return QueryType.TIMING_SEARCH
    # Q8 — 명식 구조 (D2-12 포함).
    if re.search(r"용신이\s*뭐|내\s*사주\s*(?:는|가)?\s*어때|mbti|성격|성향", text, re.IGNORECASE):
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
    m = re.search(
        r"(?:지금\s*사는\s*곳은|현재\s*거주지는?)\s*([가-힣\s]{2,12}?)(?:인데|이야|야|입니다)", text
    )
    if m:
        c.location_base = m.group(1).strip()
    if re.search(r"한다면|간다면|만난다면|된다면", text):
        cond = re.search(r"([가-힣\d\s.]+?(?:한다면|간다면|만난다면|된다면))", text)
        c.conditional = cond.group(1).strip() if cond else "조건부"
    if re.search(r"되면.*이후\s*운|당선이?\s*되면", text):
        c.branch_scenario = True
    if re.search(r"주말만|주말\s*밖에", text):
        c.reality_constraints.append("주말만 가능")
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


def parse_message(
    text: str,
    today: date,
    prev_intent: IntentJson | None = None,
    birth_year: int | None = None,
) -> ParsedMessage:
    """한 메시지를 ParsedMessage로 파싱한다(룰 기반 — LLM 폴백 경로).

    Args:
        text: 사용자 발화.
        today: 기준일(시점 해석).
        prev_intent: 직전 intent — 단답 후속(B2/B3) 슬롯 상속용(Question Linking의
            룰 우선 경로; 전체 연속성 엔진은 Phase 4).
        birth_year: 나이 변환(C12)용 출생 연도.

    Returns:
        intents 1개 이상을 가진 ParsedMessage(B4 다중 질문 시 복수).
    """
    # B2 단답 후속: 시점 슬롯만 교체, 나머지 직전 intent 상속.
    time_range, time_scope = parse_time(text, today, birth_year)
    if prev_intent is not None and _is_short_followup(text) and time_range is not None:
        inherited = prev_intent.model_copy(update={
            "intent_id": f"{prev_intent.intent_id}+followup",
            "time_range": time_range,
            "time_scope": time_scope,
        })
        return ParsedMessage(
            intents=[inherited], is_follow_up=True, inherited_from=prev_intent.intent_id,
        )

    pieces = _split_questions(text)
    subjects, mode = _detect_subjects(text)
    style = _detect_output_style(text)
    constraints = _detect_constraints(text)

    intents: list[IntentJson] = []
    for idx, piece in enumerate(pieces):
        domains = _detect_domains(piece) or _detect_domains(text)
        piece_time, piece_scope = parse_time(piece, today, birth_year)
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
            event_key=_detect_event(piece),
            event_keys=[],
            time_scope=piece_scope if piece_time else TimeScope.TIMELESS,
            time_range=piece_time,
            constraints=constraints,
            output=style,
        ))
    return ParsedMessage(intents=intents, output_style=style)
