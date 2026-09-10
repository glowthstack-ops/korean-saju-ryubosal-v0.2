"""Conversation Layer 엔진 (v2.2 Phase 4 T4.2~T4.4, docs/03 A0~A3 + docs/08 F).

턴 처리 순서(절대 원칙 7 — 대상 우선 확정):
  1. Subject Resolution(A0): 별칭/관계어/인라인/누적 참조/정정 발화 해소
  2. Question Linking(A3): 룰 우선 — 참조어 → follow-up, 단답+1슬롯 → 슬롯 상속
  3. Query Parser 호출(+상속 슬롯 병합) → 상태/엔티티 갱신
  4. 반복 감지(F7): 동일 질문 2회 이상 → 다른 각도 제시 신호

애매한 연속성의 LLM 분류기(T4.3 5순위)는 운영 연동 시 llm_client 경유로 추가한다 —
본 엔진은 룰 경로의 결정론을 보장한다.
"""

from __future__ import annotations

import re
from datetime import date

from saju_shared_types.conversation import (
    ConversationState,
    EntityType,
    LinkKind,
    LinkResult,
    ResultSummaryRef,
    SubjectResolution,
    TimeExclusion,
    TrackedEntity,
)
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    ParsedMessage,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
    TimeRange,
    TimeScope,
)

from .companion_alias import (
    RELATION_SYNONYMS,
    AliasEntry,
    normalize_token,
)
from .query_parser import (
    AFFIRMATION_RE,
    INCLUSIVE_WE_RE,
    _detect_domains,
    _parse_inline_births,
    implies_self_counterpart,
    parse_message,
    strip_parenthetical,
)
from .user_facts import extract_user_facts, merge_user_facts

# 대상 정정(A10) — subject 교체 + 동일 intent 재실행.
_CORRECTION_RE = re.compile(r"헷갈려|헷갈렸|잘못\s*봤|다시\s*체크|아니\s.*사주")
# 정책 라우트 query_type — 약한 후속 상속 대상에서 제외(주제가 아니라 정책이므로).
_POLICY_QTYPES = frozenset({
    QueryType.FEEDBACK_CORRECTION, QueryType.TERMINOLOGY_EDUCATION,
    QueryType.EMOTIONAL_SUPPORT, QueryType.OUT_OF_SCOPE,
})
# 본인 복귀(A8).
_SELF_RETURN_RE = re.compile(r"본인\s*사주로|내\s*사주로\s*봐")
# 생시 미상(A13).
_TIME_UNKNOWN_RE = re.compile(r"태어난\s*시간[은는]?\s*몰라|시간\s*모름")
# 누적 참조(F4) — "앞서 물어본 2명까지 포함".
_CUMULATIVE_RE = re.compile(r"앞서\s*물어본\s*(\d+)\s*명|이전에\s*물어본")
# 명시적 대상 지칭(A9 fallback) — 등록에서 못 찾으면 임의 추정 대신 확인 질문으로 넘긴다.
# 강한 별칭(신랑/아가/N호)은 인물 지칭이 명확해 조사와 무관하게 감지('아가는'도 대상).
# '아가'는 '나아가/들어가' 부분문자열 오인 방지로 앞 한글 음절·뒤 '씨' 제외.
_STRONG_REF_RE = re.compile(r"(?<![가-힣])(\d+\s*호|신랑|아가)(?!씨)")
# 관계어(엄마/와이프/아들…)는 소유격·동반격·사주/궁합/운 인접일 때만 — 일반 주격('엄마가 …')
# 오탐 방지. '신랑'은 강한 별칭으로 이미 처리하므로 제외.
# 소유격('아들의 …')은 뒤에 풀이성 명사(사주/궁합/운 등)가 이어질 때만 대상 지칭으로 본다 —
# "이사는 아들의 교육을 위해 가는거야" 같은 문맥 언급이 확인 질문을 유발하던 결함(2026-07-12).
_REL_SYN_ALL = sorted(
    {w for ws in RELATION_SYNONYMS.values() for w in ws} - {"신랑"}, key=len, reverse=True
)
_REL_REF_RE = re.compile(
    r"(?<![가-힣])(" + "|".join(_REL_SYN_ALL) + r")(?!씨)"
    r"(?=의\s*[가-힣\s]{0,8}?(?:사주|팔자|궁합|운세|신수|운(?![동전영행]))"
    r"|이랑|랑|이라도|과|와|\s*사주|\s*궁합|\s*운세|\s*운[^동전영행]|$)"
)
# 명시적 제외 지칭(2026-07-12 실사용 결함) — "아들 사주는 빼고 봐줘 / 안 봐도 된다니까 /
# 보지 마 / 필요 없어 / 말고". 지칭 토큰 직후(정규화·공백 제거 창)에서 제외 의사가 확인되면
# 그 토큰은 대상 지정도, 미등록 확인 질문 대상도 아니다(반복 need_subject 차단).
_EXCLUDE_TAIL_RE = re.compile(
    r"^(?:이|가)?(?:사주|명식|팔자|것|거)?[은는도만]?"
    r"(?:빼|제외|안봐|안보|보지마|보지않|필요없|말고|없이)"
)


def _mention_excluded(norm_text: str, token_norm: str) -> bool:
    """정규화 텍스트에서 토큰의 모든 출현 뒤 창(12자)에 제외 표현이 있는지 검사."""
    i = norm_text.find(token_norm)
    while i != -1:
        if _EXCLUDE_TAIL_RE.search(norm_text[i + len(token_norm): i + len(token_norm) + 12]):
            return True
        i = norm_text.find(token_norm, i + 1)
    return False
