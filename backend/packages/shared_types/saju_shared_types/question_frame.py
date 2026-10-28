"""질문 이해 층(Question Frame) — 소형 로컬 LLM 분류 결과의 닫힌 스키마(2026-10-28 데굴님 승인).

룰 파서(query_parser)는 어휘로 슬롯(대상·도메인·사건·시점·플래그)을 확정하는 **결정론 영역**이고,
Question Frame 은 질문 전체의 의도(무엇을·어떤 형태로 답해야 하는가)를 소형 LLM 1회 호출로 읽는
**질문 이해 영역**이다. 두 영역은 분리된다 — 프레임은 간지·점수·날짜·판정 필드를 갖지 않으며(절대
원칙 1·9), 쓰임은 ①답 형태 지시문 ②룰이 Q1/GENERAL 폴백으로 떨어진 턴의 라우팅 보정(룰 확정은
불변) 두 가지뿐이다. 도입은 shadow(로그 전용) → 불일치 표본 검수 → 게이트 ON 순서를 지킨다.

모든 값은 enum 닫힌 집합이다. 모델이 집합 밖 값을 내면 프레임 전체를 버린다(None) — 부분 채택 금지.
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
