"""Claude API 어댑터 — 통변 서술 호출부 (v2.2 — 모든 호출은 llm_guard를 경유).

규칙(docs/06·09): LLM은 제공된 사실의 자연어 서술만 한다. 입력 토큰은 호출 전 가드로
차단(초과 시 Context Reduction 재실행), extended thinking은 비활성(파라미터 생략),
모든 호출의 입출력 토큰을 원가 장부에 적재한다.

모델 선택(환경 변수):
  SAJU_V2_LLM_MODEL    통변 서술용 — 기본 claude-opus-4-8
  SAJU_V2_PARSER_MODEL 경량 파서용(docs/03 T3.1) — 기본 claude-haiku-4-5
API 키는 ANTHROPIC_API_KEY. 미설정이면 is_available()=False — 호출 측은 dry-run으로
직렬화 본문만 반환한다(개발/테스트 경로).
"""

from __future__ import annotations

import os

from saju_engines.llm_guard import LLMCallGuard, LLMCostLedger

DEFAULT_READING_MODEL = "claude-opus-4-8"
DEFAULT_PARSER_MODEL = "claude-haiku-4-5"

# 프로세스 전역 원가 장부(운영에서는 영속 저장소로 교체 — docs/09 8장 대시보드 원천).
COST_LEDGER = LLMCostLedger()


def reading_model() -> str:
    """통변 서술용 모델 ID."""
    return os.environ.get("SAJU_V2_LLM_MODEL", DEFAULT_READING_MODEL)


def parser_model() -> str:
    """경량 파서용 모델 ID(Query Parser 1차 — 룰 폴백은 saju_engines.query_parser)."""
    return os.environ.get("SAJU_V2_PARSER_MODEL", DEFAULT_PARSER_MODEL)


def is_available() -> bool:
    """실호출 가능 여부 — API 키 존재."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def generate_reading(
    prompt_text: str,
    call_type: str = "chat_single",
    system: str | None = None,
    product_code: str = "CHAT",
) -> str:
    """가드를 통과한 프롬프트로 통변 서술을 생성한다.

    Args:
        prompt_text: context_reducer가 직렬화한 본문(이미 가드 검증 권장 — 여기서 재검증).
        call_type: docs/09 8장 한도표 키(chat_single/chat_compare 등).
        system: 시스템 프롬프트(표현 원칙 고정 블록).
        product_code: 원가 집계용 상품 코드.

    Returns:
        LLM 서술 텍스트.

    Raises:
        TokenBudgetExceeded: 입력 상한 초과(호출 전 차단).
        RuntimeError: API 키 미설정.
    """
    if not is_available():
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — dry-run 경로를 사용하세요")

    import anthropic  # 지연 임포트 — dry-run 환경에서 SDK 미사용

    guard = LLMCallGuard(call_type, ledger=COST_LEDGER)
    input_tokens_est = guard.check_input(prompt_text + (system or ""))

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=reading_model(),
        system=system or _SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
        **guard.request_params(),  # max_tokens 상한 — thinking은 의도적 생략(비활성)
    )
    text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    guard.record(
        input_tokens=response.usage.input_tokens or input_tokens_est,
        output_tokens=response.usage.output_tokens,
        product_code=product_code,
    )
    return text


# 표현 원칙 고정 블록(docs/06 — 시스템 프롬프트에 고정).
_SYSTEM_PROMPT = (
    "당신은 사주 통변 서술가다. [필수 준수]\n"
    "1. 입력의 [이벤트 후보]/[근거 경로] 수치·간지·점수를 절대 재계산·변경하지 않는다.\n"
    "2. 사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, "
    "Trigger→진행→결과 구조로 설명한다.\n"
    "3. 입력에 없는 명리 규칙·간지·수치가 필요하면 '해당 정보는 제공되지 않았다'로 처리한다.\n"
    "4. [지시] 블록의 금기 표현과 표현 강도 가이드를 준수한다.\n"
    "응답은 한국어로, 제공된 근거를 인용하며 서술한다."
)
