"""질문 이해 층(Question Frame) — 프롬프트·JSON 검증·룰 대조(순수 함수, LLM 호출 없음).

LLM 호출(사이드이펙트)은 서비스 계층 `saju_api.services.question_frame_service` 가 담당하고,
이 모듈은 ①분류 프롬프트 ②모델 출력 → `QuestionFrame` 검증(집합 밖 값이면 None)
③룰 intent 와의 불일치 분류만 한다. 불일치 분류는 shadow 측정의 축이며, 뒤에 게이트를 켤 때
'룰이 Q1/GENERAL 폴백으로 떨어진 턴만 보정한다'는 범위(데굴님 동의 3)를 그대로 코드 조건으로
쓴다.

점수·간지·시점·판정에는 일절 개입하지 않는다(절대 원칙 1·9) — 라우팅 라벨·답 형태 지시 전용.
"""

from __future__ import annotations

import json
import re

from saju_shared_types.intent import Domain, IntentJson, QueryType
from saju_shared_types.question_frame import (
    AnswerShape,
    AskKind,
    LifestyleItem,
    QuestionFrame,
)

QUESTION_FRAME_SYSTEM = (
    "너는 사주 상담 챗봇의 '질문 분류기'다. 사주를 풀거나 계산하지 않고, 사용자 질문 한 문장이 "
    "무엇을 어떤 형태로 묻는지만 분류한다. 아래 키를 가진 JSON 객체 하나만 출력한다"
    "(설명·마크다운 금지).\n"
    "- ask_kind: recommendation(무엇을 고를지·추천) | judgment(해도 될지·좋을지 판단) | "
    "timing(언제·시기) | explanation(왜·이유·구조 설명) | comparison(둘 이상 비교·우열) | "
    "venting(감정 토로, 질문 없음) | meta(시스템·모델·프롬프트 질문) | unknown\n"
    "- lifestyle_item: food(음식·끼니·메뉴) | color(색) | clothing(옷·복장) | "
    "direction(방향·방위·자리 배치) | place(장소·지역·여행지) | "
    "activity(운동·외출·약속 등 행동 가부) | "
    "grooming(머리·미용·외모 관리) | none(해당 없음)\n"
    "- answer_shape: short_pick(짧은 선택 추천) | analysis(흐름·근거 분석) | compare_table(비교) | "
    "timeline(시기 나열) | empathy_first(공감 우선) | policy(정책 안내·거절)\n"
    "- brevity: short | normal\n"
    "- topic_object: 질문이 실제로 묻는 대상(한국어 명사구, 20자 이내. "
    "예: '점심 메뉴', '이직 시기')\n"
    "규칙: 각 키의 값은 반드시 그 키에 적힌 후보 중 하나만 쓴다(다른 키의 후보를 섞지 말 것 — "
    "ask_kind 에 analysis/none, answer_shape 에 normal/judgment 는 틀린 값). 질문이 아니거나 "
    "뜻이 불분명한 짧은 발화는 ask_kind=unknown, answer_shape=analysis, brevity=short 로 둔다.\n"
    "예시:\n"
    '질문: 오늘 점심은 뭘 먹는게 좋을까 → {"ask_kind":"recommendation","lifestyle_item":"food",'
    '"answer_shape":"short_pick","brevity":"short","topic_object":"점심 메뉴"}\n'
    '질문: 올해 이직운 어때? → {"ask_kind":"judgment","lifestyle_item":"none",'
    '"answer_shape":"analysis","brevity":"normal","topic_object":"올해 이직 흐름"}\n'
    '질문: 언제 결혼하게 될까 → {"ask_kind":"timing","lifestyle_item":"none",'
    '"answer_shape":"timeline","brevity":"normal","topic_object":"결혼 시기"}\n'
    '질문: 아빠가 너무 혼내서 힘들어 → {"ask_kind":"venting","lifestyle_item":"none",'
    '"answer_shape":"empathy_first","brevity":"normal","topic_object":"아버지와의 갈등"}\n'
    '질문: 오늘 머리 자르러 가도 될까 → {"ask_kind":"judgment","lifestyle_item":"grooming",'
    '"answer_shape":"short_pick","brevity":"short","topic_object":"오늘 미용실"}'
)