# 조건 추가(F3) / 세분화(F8).
_CONSTRAINT_RE = re.compile(r"간다면|한다면|이라면|쪽으로")
# 제약 정제 후속(F8b, 2026-06-16) — 직전 질문을 좁히는 짧은 보완(요일·시간대·달력 선호·배제).
# '평일도 없어?'가 새 질문(NEW)으로 분류돼 스레드가 끊기던 결함 차단.
# 부정 존재형('12개월 내에는 없어?'·'그 전에는 없을까') 추가 — 직전 답의 시기 제안을 좁혀
# 되묻는 후속이 NEW→too_broad로 끊기던 결함(2026-07-21 데굴님 실로그).
_REFINE_RE = re.compile(
    r"평일|주말|주중|오전|오후|아침|저녁|새벽|낮|밤"
    r"|손\s*없는|공휴일|연휴|휴일"
    r"|말고|이외|외에|그\s*외|빼고"
    r"|다른\s*(?:날|거|것|쪽)|딴\s*(?:날|거)"
    r"|없(?:어|나|나요|을까|는지)"
)
_DRILL_RE = re.compile(r"세부적으로|구체적으로|시기별로|자세히")
# 새 스레드를 여는 '처음부터 다시'·새 풀이 요청 신호 — 토픽 연속 후속에서 제외(직전 분야 미상속).
_FRESH_OVERVIEW_RE = re.compile(r"총운|전체\s*운|평생|사주\s*전체|명식|처음부터|새로\s*봐")
# 요청형만 매칭 — '사주 봐줘/사주 풀어줘/사주 풀이 해줘·부탁'. '사주 풀이를 해주는 (서비스)'처럼
# 관형형('해주는')으로 이어지는 서술은 새 풀이 요청이 아니다(2026-07-22 실로그: 자기 서비스 설명
# 발화가 요청으로 오인돼 토픽 연속이 차단 → NEW → too_broad로 빠지던 결함).
_READING_REQUEST_RE = re.compile(
    r"사주\s*봐|봐\s*줘|봐주|풀어\s*[줘봐주]"
    r"|사주\s*풀이?[를은도]?\s*(?:좀\s*)?(?:해(?!\s*주는)|부탁|줘)"
)
# 일반 운세 요청('내일 운세를 알려줘'·'오늘 운세'·'하루 운세') — 도메인 키워드가 없을 때 직전 특정
# 주제(이사·재물 등)를 물려받지 않고 새 일반 운세로 리셋한다. '내일' 같은 시점 슬롯이 붙어도
# 직전 스레드를 통째 승계하던 과승계 차단(2026-07-01 데굴님 지적: '내일 운세'가 이사 답으로 샘).
_GENERAL_FORTUNE_RE = re.compile(r"운세|하루\s*운|오늘\s*하루")
# bare 절대 시점('2026년'·'2026'·'상반기') — 상대시점 정규식(올해/내년/5월)이 못 잡는 절대 연도·
# 반기 슬롯. 도메인/총운/새풀이 신호가 없을 때만 직전 스레드 시점 교체 후속으로 본다(2026-07-01
# 데굴님 지적: '난 언제쯤 돈이 생길까?' 뒤 '2026년'이 NEW로 떨어져 재물 맥락을 잃던 결함).
_BARE_ABS_TIME_RE = re.compile(r"\d{3,4}\s*년|\b\d{4}\b|상반기|하반기|연초|연말")
# 직전 제안이 '월별 흐름'을 제시했는지 — 슬롯 답변('2026년') 시 granularity를 월로 승격한다.
_OFFER_MONTHLY_RE = re.compile(r"월별|달별|월\s*단위|매월|달마다")
# 시점-탐색 질문(스스로 시점을 찾는 질문) — 직전 시점 창을 승계하면 안 된다(2026-06-23: 7/4 이사
# 지정 뒤 '연애 언제 시작?'까지 7/4에 고정되던 과잉승계 부작용). '언제'는 파서가 open_when으로
# 잡지만, '할 수 있을까/가능할까/몇 년 후'처럼 open_when이 안 붙는 표현도 함께 차단한다.
_TIME_SEEKING_RE = re.compile(
    r"언제|할\s*수\s*있을[까지]|가능할[까지]|몇\s*살|몇\s*년\s*(뒤|후)|언제부터"
)
# 장소-탐색 질문(어디서 살까·지역 추천) — '언제'가 아니라 '어디'를 묻는 공간 질문이라 직전 시점
# 창을 승계하면 안 된다(2026-06-26 데굴님 지적: 7/4 이사 지정 뒤 '서울 살 곳 추천'까지 7/4
# 일운·질문기간·이사 타이밍 장치가 통째로 승계되던 과잉승계). 추천형 거주·지역 표현을 차단한다.
_PLACE_SEEKING_RE = re.compile(
    r"살면\s*좋은|살기\s*좋은|살\s*곳|살\s*만한|거주지|어디\s*살|어디서\s*살"
    r"|어느\s*지역|어느\s*동네|지역\s*추천|동네\s*추천"
)
# 동의+이어보기('그래 봐줘'·'응 보여줘'·'좋아 계속') — 직전 답변의 제안 수락. AFFIRMATION_RE에
# '봐줘'가 없어 fullmatch 실패하고, '봐줘'가 _READING_REQUEST_RE에 걸려 '새 풀이 요청'으로
# 끊기던 결함 차단(2026-06-25 데굴님 지적: '그래 봐줘'가 직전 이직 맥락을 잃고 일반 총운으로 빠짐).
#: 도메인 중립 사건 — 사건 기본 도메인(직업)이 있지만 이사·결혼·학업 어느 스레드에나 붙는다.
#: 후속 턴이 명시 도메인어 없이 이 사건만 들고 오면 직전 스레드 도메인을 유지한다.
_DOMAIN_NEUTRAL_EVENTS = frozenset({"contract_document"})
#: 명시 연도·미래 표지 — 있으면 회고 앵커링을 하지 않는다(사용자가 미래를 말한 것).
_FUTURE_DATE_MARK_RE = re.compile(r"20\d{2}\s*년|내년|내후년|다음\s*달|내달|다음\s*주")


def _retro_anchor_bare_date(tr: TimeRange | None, today: date) -> TimeRange | None:
    """회고 스레드에서 미래로 잡힌 일·월 단위 절대 시점을 한 해 전(과거)으로 되돌린다.

    파서의 연도 미지정 날짜 규칙은 택일 의도(미래 편향)라 지난 날짜를 내년으로 올린다.
    회고 스레드에서는 반대로 지난 해 같은 날이 맞다. 되돌린 날짜가 오늘 이전일 때만 적용.
    """
    if tr is None or tr.type != "absolute" or not tr.start:
        return tr
    if tr.granularity not in (Granularity.DAY, Granularity.MONTH):
        return tr
    start, end = tr.start, tr.end or tr.start
    if len(start) < 7 or start[:10] <= today.isoformat():
        return tr  # 이미 과거·오늘이면 손대지 않는다

    def _back(label: str) -> str:
        return f"{int(label[:4]) - 1:04d}{label[4:]}"

    new_start, new_end = _back(start), _back(end)
    probe = new_start if len(new_start) >= 10 else f"{new_start}-01"
    if probe > today.isoformat():
        return tr
    return tr.model_copy(update={"start": new_start, "end": new_end})


