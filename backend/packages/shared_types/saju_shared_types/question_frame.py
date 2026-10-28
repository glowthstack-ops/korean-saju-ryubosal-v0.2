"""질문 이해 층(Question Frame) — 소형 로컬 LLM 분류 결과의 닫힌 스키마(2026-10-28 데굴님 승인).

룰 파서(query_parser)는 어휘로 슬롯(대상·도메인·사건·시점·플래그)을 확정하는 **결정론 영역**이고,
Question Frame 은 질문 전체의 의도(무엇을·어떤 형태로 답해야 하는가)를 소형 LLM 1회 호출로 읽는
**질문 이해 영역**이다. 두 영역은 분리된다 — 프레임은 간지·점수·날짜·판정 필드를 갖지 않으며(절대
원칙 1·9), 쓰임은 ①답 형태 지시문 ②룰이 Q1/GENERAL 폴백으로 떨어진 턴의 라우팅 보정(룰 확정은
불변) 두 가지뿐이다. 도입은 shadow(로그 전용) → 불일치 표본 검수 → 게이트 ON 순서를 지킨다.

모든 값은 enum 닫힌 집합이다. 라우팅에 쓰이는 `lifestyle_item` 이 집합 밖이면 프레임 전체를
버린다(None). 형태 전용 필드(ask_kind·answer_shape·brevity)는 집합 밖 값을 기본값으로 정규화한다
(소형 모델의 키 간 후보 혼용 실측, 2026-10-28) — 지시문에만 쓰여 라우팅·점수에 닿지 않는다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AskKind(StrEnum):
    """질문이 요구하는 답의 종류."""

    RECOMMENDATION = "recommendation"  # 무엇을 고를지·추천('뭘 먹을까', '어떤 색')
    JUDGMENT = "judgment"  # 해도 될지·좋을지 판단('괜찮을까', '해도 돼?')
    TIMING = "timing"  # 언제('언제 결혼', '시기')
    EXPLANATION = "explanation"  # 왜·이유·구조 설명('왜 힘들었을까', '내 용신은')
    COMPARISON = "comparison"  # 둘 이상 비교·우열('vs', '누가 더')
    VENTING = "venting"  # 감정 토로(질문 없음)
    META = "meta"  # 시스템·모델·프롬프트 질문
    UNKNOWN = "unknown"


class LifestyleItem(StrEnum):
    """생활 선택 항목 — 오행 생활화(docs/08 D-3 5번) 분기 축."""

    FOOD = "food"  # 음식·끼니·메뉴
    COLOR = "color"  # 색
    CLOTHING = "clothing"  # 옷·복장
    DIRECTION = "direction"  # 방향·방위·자리 배치
    PLACE = "place"  # 장소·지역·여행지
    ACTIVITY = "activity"  # 운동·외출·약속·행동 가부
    GROOMING = "grooming"  # 머리·미용·외모 관리
    NONE = "none"


class AnswerShape(StrEnum):
    """답의 형태 — 풀이 지시문에만 쓰인다(점수·판정 무관)."""

    SHORT_PICK = "short_pick"  # 짧은 선택 추천
    ANALYSIS = "analysis"  # 흐름·근거 분석
    COMPARE_TABLE = "compare_table"  # 비교
    TIMELINE = "timeline"  # 시기 나열
    EMPATHY_FIRST = "empathy_first"  # 공감 우선
    POLICY = "policy"  # 정책 안내·거절


class Brevity(StrEnum):
    """분량 힌트."""

    SHORT = "short"
    NORMAL = "normal"


class TimeDirection(StrEnum):
    """질문의 시간 방향(shadow, 2026-10-28) — 룰의 회고 판정과 대조만 한다.

    대조 상대는 `chat_service._question_time_direction`. 날짜·창은 만들지 않는다.
    """

    PAST = "past"  # 이미 지난 일을 묻는다('작년에 왜 힘들었을까')
    FUTURE = "future"  # 앞으로를 묻는다('내년 이직운')
    WISH = "wish"  # 바람·소원('일 적당히 있었으면 좋겠어') — 과거형 어미여도 과거가 아니다
    COUNTERFACTUAL = "counterfactual"  # 반사실('그때 갔었으면 어땠을까')
    NONE = "none"  # 시간 방향 없음(성향·구조·정책)


class SubjectFrame(StrEnum):
    """질문이 가리키는 대상의 틀(shadow, 2026-10-28) — 누구의 사주인지 **ID 매핑은 하지 않는다**
    (별칭 레지스트리=룰). 룰이 직전 대상을 상속한 턴과 대조해 본인 복귀·확인 질문 신호로만 쓴다."""

    SELF_EXPLICIT = "self_explicit"  # 1인칭 명시('내가', '나는', '내 사주')
    COMPANION_SINGLE = "companion_single"  # 제3자 한 명('남편의 재물운')
    COMPANIONS_ONLY = "companions_only"  # 본인 제외 둘 이상('남편이랑 아들 둘만 비교')
    SELF_WITH_COMPANIONS = "self_with_companions"  # 본인 포함('남편이랑 내 궁합', '우리 둘')
    ALL = "all"  # 등록 전체('우리 가족 모두')
    UNSPECIFIED = "unspecified"  # 대상 언급 없음(직전 대상 상속 대상)


MENTIONED_PEOPLE_MAX = 5
MENTIONED_PERSON_MAX_CHARS = 10
TOPIC_OBJECT_MAX_CHARS = 20


class QuestionFrame(BaseModel):
    """소형 LLM 1회 호출의 출력(닫힌 집합). 간지·점수·날짜·판정 필드는 두지 않는다."""

    model_config = ConfigDict(extra="ignore")

    ask_kind: AskKind = AskKind.UNKNOWN
    lifestyle_item: LifestyleItem = LifestyleItem.NONE
    answer_shape: AnswerShape = AnswerShape.ANALYSIS
    brevity: Brevity = Brevity.NORMAL
    # 질문이 실제로 묻는 대상(한국어 명사구). 지시문에만 쓰이며 20자로 자른다.
    topic_object: str = Field(default="", max_length=TOPIC_OBJECT_MAX_CHARS)
    # shadow 전용(2026-10-28 데굴님 "분류 모델 병행은 제외하고 진행") — 룰 대조·측정만, 라우팅·시점·
    # 대상 확정에는 쓰지 않는다. 게이트는 측정 후 별도 승인.
    time_direction: TimeDirection = TimeDirection.NONE
    subject_frame: SubjectFrame = SubjectFrame.UNSPECIFIED
    # 질문에 등장한 사람 지칭(호칭·이름 원문, 최대 5개·각 10자). 레지스트리 매핑은 룰이 한다.
    mentioned_people: list[str] = Field(default_factory=list, max_length=MENTIONED_PEOPLE_MAX)

    @field_validator("mentioned_people", mode="before")
    @classmethod
    def _trim_people(cls, v: object) -> list[str]:
        """문자열 목록만 받는다 — 길이 상한·개수 상한으로 자르고, 빈 값·중복은 버린다."""
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            tok = item.strip().replace("\n", " ")[:MENTIONED_PERSON_MAX_CHARS]
            if tok and tok not in out:
                out.append(tok)
        return out[:MENTIONED_PEOPLE_MAX]

    @field_validator("topic_object", mode="before")
    @classmethod
    def _trim_topic(cls, v: object) -> str:
        """문자열이 아니면 빈 값, 길면 상한에서 자른다(모델이 문장을 써도 프레임은 유지)."""
        if not isinstance(v, str):
            return ""
        return v.strip().replace("\n", " ")[:TOPIC_OBJECT_MAX_CHARS]


class QuestionFrameShadow(BaseModel):
    """shadow 관측 1건 — 룰 결정과 프레임의 불일치·지연을 로그로 남긴다(답변 영향 0)."""

    question: str
    rule_query_type: str
    rule_domain: str
    frame: QuestionFrame | None = None
    ok: bool = False
    error: str | None = None
    latency_ms: int = 0
    model: str = ""
    disagreements: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    # 룰 쪽 대조값(shadow, 2026-10-28): 회고 판정('past'/'future')·대상 틀·직전 대상 상속 여부.
    rule_time_direction: str | None = None
    # 판정 근거(window_past/past_phrase/…) — 창 구조 판정은 대조에서 따로 센다.
    rule_time_reason: str | None = None
    rule_subject_frame: str | None = None
    rule_subject_inherited: bool | None = None