def build_frame_prompt(question: str, prev_summary: str | None = None) -> str:
    """사용자 질문(+직전 턴 요지 한 줄) → 분류기 입력."""
    q = question.strip().replace("\n", " ")
    if prev_summary:
        return f"직전 턴 요지: {prev_summary.strip()[:80]}\n질문: {q}\nJSON:"
    return f"질문: {q}\nJSON:"


def frame_json_schema() -> dict:
    """Ollama 구조화 출력(format)에 넘길 JSON 스키마 — enum 닫힌 집합 그대로."""
    return {
        "type": "object",
        "properties": {
            "ask_kind": {"type": "string", "enum": [e.value for e in AskKind]},
            "lifestyle_item": {"type": "string", "enum": [e.value for e in LifestyleItem]},
            "answer_shape": {"type": "string", "enum": [e.value for e in AnswerShape]},
            "brevity": {"type": "string", "enum": ["short", "normal"]},
            "topic_object": {"type": "string"},
        },
        "required": ["ask_kind", "lifestyle_item", "answer_shape", "brevity", "topic_object"],
    }


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def parse_frame(text: str) -> QuestionFrame | None:
    """모델 출력 → QuestionFrame. JSON 이 아니거나 집합 밖 값이면 None(부분 채택 금지)."""
    if not text or not text.strip():
        return None
    body = _FENCE_RE.sub("", text.strip()).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(body[start:end + 1])
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    lowered = {k: (v.strip().lower() if isinstance(v, str) and k != "topic_object" else v)
               for k, v in raw.items()}
    try:
        return QuestionFrame.model_validate(lowered)
    except ValueError:
        return None


# ── 룰 대조 — shadow 측정 축이자 향후 게이트 조건 ─────────────────────

_TIMING_RULE = frozenset({QueryType.TIMING_SEARCH, QueryType.DATE_RECOMMENDATION})
_COMPARE_RULE = frozenset({QueryType.COMPARISON, QueryType.DECISION_SUPPORT})


def is_rule_fallback(intent: IntentJson) -> bool:
    """룰이 아무 규칙에도 걸리지 않아 Q1 총운 + GENERAL 로 떨어진 턴 — 프레임 보정 허용 범위."""
    return intent.query_type is QueryType.FORTUNE_OVERVIEW and intent.domain is Domain.GENERAL


def frame_disagreements(frame: QuestionFrame, intent: IntentJson) -> list[str]:
    """프레임과 룰 intent 의 불일치 라벨(없으면 빈 목록). 측정·검수용 — 라우팅을 바꾸지 않는다."""
    out: list[str] = []
    if frame.lifestyle_item is not LifestyleItem.NONE and is_rule_fallback(intent):
        out.append("lifestyle_on_overview_fallback")  # '오늘 옷 뭐 입을까' 류 — 핵심 결함군
    if (
        frame.lifestyle_item is not LifestyleItem.NONE
        and intent.query_type is QueryType.DOMAIN_ANALYSIS
    ):
        out.append("lifestyle_on_domain")  # 룰이 분야 분석으로 확정 — 보정 대상 아님, 관찰만
    if frame.ask_kind is AskKind.VENTING and intent.query_type is not QueryType.EMOTIONAL_SUPPORT:
        out.append("venting_vs_rule_analysis")
    if frame.ask_kind is not AskKind.VENTING and intent.query_type is QueryType.EMOTIONAL_SUPPORT:
        out.append("rule_venting_vs_frame_question")
    # 룰이 시점 창을 잡았으면('내년 한 해는', '5월은 어때?') 프레임의 timing 은 답 형태일 뿐 라우팅
    # 충돌이 아니다 — 시점도 시기 라우트도 없는데 프레임만 '언제'를 읽은 경우('괜찮은 때야?')만
    # 남긴다.
    if (
        frame.ask_kind is AskKind.TIMING
        and intent.query_type not in _TIMING_RULE
        and intent.time_range is None
    ):
        out.append("timing_vs_rule")
    if frame.ask_kind is AskKind.COMPARISON and intent.query_type not in _COMPARE_RULE:
        out.append("comparison_vs_rule")
    if frame.ask_kind is AskKind.META and intent.query_type is not QueryType.OUT_OF_SCOPE:
        out.append("meta_vs_rule")
    if frame.ask_kind is not AskKind.META and intent.query_type is QueryType.OUT_OF_SCOPE:
        out.append("rule_out_of_scope_vs_frame")
    return out