# 동의어로 시작 + (선택)이어보기/풀이 동사로 끝나고 새 도메인이 없을 때만 직전 의도를 승계한다.
_AFFIRM_CONTINUE_RE = re.compile(
    r"^(?:그래(?:요)?|그러[자지]|응+|네+|넵|예+|어+|좋아(?:요)?|좋지|콜|오케이?|오키|ok|okay"
    r"|ㅇㅇ+|ㅇㅋ)"
    r"\s*[,.!~ㅎㅋ]*\s*"
    r"(?:봐\s*줘|봐주|보여\s*줘|풀어\s*줘|해\s*줘|계속(?:해)?|이어(?:서)?|마저|더)?"
    r"[!.~ㅎㅋ\s]*$",
    re.IGNORECASE,
)


def is_affirm_continue(text: str) -> bool:
    """'그래 봐줘'·'응 보여줘' 류 동의+이어보기인가(새 도메인 없음).

    직전 답변의 제안을 그대로 수락·이어보는 발화 판정 — 링크 승계 및 '제안 이어보기' 지시문에 공용.
    """
    return bool(_AFFIRM_CONTINUE_RE.match(text.strip())) and not _detect_domains(text)


# 결론 요구형 후속(2026-07-14 P4) — "그래서 붙는다는거야 아니라는거야?"류. 도메인 intent보다
# 상위의 대화 행위로, 새 월별 분석 대신 직전 분석의 압축 결론(1문장 결론→확실성→근거→조건)을
# 계약한다. 실측: 이 유형이 domain_analysis로 떨어져 월별 흐름을 통째 재서술하던 결함.
_CONCLUSION_SEEK_RE = re.compile(
    r"(?:그래서|결국|그러니까|그니까)[^\n]{0,40}?(?:[다이]라는\s*거야|다는\s*거야|는\s*거야)"
    r"|결론(?:이|은|만)?\s*(?:뭐|무엇|어떻|말해|알려)"
    r"|(?:된다는|안\s*된다는|맞다는|아니라는)\s*거(?:야|지|냐)"
    r"|(?:되는\s*거야|안\s*되는\s*거야)\s*(?:아니(?:야|냐))?"
    # '~(한)다는 소리야/뜻이야/말이야' 변형(2026-07-14 후속②) — '무슨 뜻이야'(용어 질문)는
    # (다는|라는) 선행 조건으로 배제된다.
    r"|[가-힣]+(?:다는|라는)\s*(?:소리|뜻|말)\s*이?[야지냐]"
)


def tr_year_span(tr: TimeRange | None) -> tuple[int, int] | None:
    """TimeRange의 연 단위 창을 (시작연, 끝연)으로 환산한다(연도 미상이면 None)."""
    if tr is None:
        return None
    ys: list[int] = []
    for key in (tr.start, tr.end):
        if key and key[:4].isdigit():
            ys.append(int(key[:4]))
    return (min(ys), max(ys)) if ys else None


def overlaps_exclusions(
    span: tuple[int, int] | None, exclusions: list[TimeExclusion]
) -> bool:
    """연도 창이 배제 목록과 겹치는가 — 승계·커밋 가드 공용."""
    if span is None:
        return False
    return any(
        not (span[1] < e.start_year or e.end_year < span[0]) for e in exclusions
    )


