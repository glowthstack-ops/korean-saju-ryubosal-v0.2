"""질문 이해 층(Question Frame) 서비스 — 소형 로컬 LLM 호출·shadow 관측(2026-10-28 데굴님 승인).

순수 로직(프롬프트·검증·룰 대조)은 `saju_engines.question_frame` 에 있고, 여기는 사이드이펙트만 —
`llm_client.call_role_raw("question_frame", …)` 호출, 지연 측정, shadow 기록
(프로세스 로그 + JSONL).

**shadow 단계 계약**: `observe_async` 는 백그라운드 스레드에서 돌고 결과를 어디에도
돌려주지 않는다 — 답변·라우팅·점수에 영향 0, 호출 지연 0. 측정(불일치율·지연)과 표본 검수를
거친 뒤에만 게이트(룰 Q1/GENERAL 폴백 턴 한정 보정)를 별도 승인으로 켠다. 서버 부재·타임아웃·
파싱 실패는 전부 `ok=False` 관측 1건으로만 남고 예외를 밖으로 내지 않는다(절대 원칙 11 —
보조 기능 부재가 차단 금지).
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from saju_engines.question_frame import (
    QUESTION_FRAME_SYSTEM,
    apply_frame_correction,
    build_frame_prompt,
    frame_disagreements,
    is_rule_fallback,
    parse_frame,
)
from saju_shared_types.intent import IntentJson
from saju_shared_types.question_frame import QuestionFrameShadow

from . import llm_client

_logger = logging.getLogger(__name__)

ROLE = "question_frame"
ENV_FLAG = "SAJU_QUESTION_FRAME_SHADOW"
GATE_FLAG = "SAJU_QUESTION_FRAME_GATE"  # 2026-10-28 데굴님 "우선 켜고" — 색·방향·음식·장소 보정
_REPO_ROOT = Path(__file__).resolve().parents[5]
SHADOW_PATH = _REPO_ROOT / "var" / "question_frame_shadow.jsonl"
_MAX_OUTPUT_TOKENS = 120

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qframe")


def enabled() -> bool:
    """shadow 관측 ON 여부 — 환경 플래그 '1' + 설정에 question_frame 역할이 있을 때만."""
    # 루트 .env 의 플래그·Ollama 주소를 지연 로드(앱 기동 전 호출 대비).
    llm_client._load_env_files()
    if os.environ.get(ENV_FLAG, "0") != "1":
        return False
    try:
        return ROLE in llm_client.load_config()
    except Exception:  # noqa: BLE001 — 설정 결함은 shadow 를 끄는 쪽으로만 작용
        return False


def _timeout_seconds() -> float:
    opts = llm_client.load_config().get("options", {})
    return float(opts.get("question_frame_timeout_seconds", 3.0))


def observe_sync(
    question: str,
    intent: IntentJson,
    *,
    thread_id: str | None = None,
    prev_summary: str | None = None,
) -> QuestionFrameShadow:
    """프레임 1회 호출 + 룰 대조 → 관측 1건(예외 없음). 측정 스크립트와 백그라운드 관측이 공용."""
    shadow = QuestionFrameShadow(
        question=question,
        rule_query_type=intent.query_type.value,
        rule_domain=intent.domain.value,
        thread_id=thread_id,
    )
    t0 = time.monotonic()
    try:
        shadow.model = str(llm_client.load_config()[ROLE]["model"])
        text, _in_tok, _out_tok = llm_client.call_role_raw(
            ROLE, QUESTION_FRAME_SYSTEM, build_frame_prompt(question, prev_summary),
            max_tokens=_MAX_OUTPUT_TOKENS, timeout=_timeout_seconds(),
            surface="question_frame", ref_id=thread_id,
        )
        frame = parse_frame(text)
        if frame is None:
            shadow.error = f"parse_failed: {text[:120]!r}"
        else:
            shadow.frame = frame
            shadow.ok = True
            shadow.disagreements = frame_disagreements(frame, intent)
    except Exception as exc:  # noqa: BLE001 — 로컬 모델 부재·타임아웃은 관측 실패 1건일 뿐
        shadow.error = f"{type(exc).__name__}: {str(exc)[:160]}"
    shadow.latency_ms = int((time.monotonic() - t0) * 1000)
    return shadow


def _record(shadow: QuestionFrameShadow) -> None:
    """프로세스 로그 1줄 + JSONL append(best-effort). 둘 다 실패해도 조용히 넘긴다."""
    payload = shadow.model_dump(mode="json")
    _logger.info("question_frame_shadow %s", json.dumps(payload, ensure_ascii=False))
    try:
        SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SHADOW_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        _logger.debug("question_frame_shadow jsonl write skipped: %s", exc)


def gate_enabled() -> bool:
    """보정 게이트 ON 여부 — `SAJU_QUESTION_FRAME_GATE=1` + 역할 설정. shadow 플래그와 독립."""
    llm_client._load_env_files()
    if os.environ.get(GATE_FLAG, "0") != "1":
        return False
    try:
        return ROLE in llm_client.load_config()
    except Exception:  # noqa: BLE001
        return False


def correct_if_fallback(
    question: str,
    intent: IntentJson,
    *,
    thread_id: str | None = None,
) -> tuple[IntentJson, bool]:
    """게이트 ON + 룰 Q1/GENERAL 폴백 턴이면 프레임을 **동기** 호출해 보정 → (intent, 관측 여부).

    보정 범위는 `apply_frame_correction`(색·방향·음식·장소만). 호출 실패·파싱 실패·게이트 밖
    항목이면 원본 그대로. 관측은 shadow 와 같은 기록 경로에 `applied:<item>` 라벨을 더해 남겨
    실답 재검수가 가능하게 한다. 폴백 턴이 아니면 호출하지 않고 (intent, False) — 호출자는 그때
    shadow 로 넘긴다.
    """
    if not gate_enabled() or not is_rule_fallback(intent):
        return intent, False
    shadow = observe_sync(question, intent, thread_id=thread_id)
    new_intent = intent
    if shadow.frame is not None:
        new_intent, label = apply_frame_correction(intent, shadow.frame, question)
        if label is not None:
            shadow.disagreements = [*shadow.disagreements, label]
    _record(shadow)
    return new_intent, True


_WARM_UP_TIMEOUT_SECONDS = 180.0


def warm_up(*, block: bool = False) -> bool:
    """로컬 모델을 미리 적재한다(shadow·게이트 중 하나라도 ON 일 때만) → 제출/수행 여부.

    실측(2026-10-28): 4.6GB 모델 콜드 로드는 3초 타임아웃 안에 끝나지 않고, 타임아웃으로 끊긴 연결은
    Ollama 가 적재 자체를 중단해("client connection closed before llama-server finished loading")
    다음 호출도 또 콜드 로드가 된다 — 긴 타임아웃의 예열 호출 1회가 필요하다. 프로파일 keep_alive
    (24h)로 적재를 유지한다. 실패는 로그 1줄, 예외 없음.
    """
    if not (enabled() or gate_enabled()):
        return False

    def _run() -> None:
        t0 = time.monotonic()
        try:
            llm_client.call_role_raw(
                ROLE, QUESTION_FRAME_SYSTEM, build_frame_prompt("안녕"),
                max_tokens=16, timeout=_WARM_UP_TIMEOUT_SECONDS, surface="question_frame_warmup",
            )
            _logger.info("question_frame warm-up ok %dms", int((time.monotonic() - t0) * 1000))
        except Exception as exc:  # noqa: BLE001 — 예열 실패는 기능을 막지 않는다
            _logger.warning("question_frame warm-up failed: %s: %s", type(exc).__name__, exc)

    if block:
        _run()
        return True
    try:
        _EXECUTOR.submit(_run)
    except RuntimeError:
        return False
    return True


def observe_async(
    question: str,
    intent: IntentJson,
    *,
    thread_id: str | None = None,
    prev_summary: str | None = None,
) -> bool:
    """플래그 ON 이면 백그라운드 관측을 제출하고 True. 호출자는 결과를 기다리지도 받지도 않는다."""
    if not enabled():
        return False
    snapshot = intent.model_copy(deep=True)

    def _run() -> None:
        _record(observe_sync(question, snapshot, thread_id=thread_id, prev_summary=prev_summary))

    try:
        _EXECUTOR.submit(_run)
    except RuntimeError as exc:  # 인터프리터 종료 중 제출 — 관측 생략
        _logger.debug("question_frame_shadow submit skipped: %s", exc)
        return False
    return True