class ConversationEngine:
    """스레드 1개의 턴 처리기 — 상태는 호출 측이 보존/주입(저장소 분리)."""

    def __init__(
        self,
        aliases: dict[str, str] | None = None,
        alias_index: dict[str, list[AliasEntry]] | None = None,
    ) -> None:
        """대상 해소용 별칭 인덱스를 구성한다.

        Args:
            aliases: 레거시 별칭('1호'/'신랑') → companion_id(E14 학습분·테스트 호환).
            alias_index: 등록 동반자 레지스트리 기반 인덱스(별칭→AliasEntry 목록, 모호성 표현).

        둘을 단일 인덱스 ``self._index``로 병합한다 — alias_index가 SSOT, aliases는 보조.
        """
        self._index: dict[str, list[AliasEntry]] = {
            normalize_token(k): list(v) for k, v in (alias_index or {}).items()
        }
        for alias, cid in (aliases or {}).items():
            key = normalize_token(alias)
            if len(key) < 2:
                continue
            bucket = self._index.setdefault(key, [])
            if not any(e.subject_id == cid for e in bucket):
                bucket.append(AliasEntry(
                    subject_id=cid, label=alias, relation_to_user=None, source="legacy",
                ))

    # ── 공개 API ─────────────────────────────────────────────────

    def process_turn(
        self,
        state: ConversationState,
        text: str,
        today: date,
        birth_year: int | None = None,
        current_month_label: str | None = None,
    ) -> tuple[ParsedMessage, ConversationState, SubjectResolution, LinkResult]:
        """한 턴을 처리해 (파싱 결과, 갱신 상태, 대상 해소, 연속성)을 반환한다.

        current_month_label: 오늘이 속한 절기 월운 라벨(YYYY-MM) — '이번 달' 등 상대 시점을
            절기 기준으로 파싱하도록 parse_message에 전달(미주입 시 양력 폴백).
        """
        resolution = self.resolve_subjects(state, text)
        link = self.link_question(state, text)

        prev = state.last_intent if link.is_follow_up else None
        parsed = parse_message(
            text, today, prev_intent=prev, birth_year=birth_year,
            current_month_label=current_month_label,
        )

        # 슬롯 상속 보강: 파서가 직접 상속 못 한 경우(참조어형) 도메인/대상 병합.
        explicit_domains = bool(_detect_domains(text))
        prev_domain = prev.domain if prev is not None else Domain.GENERAL
        for intent in parsed.intents:
            if link.is_follow_up and intent.domain is Domain.GENERAL and link.inherited_domain:
                intent.domain = link.inherited_domain
            # 도메인 중립 사건(계약·문서)은 사건 기본 도메인(직업)으로 스레드를 갈아타지 않는다 —
            # 이사 스레드의 '계약금을 넣은 건 6월 17일이야'가 직업 도메인으로 새던 결함
            # (2026-09-06 데굴님 테스트 대화). 명시 도메인어가 있으면 전환을 존중한다.
            neutral_event = (
                link.is_follow_up and not explicit_domains
                and intent.event_key in _DOMAIN_NEUTRAL_EVENTS
                and prev_domain is not Domain.GENERAL
            )
            if neutral_event:
                intent.domain = prev_domain
                intent.domains = []
            # 의도 연속성: 후속 턴이 새 사건·도메인을 들고 오지 않은 '시점·사실 보완'(예:
            # '7월 4일은 갑오월이야')이면 직전 질문의 query_type·event_key를 이어받아 같은
            # 주제(계약·이사 평가 등)를 계속 다룬다 — 막연한 하루 운세로 리셋되지 않게.
            if link.is_follow_up and prev is not None:
                introduces_new = (
                    intent.event_key is not None and not neutral_event
                ) or explicit_domains
                weak = intent.query_type in (
                    QueryType.FORTUNE_OVERVIEW, QueryType.DOMAIN_ANALYSIS,
                )
                if (
                    not introduces_new and weak
                    and prev.query_type is not QueryType.FORTUNE_OVERVIEW
                    and prev.query_type not in _POLICY_QTYPES  # 정책류(정정·용어·공감·범위밖)
                ):
                    intent.query_type = prev.query_type
                    if intent.event_key is None:
                        intent.event_key = prev.event_key
                        intent.event_keys = intent.event_keys or list(prev.event_keys)
                    intent.relocation_kind = prev.relocation_kind
            if resolution.subjects:
                intent.subjects = resolution.subjects
                intent.subject_mode = resolution.subject_mode
                # 등록 기반 대상 해소로 비교/경쟁/다자 모드가 확정되면 질문 유형도 비교로 승격한다
                # — query_type은 parse_message에서 레지스트리 해소 전에 잡혀 비교를 놓칠 수 있다
                # (예: '지민 민수 영희 비교해줘'). 정책류(정정·용어·공감·범위밖)는 건드리지 않는다.
                if (
                    resolution.subject_mode in (
                        SubjectMode.PAIRWISE, SubjectMode.COMPARE_EXCLUDE_SELF,
                        SubjectMode.RANKING,
                    )
                    and intent.query_type not in _POLICY_QTYPES
                ):
                    intent.query_type = QueryType.COMPARISON
            if resolution.correction:
                intent.query_type = QueryType.FEEDBACK_CORRECTION

        # 회고 스레드의 연도 없는 날짜('6월 17일이야')는 과거로 앵커링한다(2026-09-06 데굴님
        # 테스트 대화: 7/4 이사 회고 뒤 '계약금 넣은 건 6월 17일'이 택일용 미래 편향으로 2027년이
        # 되어 회고가 꺼지고 다음 턴까지 미래 서술로 흐른 결함). 파서는 스레드 방향을 모르므로
        # 여기서 보정한다 — 명시 연도·미래 표지가 없고, 한 해 전 같은 날이 오늘 이전일 때만.
        if link.is_follow_up and state.last_retro and not _FUTURE_DATE_MARK_RE.search(text):
            for intent in parsed.intents:
                intent.time_range = _retro_anchor_bare_date(intent.time_range, today)

        # 이번 턴 자체 시점 보유 여부 — 배제 재요청 해제(P2)·시점 출처 메타(P7)의 근거.
        # 승계로 덮어쓰기 전에 판정해야 한다.
        primary = parsed.intents[0]
        own_time = primary.time_range is not None and bool(primary.time_range.start)

        # P2 — 배제 시점 병합: 스코프 만료 → 이번 턴 배제 추가 → 명시적 재요청 해제.
        exclusions = self._merge_time_exclusions(state, primary, link, own_time)

        # P4 — 결론 요구형 후속: 같은 주제의 결론 재확인이면 대화 행위를 표시한다.
        # 도메인 전환(다른 주제의 결론 요구)은 새 분석이므로 제외.
        if (
            link.is_follow_up and prev is not None
            and _CONCLUSION_SEEK_RE.search(text)
            and (primary.domain is prev.domain or primary.domain is Domain.GENERAL)
        ):
            for intent in parsed.intents:
                intent.dialogue_act = "conclusion_summary"
                # '~라는 소리야 뭐야'의 '뭐야'가 용어 질문(policy)으로 오분류되면 canned
                # 응답으로 빠진다 — 결론 재확인은 직전 분석 주제를 잇는다.
                if intent.query_type in _POLICY_QTYPES:
                    intent.query_type = prev.query_type
                    intent.event_key = intent.event_key or prev.event_key
                    intent.event_keys = intent.event_keys or list(prev.event_keys)

        # 도메인 승계(2026-07-23): 후속 턴이 도메인 감지 없이(GENERAL) 이어지면
        # 직전 턴의 도메인을 잇는다 — '그럼 언제야?'류 후속이 전 도메인 후보
        # (이동·계약 등)로 흩어져 엉뚱한 주제를 서술하는 결함 방지. 이번 턴이
        # 명시 도메인을 새로 감지하면 미승계(도메인 전환 존중).
        if (
            link.is_follow_up and prev is not None
            and primary.domain is Domain.GENERAL
            and prev.domain is not Domain.GENERAL
        ):
            for intent in parsed.intents:
                if intent.domain is Domain.GENERAL:
                    intent.domain = prev.domain
                    if not intent.domains:
                        intent.domains = [prev.domain]

        # 시점 슬롯은 스레드 레벨로 유지 — 후속이든 도메인 전환(link=NEW 포함)이든, 이번 턴이 자체
        # 시점을 안 들고 오고 '새 풀이/리셋' 신호도 아니면 직전 턴의 시점 창을 이어받는다(2026-06-23
        # 데굴님 지적: 8/31·9/30=2026 맥락의 후속 '대출 안 나오나?'가 link=NEW로 떨어져 막연한 미래
        # 10년 흐름으로 빠짐). 사용자가 명시 시점을 새로 주거나 총운·새 풀이를 요청하면 미승계.
        inherited_time_used = False
        last = state.last_intent
        if (
            last is not None and last.time_range is not None and last.time_range.start
            and not _FRESH_OVERVIEW_RE.search(text)
            and not _READING_REQUEST_RE.search(text)
            and not _TIME_SEEKING_RE.search(text)
            and not _PLACE_SEEKING_RE.search(text)
            # 직업 분야·적성 질문은 원국 축이라 직전 시점(예: '9월')을 잇지 않는다(2026-09-10).
            and not any(getattr(i, "career_field", False) for i in parsed.intents)
            # P2 승계 가드 — 직전 시점이 배제 창과 겹치면 오염 승계를 차단한다(배제 기간은
            # 절대 target으로 승격 금지). 시점 미확정으로 두면 broad/재질문 경로가 처리.
            and not overlaps_exclusions(tr_year_span(last.time_range), exclusions)
        ):
            for intent in parsed.intents:
                # 자체 시점이 있거나(다른 시점을 새로 지정 → 그 시점이 이후 승계 기준이 됨) '언제'
                # 개방형 시점-탐색이면 승계하지 않는다(2026-06-23 과잉승계 부작용 수정: 7/4 이사 뒤
                # '연애 언제 시작?'까지 7/4에 고정되던 결함).
                if intent.time_range is not None and (
                    intent.time_range.start or intent.time_range.type == "open_when"
                ):
                    continue
                intent.time_range = last.time_range
                # 시점 창과 함께 time_scope도 승계(2026-07-17 데굴님 지적:
                # '이후 3개월' 맥락의 후속 '건강은 어때?'가 창(90일)은
                # 이어받고 scope는 timeless로 남아 응답이 '오늘' 중심으로
                # 좁혀지던 결함). 이번 턴이 자체적으로 의미 있는 scope
                # 신호(과거 회고·인생 단계 등)를 갖고 있으면 보존하고,
                # 미확정 기본값(timeless)일 때만 직전 scope를 잇는다.
                if intent.time_scope is TimeScope.TIMELESS:
                    intent.time_scope = last.time_scope
                inherited_time_used = True

        # offer-slot: 직전 제안이 '월별 흐름'이었고 이번이 후속이면 연 단위 시점을 월별로 승격한다
        # ('어느 해의 월별 흐름?' → '2026년' = 2026년 월별). 사용자가 명시 월을 준 경우는 유지.
        if link.is_follow_up and state.last_offer and _OFFER_MONTHLY_RE.search(state.last_offer):
            for intent in parsed.intents:
                tr = intent.time_range
                if tr is not None and tr.granularity is Granularity.YEAR:
                    intent.time_range = tr.model_copy(
                        update={"granularity": Granularity.MONTH, "granularity_override": True}
                    )

        # P0 — 시점 해소 추적(대화 계층): 파싱 계층 trace에 승계·배제·행위를 덧붙인다.
        parsed.trace.update({
            "own_time": own_time,
            "inherited_time": (
                (last.time_range.start, last.time_range.end)
                if inherited_time_used and last is not None and last.time_range is not None
                else None
            ),
            "active_exclusions": [e.model_dump() for e in exclusions],
            "dialogue_act": parsed.intents[0].dialogue_act,
        })
        # 사실 원장(P0) — 주제 전환(NEW + 도메인 변경)이면 topic 스코프 사실 만료.
        topic_reset = (
            not link.is_follow_up
            and state.last_intent is not None
            and primary.domain is not state.active_topic
        )
        new_state = self._advance_state(
            state, text, parsed, resolution, exclusions, own_time,
            topic_reset=topic_reset,
        )
        return parsed, new_state, resolution, link

    @staticmethod
    def _merge_time_exclusions(
        state: ConversationState,
        intent: IntentJson,
        link: LinkResult,
        own_time: bool,
    ) -> list[TimeExclusion]:
        """배제 시점 상태 병합 (2026-07-14 P2).

        규칙: ①current_turn 스코프는 다음 턴에 만료 ②주제 전환(link=NEW)이면
        current_topic 스코프 만료(thread 스코프만 존속) ③이번 턴 명시 배제 추가
        ④이번 턴 자체 명시 시점이 배제 창과 겹치면 그 배제 해제(명시적 재요청 —
        "아까는 의미 없다 했지만 이번에는 2026년만 다시 봐줘").
        """
        turn = state.turn_no + 1
        kept = [
            e for e in state.time_exclusions
            if e.scope != "current_turn"
            and not (e.scope == "current_topic" and not link.is_follow_up)
        ]
        for it in intent.time_exclusions:
            if not any(
                k.start_year == it.start_year and k.end_year == it.end_year
                for k in kept
            ):
                kept.append(TimeExclusion(
                    start_year=it.start_year, end_year=it.end_year,
                    scope="current_topic", source_turn=turn,
                    explicit=it.explicit, reason=it.reason,
                    confidence=it.confidence,
                ))
        if own_time:
            span = tr_year_span(intent.time_range)
            if span is not None:
                kept = [
                    k for k in kept
                    if span[1] < k.start_year or k.end_year < span[0]
                ]
        return kept

    # ── T4.4 Subject Resolution (A0) ─────────────────────────────

    def resolve_subjects(self, state: ConversationState, text: str) -> SubjectResolution:
        """대상 확정 — intent보다 먼저. 모호하면 추측하지 않고 unresolved로 표시."""
        correction = bool(_CORRECTION_RE.search(text))
        time_unknown = bool(_TIME_UNKNOWN_RE.search(text))

        subjects: list[SubjectRef] = []
        unresolved: list[str] = []

        # A8 — 본인 복귀.
        if _SELF_RETURN_RE.search(text):
            return SubjectResolution(
                subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
                subject_mode=SubjectMode.SINGLE,
                correction=correction,
            )

        # A9 — 별칭/관계어/번호: 등록 동반자 인덱스 기반 최장 매칭(SSOT=레지스트리).
        # 단일 후보만 자동 해소하고, 복수 후보(ambiguous)는 추측 없이 확인 질문으로 넘긴다.
        # 괄호 주석('은행 대출(남편)')은 역할 표기이지 대상 지정이 아니므로 스캔에서 제외
        # (2026-07-22 실로그: '(남편)'이 대상 채택 → 본인 배제 companion_only 오판).
        scan_text = strip_parenthetical(text)
        norm_text = normalize_token(scan_text)
        for token, entries in self._match_aliases(scan_text):
            if _mention_excluded(norm_text, token):  # "아들 사주는 빼고" — 등록돼 있어도 제외
                continue
            uniq_ids = {ae.subject_id for ae in entries}
            if len(uniq_ids) == 1:
                ae = entries[0]
                subjects.append(SubjectRef(
                    kind=SubjectKind.COMPANION, label=ae.label or token,
                    companion_id=ae.subject_id,
                ))
            else:  # 복수 등록 대상이 같은 별칭 → 어느 분인지 확인(자동 첫 후보 선택 금지)
                unresolved.append(token)
        # 미등록 관계어/별칭 지칭(예: 배우자 미등록인데 "와이프랑 봐줘") — 임의 추정 대신 확인.
        resolved_ids = {s.companion_id for s in subjects if s.companion_id}
        ref_tokens = [m.group(1).replace(" ", "") for m in _STRONG_REF_RE.finditer(scan_text)]
        ref_tokens += [m.group(1).replace(" ", "") for m in _REL_REF_RE.finditer(scan_text)]
        for tok in ref_tokens:
            key = normalize_token(tok)
            if _mention_excluded(norm_text, key):  # 미등록 + 제외 의사 — 확인 질문 대상 아님
                continue
            already = key in self._index and any(
                ae.subject_id in resolved_ids for ae in self._index[key]
            )
            if not already and tok not in unresolved:
                unresolved.append(tok)

        # A6/A7 — 인라인 생년월일 → 임시 인물(Entity Tracking 등록은 상태 갱신에서).
        inline = _parse_inline_births(text)
        subjects += inline

        # F4 — 누적 참조: 이전 턴의 임시 인물을 집합으로 재호출.
        cumulative = _CUMULATIVE_RE.search(text)
        if cumulative:
            wanted = int(cumulative.group(1)) if cumulative.group(1) else None
            past_temps = [
                e for e in state.entities
                if e.type is EntityType.PERSON and e.attributes.get("kind") == "inline_temp"
            ]
            recall = past_temps[-wanted:] if wanted else past_temps
            for e in recall:
                subjects.append(SubjectRef(
                    kind=SubjectKind.INLINE_TEMP, label=e.label, entity_id=e.id,
                ))

        # 1인칭 복수 주어('우리가/우리는/우리 둘/우리 부부/저희가') — 동반자가 해소됐으면
        # 본인도 대상에 포함한다(2026-07-22 실로그: '우리가 주의할 점은?'+남편 첨부가 본인
        # 배제된 companion_only로 빠져 출생정보 확인 오류·남편 단독 풀이 오판). '우리 남편'
        # 소유격은 INCLUSIVE_WE_RE가 조사 필수라 매칭되지 않는다.
        if (
            subjects
            and INCLUSIVE_WE_RE.search(text)
            and not any(s.kind is SubjectKind.SELF for s in subjects)
        ):
            subjects.insert(0, SubjectRef(kind=SubjectKind.SELF, label="본인"))

        if not subjects and not unresolved:
            # 직전 턴 subject 상속, 그것도 없으면 self (A0 4순위).
            inherited = state.active_subjects or [
                SubjectRef(kind=SubjectKind.SELF, label="본인")
            ]
            subjects = list(inherited)

        mode = self._subject_mode(text, subjects, state)
        return SubjectResolution(
            subjects=subjects,
            subject_mode=mode,
            unresolved=unresolved,
            correction=correction,
            time_unknown=time_unknown,
        )

    def _match_aliases(self, text: str) -> list[tuple[str, list[AliasEntry]]]:
        """발화에서 인덱스 별칭을 최장 우선으로 찾는다(공백 정규화·짧은 키 임베딩 제외).

        정규화 텍스트에 별칭 키가 부분문자열로 존재하면 후보. 더 긴 별칭에 포함되는 짧은
        별칭은 건너뛴다(예: '큰아들' 매칭 시 '아들'은 스킵 — 잘못된 모호 판정 방지). 반환은
        (매칭 별칭, 그 별칭의 AliasEntry 목록) 목록으로, 복수 대상 판정은 호출 측이 한다.
        """
        norm = normalize_token(text)
        out: list[tuple[str, list[AliasEntry]]] = []
        accepted: list[str] = []
        for key in sorted(self._index, key=len, reverse=True):
            if key in norm and not any(key in ak for ak in accepted):
                out.append((key, self._index[key]))
                accepted.append(key)
        return out

    @staticmethod
    def _subject_mode(
        text: str, subjects: list[SubjectRef], state: ConversationState
    ) -> SubjectMode:
        if re.search(r"나를\s*제외", text):
            return SubjectMode.COMPARE_EXCLUDE_SELF
        # 관계/비교·경쟁·순위 질의 신호. 비교 대상은 등록 동반자 + 인라인 임시 인물 모두 센다.
        _companions = [s for s in subjects if s.kind is SubjectKind.COMPANION]
        _non_self = [s for s in subjects if s.kind is not SubjectKind.SELF]
        _has_self = any(s.kind is SubjectKind.SELF for s in subjects)
        _self_ref = bool(re.search(r"나랑|나하고|내가|나\s*vs|나\s*대\b|우리\s*둘|나는", text))
        _compare_kw = re.search(r"궁합|잘\s*맞|안\s*맞|비교|어울리|사이|관계", text)
        _compet_kw = re.search(
            r"누가|이길|이겨|합격|승부|당선|우승|선발|오디션|대회|붙|더\s*잘", text
        )
        _ranking_kw = re.search(r"누가|누구|순위|제일|가장|랭킹|비교|합이\s*좋은|더\s*잘", text)
        # 비교 대상 3명 이상(본인 미포함) + 비교/순위 → 다자 비교(ranking). 2명은 아래 경쟁/비교로.
        if len(_non_self) >= 3 and not _has_self and _ranking_kw:
            return SubjectMode.RANKING
        # 본인 vs 동반자 1명 경쟁/비교 — self-ref면 pairwise(build_effective_subjects가 self 삽입).
        if _self_ref and len(_companions) == 1 and (_compet_kw or _compare_kw):
            return SubjectMode.PAIRWISE
        # 상호 술어는 1인칭 생략을 허용한다 — '전남친과 다시 만날 수 있을까'에는 '나'가 없지만
        # 만나는 주체는 둘이다. _self_ref(명시적 1인칭)만 보면 이 부류를 통째로 놓친다.
        if len(_non_self) == 1 and implies_self_counterpart(text):
            return SubjectMode.PAIRWISE
        # 동반자 2명(본인 미포함) 비교/경쟁 → 동반자끼리(본인 제외). '궁합/누가 이길' 등.
        if len(_companions) == 2 and not _has_self and (_compare_kw or _compet_kw):
            return SubjectMode.COMPARE_EXCLUDE_SELF
        if re.search(r"궁합|나랑\s*맞", text):
            return SubjectMode.PAIRWISE
        if (
            re.search(r"둘\s*다|모두|종합해서", text) or INCLUSIVE_WE_RE.search(text)
        ) and len(subjects) >= 2:
            return SubjectMode.GROUP_AGGREGATE
        return state.last_intent.subject_mode if (
            state.last_intent and len(subjects) == len(state.last_intent.subjects)
            and subjects == state.last_intent.subjects
        ) else SubjectMode.SINGLE

    # ── T4.3 Question Linking (A3 — 룰 우선) ─────────────────────

    def link_question(self, state: ConversationState, text: str) -> LinkResult:
        """연속성 판별 — 룰 1~4순위(5순위 LLM 분류기는 운영 연동 시)."""
        if state.last_intent is None:
            return LinkResult(is_follow_up=False, link_kind=LinkKind.NEW)
        parent_id = state.last_intent.intent_id

        # 1순위 — 명시적 참조어/판정 인용 → follow-up 확정.
        if re.search(r"그\s*사람|그때|그\s*시기|이번\s*운|라고\s*했잖|그럼\s", text):
            kind = (
                LinkKind.CHALLENGE if re.search(r"했잖|아니야", text)
                else LinkKind.DOMAIN_SHIFT if _detect_domains(text)
                else LinkKind.TIME_SHIFT
            )
            return self._follow(parent_id, kind, state)

        # 일반 운세 요청('내일 운세를 알려줘'·'운세 알려줘') — 도메인 키워드가 없으면 직전 특정
        # 주제(이사·재물 등)를 승계하지 않고 새 일반 운세로 리셋한다(과승계 차단, 2026-07-01).
        # 시점(내일 등)은 파서가 자체 파싱하므로 NEW로 끊어도 시점은 유지된다.
        if _GENERAL_FORTUNE_RE.search(text) and not _detect_domains(text):
            return LinkResult(is_follow_up=False, link_kind=LinkKind.NEW)

        # 2순위 — 단답(10자 이하) + 슬롯 1개만 → 교체상속(B2/B3).
        compact = text.replace(" ", "")
        if len(compact) <= 10:
            if re.search(
                r"\d{1,2}월|오늘|내일|모레|글피|올해|내년|이번\s*주"
                r"|[년연월주일]\s*단위"  # '년단위였어' — 직전 질문의 기간 단위 정정(2026-06-12)
                # 상대 창 단답('12개월 내에는 없어?'·'6개월 안에는?') — 직전 의도에 창만
                # 교체하는 시점 후속(2026-07-21 데굴님 실로그: NEW→too_broad로 끊기던 결함).
                r"|\d{1,3}\s*(?:개월|년|주|일)\s*(?:안|이내|내)",
                text,
            ):
                return self._follow(parent_id, LinkKind.TIME_SHIFT, state)
            if _detect_domains(text):
                return self._follow(parent_id, LinkKind.DOMAIN_SHIFT, state)
            # bare 절대 시점('2026년'·'상반기') — 새 도메인/총운/새풀이 신호가 없을 때만 직전 스레드
            # 시점 교체 후속. parse_message(prev)의 시점 클론이 domain·query_type·event를 승계한다.
            if (
                _BARE_ABS_TIME_RE.search(text)
                and not _FRESH_OVERVIEW_RE.search(text)
                and not _READING_REQUEST_RE.search(text)
            ):
                return self._follow(parent_id, LinkKind.TIME_SHIFT, state)
            if re.search(r"남편|아내|엄마|아빠|아들|딸|\d+호", text):
                return self._follow(parent_id, LinkKind.SUBJECT_SHIFT, state)

        # 3순위 — 조건 누적(F3) / 세분화(F8).
        if _CONSTRAINT_RE.search(text) and not _detect_domains(text):
            return self._follow(parent_id, LinkKind.CONSTRAINT_ADD, state)
        # 제약 정제(F8b) — 새 도메인 없이 직전 질문을 좁히는 짧은 보완('평일도 없어?').
        if _REFINE_RE.search(text) and not _detect_domains(text) and len(compact) <= 20:
            return self._follow(parent_id, LinkKind.CONSTRAINT_ADD, state)
        if _DRILL_RE.search(text) and len(compact) <= 20:
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)

        # 정정/이의(B9·A10) — challenge.
        if _CORRECTION_RE.search(text):
            return self._follow(parent_id, LinkKind.CHALLENGE, state)

        # 단순 수락 — 직전 답변이 제안·질문으로 끝났고('…정해드릴까요?') '그래/응/부탁해'로 수락한
        # 경우. 직전 의도를 그대로 이어 같은 주제·창을 계속 다룬다(수락이 새 질문으로 끊겨 broad
        # 안내로 빠지던 결함 차단 — 2026-06-18 데굴님 지적).
        if AFFIRMATION_RE.fullmatch(text.strip()):
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)
        # 동의+이어보기('그래 봐줘') — 새 도메인 없으면 직전 의도 승계(위 _READING_REQUEST_RE
        # 가드보다 먼저 잡아 '새 풀이'로 끊기지 않게).
        if is_affirm_continue(text):
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)
        # offer-slot — 직전 답변이 제안(offer)으로 끝났고('어느 해의 월별 흐름?') 짧게 슬롯값으로
        # 답하면('2026년'·'A안') '그래' 없이도 제안 수락으로 본다. 새 도메인/총운/새풀이는 제외
        # (우선순위 #1: 명시 새 도메인 최우선). 시점 슬롯은 위 2순위가 이미 처리한다.
        if (
            state.last_offer
            and len(compact) <= 12
            and not _detect_domains(text)
            and not _FRESH_OVERVIEW_RE.search(text)
            and not _READING_REQUEST_RE.search(text)
        ):
            return self._follow(parent_id, LinkKind.TIME_SHIFT, state)
        # offer-answer(2026-07-22) — 직전 답변이 되물음/제안(offer)으로 끝났고 이번 발화가
        # 새 도메인·총운·새 풀이 신호 없는 서술형 답변이면 길이와 무관하게 직전 스레드를
        # 잇는다(위 offer-slot의 12자 제한이 문장형 답변 '…웹 서비스인데, 이미 개발은
        # 끝났어'를 NEW로 끊어 too_broad로 빠지던 공백). 시점 슬롯이 아닌 내용 답변이므로
        # drill-down으로 승계한다.
        if (
            state.last_offer
            and not _detect_domains(text)
            and not _FRESH_OVERVIEW_RE.search(text)
            and not _READING_REQUEST_RE.search(text)
        ):
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)

        # 결론 요구형(P4, 2026-07-14) — "그래서 ~라는 소리야/거야"는 같은 도메인 단어('합격')가
        # 들어 있어도 새 질문이 아니라 직전 분석의 결론 재확인이다. 도메인이 직전과 같거나
        # 미검출일 때만 후속으로 잇는다(다른 주제의 결론 요구는 새 분석 — 4순위로).
        if _CONCLUSION_SEEK_RE.search(text):
            doms = _detect_domains(text)
            if not doms or state.last_intent.domain in doms:
                return self._follow(parent_id, LinkKind.DRILL_DOWN, state)

        # 토픽 연속(2026-06-22) — 활성 스레드(직전 분야 확정)에서 '새 도메인을 안 들고 온' 충분히
        # 구체적인 후속은 직전 분야를 잇는 drill-down으로 본다(예: 관계 풀이 뒤 '주변 사람이야
        # 새로운 사람이야?'). 지시어·도메인 키워드가 없어 NEW로 떨어진 뒤 시점·분야 부재로
        # too_broad 바운스되던 결함 차단 — 기존 intent 분류(_detect_domains) 재사용. 가드: 짧은
        # 반응어('그래?')·새 풀이·리셋 요청('네 사주 봐줘'·'총운 처음부터')은 제외(새 스레드 보존).
        if (
            state.last_intent.domain is not Domain.GENERAL
            and len(compact) >= 12
            and not _detect_domains(text)
            and not _FRESH_OVERVIEW_RE.search(text)
            and not _READING_REQUEST_RE.search(text)
        ):
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)

        # 4순위 — 새로운 도메인+완결 질문 → 새 스레드 문맥.
        return LinkResult(is_follow_up=False, link_kind=LinkKind.NEW)

    @staticmethod
    def _follow(parent_id: str, kind: LinkKind, state: ConversationState) -> LinkResult:
        assert state.last_intent is not None
        return LinkResult(
            is_follow_up=True,
            parent_intent_id=parent_id,
            link_kind=kind,
            inherited_domain=state.last_intent.domain,
            inherited_subjects=state.last_intent.subjects,
        )

    # ── T4.2 Entity Tracking + 상태 전이 ─────────────────────────

    def _advance_state(
        self,
        state: ConversationState,
        text: str,
        parsed: ParsedMessage,
        resolution: SubjectResolution,
        time_exclusions: list[TimeExclusion] | None = None,
        own_time: bool = False,
        topic_reset: bool = False,
    ) -> ConversationState:
        """턴 종료 상태 — 엔티티·반복·활성 문맥·배제 시점·시점 출처·사실 원장 갱신."""
        turn = state.turn_no + 1
        intent = parsed.intents[0]
        entities = list(state.entities)

        # 인라인 임시 인물(A6/A7)은 반드시 Entity Tracking 등록 — 누적 참조(F4) 대비.
        known = {e.id for e in entities}
        for s in resolution.subjects:
            if s.kind is SubjectKind.INLINE_TEMP and s.inline_birth is not None:
                eid = s.entity_id or f"temp_{s.inline_birth.date.replace('-', '')}" + (
                    f"_{s.inline_birth.gender or 'u'}".lower()
                )
                if eid not in known:
                    entities.append(TrackedEntity(
                        id=eid, type=EntityType.PERSON, label=s.label,
                        source_turn=turn, source_role="user",
                        attributes={"kind": "inline_temp",
                                    "birth": s.inline_birth.model_dump()},
                    ))
                    known.add(eid)
        # 외부 일정 앵커(C11).
        if intent.time_range is not None:
            for a in intent.time_range.anchor_dates:
                eid = f"anchor_{a.date}"
                if eid not in known:
                    entities.append(TrackedEntity(
                        id=eid, type=EntityType.ANCHOR_DATE, label=a.label,
                        source_turn=turn, source_role="user",
                        attributes={"date": a.date},
                    ))
                    known.add(eid)

        # F7 — 동일 질문 반복 감지(정규화 비교).
        norm = re.sub(r"[\s?.!~ㅋㅎ]", "", text)
        repeat = state.repeat_count + 1 if norm == state.last_question_norm else 0

        # P7 lite — 활성 시점의 출처 메타. 명시 시점이 승계보다 우선하며, 이번 턴이
        # 시점을 못 정했으면 기존 메타 유지(낮은 신뢰 갱신이 상태를 덮지 않게).
        time_meta = state.active_time_meta
        if intent.time_range is not None and intent.time_range.start:
            time_meta = {
                "value": intent.time_range.start,
                "source_turn": turn,
                "resolution_type": "explicit" if own_time else "inherited",
                "confidence": 0.95 if own_time else 0.7,
            }

        # 사실 원장(P0, 2026-07-22) — 이번 턴 사용자 명시 사실 추출·병합(user_explicit만).
        facts = merge_user_facts(state, extract_user_facts(text, turn), topic_reset)

        return state.model_copy(update={
            "turn_no": turn,
            "active_subjects": resolution.subjects,
            "active_topic": intent.domain,
            "active_time_scope": (
                intent.time_range.start if intent.time_range else state.active_time_scope
            ),
            "active_event": intent.event_key or state.active_event,
            "last_intent": intent,
            "repeat_count": repeat,
            "last_question_norm": norm,
            "entities": entities,
            "time_exclusions": (
                time_exclusions if time_exclusions is not None else state.time_exclusions
            ),
            "active_time_meta": time_meta,
            "user_facts": facts,
        })

    # ── T4.5 claim 엔티티(시스템 답변 발) ─────────────────────────

    @staticmethod
    def register_system_results(
        state: ConversationState, summaries: list[ResultSummaryRef]
    ) -> ConversationState:
        """시스템 답변의 명리 판정/이벤트를 엔티티로 등록 — 수 턴 뒤 이의 재검산 대비."""
        entities = list(state.entities)
        known = {e.id for e in entities}
        for idx, s in enumerate(summaries):
            eid = f"claim_t{state.turn_no}_{idx}" if s.kind == "claim" else (
                f"{s.kind}_t{state.turn_no}_{idx}"
            )
            if eid in known:
                continue
            entities.append(TrackedEntity(
                id=eid,
                type=EntityType.CLAIM if s.kind == "claim" else EntityType.EVENT,
                label=s.label,
                source_turn=state.turn_no,
                source_role="assistant",
                attributes={"detail": s.detail},
            ))
        return state.model_copy(update={
            "entities": entities, "last_results": summaries,
        })
