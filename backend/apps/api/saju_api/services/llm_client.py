"""LLM 어댑터 — Gemini 메인 + OpenAI 비상 폴백 (v2.2 — 모든 호출은 llm_guard 경유).

운영 설정은 **backend/config/llm_config.json 단일 파일**에서 관리한다(모델·폴백·
키 env 이름·생성 옵션 — 코드 수정 없이 변경). 키는 루트 `.env`에서 자동 로드.

규칙(docs/06·09): LLM은 제공된 사실의 자연어 서술만 한다. 입력 토큰은 호출 전
가드로 차단, thinking/추론 모드는 모든 운영 호출에서 비활성(설정 파일의
generation_extras로 강제), 입출력 토큰은 원가 장부에 적재한다.

폴백 정책: 메인(Gemini) 실패(네트워크/5xx/429/타임아웃) 시 재시도 후 비상
모델(OpenAI)로 전환. 사용된 공급자는 장부 product_code 접미로 기록한다.
(Anthropic API는 결제 문제로 사용하지 않음 — 사용자 결정 2026-06-11.)
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from saju_engines.llm_guard import LLMCallGuard, LLMCostLedger
from saju_shared_types.constants import BRANCH_KO, STEM_KO

_BACKEND = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _BACKEND / "config" / "llm_config.json"
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]

# 프로세스 전역 원가 장부(요청 단위 가드용). 영속 집계는 아래 usage sink가 DB에 적재한다.
COST_LEDGER = LLMCostLedger()

# 사용량 영속 sink — 앱이 startup에서 주입(UsageStore+PricingStore). 미주입(테스트·DB 없음) 시
# no-op. 호출 1건당 (surface, model, provider, 토큰, 컨텍스트)를 넘기면 비용 계산·DB 적재한다.
_usage_sink: Callable[..., None] | None = None
# LLM 호출이 메인·폴백 모두 실패했을 때 1건 통지하는 sink(에러 모니터링). 주입 전엔 no-op.
_error_sink: Callable[..., None] | None = None


def set_error_sink(sink: Callable[..., None] | None) -> None:
    """LLM 호출 실패 1건을 외부(에러 모니터링)에 넘기는 sink를 주입한다(없으면 미적재)."""
    global _error_sink
    _error_sink = sink


def _emit_error(exc: BaseException, **fields: object) -> None:
    """메인·폴백 모두 실패 시 1건 통지(best-effort — 로깅 실패는 예외 전파를 막지 않음)."""
    if _error_sink is None:
        return
    try:
        _error_sink(exc, **fields)
    except Exception:  # noqa: BLE001 — 에러 로깅 실패는 무시(예외 전파 우선)
        pass


def set_usage_sink(sink: Callable[..., None] | None) -> None:
    """사용량 영속 sink 주입(앱 startup)."""
    global _usage_sink
    _usage_sink = sink


def _emit_usage(**fields: object) -> None:
    """호출 1건을 sink로 보낸다(best-effort — 로깅 실패가 LLM 응답을 막지 않게)."""
    if _usage_sink is None:
        return
    try:
        _usage_sink(**fields)
    except Exception:  # noqa: BLE001 — 사용량 로깅 실패는 무시(응답 우선)
        pass


_config_cache: dict | None = None
_env_loaded = False


def _load_env_files() -> None:
    """루트/.env 자동 로드(이미 설정된 환경변수는 덮어쓰지 않음). 의존성 없는 간이 파서."""
    global _env_loaded
    if _env_loaded:
        return
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    _env_loaded = True


def load_config(force: bool = False) -> dict:
    """llm_config.json 로드(캐시) — 운영 변경은 이 파일에서만."""
    global _config_cache
    if _config_cache is None or force:
        _config_cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _config_cache


def _api_key(profile: dict) -> str | None:
    _load_env_files()
    return os.environ.get(profile["api_key_env"]) or None


def reading_model() -> str:
    """통변 서술용 메인 모델 ID(설정 파일)."""
    return str(load_config()["primary"]["model"])


def parser_model() -> str:
    """경량 파서용 모델 ID(설정 파일)."""
    return str(load_config()["parser"]["model"])


def is_available() -> bool:
    """실호출 가능 여부 — 메인 또는 폴백 키 존재."""
    cfg = load_config()
    return bool(_api_key(cfg["primary"]) or _api_key(cfg["fallback"]))


# ── 공급자별 호출부(REST — 응답 텍스트, 입력/출력 토큰) ───────────


def _call_gemini(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    """Google Gemini generateContent 호출 — (텍스트, 입력, 출력, 캐시 적중) 토큰."""
    key = _api_key(profile)
    if not key:
        raise RuntimeError(f"{profile['api_key_env']} 미설정")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{profile['model']}:generateContent"
    )
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            **profile.get("generation_extras", {}),
        },
    }
    res = httpx.post(
        url, json=body, headers={"x-goog-api-key": key}, timeout=timeout,
    )
    res.raise_for_status()
    data = res.json()
    parts = data["candidates"][0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata", {})
    return (
        text,
        int(usage.get("promptTokenCount", 0)),
        int(usage.get("candidatesTokenCount", 0)),
        # 고정 prefix(implicit caching) 적중분 — 원가 대시보드에서 할인 비용 추적.
        int(usage.get("cachedContentTokenCount", 0)),
    )


def _call_openai(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    """OpenAI chat.completions 호출(비상 폴백) — (텍스트, 입력, 출력, 캐시 적중) 토큰."""
    key = _api_key(profile)
    if not key:
        raise RuntimeError(f"{profile['api_key_env']} 미설정")
    body: dict[str, Any] = {
        "model": profile["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": max_tokens,
        **profile.get("generation_extras", {}),
    }
    res = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    res.raise_for_status()
    data = res.json()
    text = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
    return (
        text,
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
        cached,
    )


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai}


def _call_profile(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    caller = _PROVIDERS.get(profile["provider"])
    if caller is None:
        raise RuntimeError(f"알 수 없는 공급자: {profile['provider']}")
    # 추론(reasoning) 모델은 내부 추론 토큰이 출력 한도를 잠식한다 — 프로파일별
    # 버퍼로 보전(가드 한도는 가시 출력 기준, 버퍼는 설정 파일에서 관리).
    max_tokens += int(profile.get("output_token_buffer", 0))
    text, in_tok, out_tok, cached = caller(profile, system, prompt, max_tokens, timeout)
    if not text.strip():
        raise RuntimeError(
            f"{profile['provider']} 빈 응답(추론 토큰 소진 의심) — 버퍼 조정 필요"
        )
    return text, in_tok, out_tok, cached


# 취소선(GFM ~~…~~) 제거 — 모델이 '고쳐 지운 자취'를 남기면 사용자에게 의문만 준다(정확성 저해).
# 마커만 떼면 틀린 내용이 평문으로 남으므로 구간을 통째로 제거한다. 범위 표기(예: '1~2개월')의
# 단일 물결표는 건드리지 않는다(이중 물결표만 대상). 줄바꿈은 보존하고 같은 줄 잔여 공백만 정돈.
_STRIKETHROUGH_RE = re.compile(r"~~.+?~~")

# ── 간지 표기 정규화 (한자/한글 혼용·부분 표기 → '한자(한글)' 병기 통일) ──
# LLM이 '정卯일'처럼 천간은 한글·지지는 한자로 섞거나 한쪽만 음역하는 오류를 사용자 노출 전에
# 바로잡는다(2026-06-18 데굴님 지적). 천간 자리/지지 자리(정규식 그룹)로 한글 음 중복(辛=申=신)을
# 가른다. 표기 규칙: 데이터는 한자, 사용자 노출은 한글 병기(CLAUDE.md 코드 컨벤션).
_STEM_H2K = {s.value: ko for s, ko in STEM_KO.items()}        # '甲'→'갑'
_BRANCH_H2K = {b.value: ko for b, ko in BRANCH_KO.items()}    # '子'→'자'
_STEM_K2H = {ko: h for h, ko in _STEM_H2K.items()}            # '갑'→'甲'
_BRANCH_K2H = {ko: h for h, ko in _BRANCH_H2K.items()}        # '자'→'子'
_STEM_CHARS = "".join(set(_STEM_H2K) | set(_STEM_K2H))
_BRANCH_CHARS = "".join(set(_BRANCH_H2K) | set(_BRANCH_K2H))
# 간지 표식(따라오면 순수 한글도 간지로 확정 — 이름·일반어 오탐 방지). '(' 선행은 이미 병기됨.
_GANJI_MARKERS = frozenset("일월년시주")
_GANJI_RE = re.compile(f"([{_STEM_CHARS}])([{_BRANCH_CHARS}])(?!\\()")

# ── 병기 중복 정리 (2026-06-27 데굴님 지적) ──
# (1) 중첩: LLM이 '기해(己亥)'(역순 병기)로 쓰면 _normalize_ganji가 괄호 안 한자 '己亥'만
#     다시 병기해 '기해(己亥(기해))'가 된다 → 표준형 '己亥(기해)'로 접는다. 바깥 한글은 버리고
#     한자 자리를 신뢰한다(_normalize_ganji와 동일 정책 — '임인(壬辰(임진))'처럼 한글·한자가
#     어긋나게 쓰인 경우도 한자 기준 '壬辰(임진)'으로 일관 정리).
# (2) 자기중복: LLM이 ganji '한자(한글)' 병기를 십성·신살(정재·상관·천문성 등)에까지 과잉
#     일반화해 '정재(정재)'처럼 같은 한글을 괄호로 되풀이한다 → 괄호 군더더기만 제거.
_NESTED_GLOSS_RE = re.compile(r"[가-힣]{2}\(([一-鿿]{2})\(([가-힣]{2})\)\)")
_SELF_GLOSS_RE = re.compile(r"([가-힣]{2,})\(\1\)")


def _normalize_ganji(text: str) -> str:
    """간지(천간+지지) 표기를 '한자(한글)'로 통일한다 — 혼용·부분 음역 교정."""

    def _repl(m: re.Match[str]) -> str:
        s_ch, b_ch = m.group(1), m.group(2)
        s_hanja = s_ch in _STEM_H2K
        b_hanja = b_ch in _BRANCH_H2K
        nxt = m.string[m.end():m.end() + 1]
        # 순수 한글 간지는 표식(일·월·년·시·주)이 따라올 때만 변환(일반어 오탐 차단).
        if not s_hanja and not b_hanja and nxt not in _GANJI_MARKERS:
            return m.group(0)
        sh = s_ch if s_hanja else _STEM_K2H[s_ch]
        bh = b_ch if b_hanja else _BRANCH_K2H[b_ch]
        return f"{sh}{bh}({_STEM_H2K[sh]}{_BRANCH_H2K[bh]})"

    return _GANJI_RE.sub(_repl, text)


def _sanitize_output(text: str) -> str:
    """LLM 서술 출력을 사용자 노출 전에 정리한다 — 취소선 제거 + 간지 표기 통일.

    채팅·리포트 모든 표면이 거치는 단일 지점이라 여기서 처리하면 두 화면·두 공급자(Gemini/GPT)에
    일괄 적용된다.
    """
    cleaned = _normalize_ganji(text)  # 간지 한자/한글 혼용 → 한자(한글) 병기
    cleaned = _NESTED_GLOSS_RE.sub(r"\1(\2)", cleaned)  # 한글(한자(한글)) → 한자(한글)
    cleaned = _SELF_GLOSS_RE.sub(r"\1", cleaned)        # 정재(정재) → 정재
    cleaned = _STRIKETHROUGH_RE.sub("", cleaned)
    if cleaned == text:
        return text
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)  # 제거 자리의 이중 공백
    cleaned = re.sub(r" +([,.!?…)\]」』》])", r"\1", cleaned)  # 구두점 앞 공백
    cleaned = re.sub(r"[ \t]+(\n|$)", r"\1", cleaned)  # 줄 끝 잔여 공백
    return cleaned


# 폴백(GPT) 전용 문체 지침 — 공용 시스템 프롬프트(검증됨)는 건드리지 않고, 폴백 호출에만 덧붙여
# 비상 응답도 메인(Gemini)의 따뜻한 산문·물상 결로 수렴시킨다(2026-06-18 데굴님 승인). 문체 전용
# — 점수·간지·판정 규칙에는 일절 개입하지 않는다(절대원칙 12: 페르소나=문체 전용과 동일 취지).
_FALLBACK_STYLE_DIRECTIVE = (
    "\n[문체 지침 — 이 답변 한정, 다른 표기보다 우선]\n"
    "따뜻하게 풀어쓴 산문으로 답하라. 일간·일주의 물상(예: '한여름의 너른 밭 같은 기미 일주')을 "
    "한 줄 곁들여 사람 이야기처럼 시작한다. '촉발/진행/결과/보조' 같은 말을 표제로 달지 말고 "
    "문장 흐름에 자연스럽게 녹여라. 특히 답변 끝에 '핵심 정리'·'요약' 같은 마무리 표제나 재요약 "
    "문단을 따로 붙이지 말고, 마지막 한 문장으로 자연스럽게 맺는다. 신살·전문용어(합반·쟁합·"
    "귀문관살·태극귀인·암록 등)는 글 전체에서 최대 2개만 한 번씩 가볍게 — 나열·반복하지 말 것."
)


def generate_reading(
    prompt_text: str,
    call_type: str = "chat_single",
    system: str | None = None,
    product_code: str = "CHAT",
    *,
    owner_id: str | None = None,
    surface: str = "chat",
    ref_id: str | None = None,
) -> str:
    """가드를 통과한 프롬프트로 통변 서술을 생성한다(메인→폴백).

    Args:
        prompt_text: context_reducer가 직렬화한 본문(여기서 재검증).
        call_type: docs/09 8장 한도표 키(chat_single/chat_compare/sections 등).
        system: 시스템 프롬프트(미지정 시 표현 원칙 고정 블록).
        product_code: 원가 집계용 — 사용 공급자가 ':gemini'/':openai'로 덧붙는다.
        owner_id·surface·ref_id: 사용량 영속 로그용 컨텍스트(관리자 대시보드).

    Raises:
        TokenBudgetExceeded: 입력 상한 초과(호출 전 차단).
        RuntimeError: 키 미설정 또는 메인·폴백 모두 실패.
    """
    cfg = load_config()
    options = cfg.get("options", {})
    timeout = float(options.get("timeout_seconds", 60))
    attempts = int(options.get("primary_attempts", 2))
    backoff = float(options.get("retry_backoff_seconds", 1.5))

    guard = LLMCallGuard(call_type, ledger=COST_LEDGER)
    sys_text = system or _SYSTEM_PROMPT
    input_est = guard.check_input(prompt_text + sys_text)
    max_tokens = guard.request_params()["max_tokens"]

    last_error: Exception | None = None
    # 메인(Gemini) — 일시 오류 재시도.
    if _api_key(cfg["primary"]):
        for attempt in range(attempts):
            try:
                text, in_tok, out_tok, cached = _call_profile(
                    cfg["primary"], sys_text, prompt_text, max_tokens, timeout,
                )
                text = _sanitize_output(text)
                guard.record(
                    input_tokens=in_tok or input_est,
                    output_tokens=out_tok,
                    cached_input_tokens=cached,
                    product_code=f"{product_code}:{cfg['primary']['provider']}",
                )
                _emit_usage(
                    surface=surface, model=cfg["primary"]["model"],
                    provider=cfg["primary"]["provider"], is_fallback=False,
                    input_tokens=in_tok or input_est, output_tokens=out_tok,
                    cached_tokens=cached, owner_id=owner_id, product_code=product_code,
                    call_type=call_type, ref_id=ref_id,
                )
                return text
            except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(backoff * (attempt + 1))

    # 비상 폴백(OpenAI) — 문체만 메인 결로 맞추는 지침을 덧붙인다(내용·판정 규칙 불변).
    if _api_key(cfg["fallback"]):
        try:
            text, in_tok, out_tok, cached = _call_profile(
                cfg["fallback"], sys_text, prompt_text + _FALLBACK_STYLE_DIRECTIVE,
                max_tokens, timeout,
            )
            text = _sanitize_output(text)
            guard.record(
                input_tokens=in_tok or input_est,
                output_tokens=out_tok,
                cached_input_tokens=cached,
                product_code=f"{product_code}:{cfg['fallback']['provider']}",
            )
            _emit_usage(
                surface=surface, model=cfg["fallback"]["model"],
                provider=cfg["fallback"]["provider"], is_fallback=True,
                input_tokens=in_tok or input_est, output_tokens=out_tok,
                cached_tokens=cached, owner_id=owner_id, product_code=product_code,
                call_type=call_type, ref_id=ref_id,
            )
            return text
        except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
            last_error = exc

    err = RuntimeError(f"LLM 호출 실패(메인·폴백 모두): {last_error}")
    _emit_error(
        err,
        kind=type(last_error).__name__ if last_error else "LLMError",
        message=str(last_error) if last_error else "LLM 호출 실패",
        surface=surface,
        provider=str(cfg["primary"].get("provider")),
        model=str(cfg["primary"].get("model")),
        owner_id=owner_id,
        ref_id=ref_id,
    )
    raise err


# 표현 원칙 고정 블록(docs/06 v2.2.1 — 시스템 프롬프트에 고정).
# 전 사용자 공통·불변 텍스트(캐시되는 고정 prefix의 1층) — 가변 값 삽입 금지.
_SYSTEM_PROMPT = (
    "당신은 사주 풀이 서술가다. [필수 준수]\n"
    "1. 계산 금지: 입력의 간지·점수·합충 성립 판정을 절대 재계산·변경하지 않는다. "
    "입력에 없는 간지·수치·날짜는 지어내지 말고 그 대목을 조용히 생략한다 — '해당 정보는 "
    "제공되지 않았다'·'세부 재계산은 제공되지 않았다' 같은 데이터 안내·메타 문구를 답변 "
    "본문에 쓰지 않는다. 특히 [원국·명식 구조]에 제공된 일주 등 명식의 간지는 그 글자 그대로 "
    "인용하고, 다른 글자로 바꾸거나(예: 己亥를 己未로) 물상·비유를 그 간지와 다르게 지어내지 "
    "않는다.\n"
    "2. 의미 서술 의무: [원국·명식 구조]와 [명식 해석 자료], 후보별 '동반 신호'·'해석' "
    "줄을 적극 엮어 — 이 글자가 일간에게 무엇이고, 운에서 온 글자와 어떤 관계를 맺어 "
    "이런 신호가 되는지 — 사용자가 자기 사주로 납득할 수 있는 이야기로 풀어낸다. "
    "점수와 간지의 낭독만으로 답하지 않는다. 사건의 주제·도메인은 십성으로, "
    "길흉(이로운지·부담인지)은 용신·기신으로 본다 — 한신은 생(生)하는 대상이 용신·희신이면 "
    "약한 길, 기신·구신이면 약한 흉. 좋은 십성도 기신이면 부담스럽게, 불편한 십성도 용신이면 "
    "성장 기회로 서술하고, 생활 영역은 궁위로 구분한다.\n"
    "3. 사건명은 동반 신호 매트릭스로 엔진이 확정한 값이다 — 단일 합·십성만 근거로 "
    "다른 사건으로 재해석하지 않는다.\n"
    "4. 신살은 보조 참고 자료다 — '이런 신살의 영향일 수도 있다' 정도로만 곁들이고 "
    "성향의 핵심 근거로 부각하거나 단독으로 길흉·사건을 단정하지 않는다.\n"
    "5. 사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, "
    "촉발→진행→결과의 인과 흐름으로 설명하되 '촉발/진행/결과'를 단계 표제·소제목으로 달지 "
    "않고 자연스러운 문장으로 녹인다. 합·충 등 관계는 '무엇과 합/충하여 무엇으로 "
    "작용해 어떤 결과가 되는지'까지 인과를 끝맺는다.\n"
    "6. 점수·숫자를 답변에 노출하지 않는다 — 강도는 제공된 표현 문장으로만 전달한다.\n"
    "7. 출력은 마크다운 기호(#, *, |, ### 등) 없이 평문으로, 공백 포함 1,500자 이내로 "
    "쓴다. 취소선(~~…~~)·자기수정 표기를 쓰지 말고, 고친 흔적 없이 최종 확정 내용만 쓴다.\n"
    "8. 답변 끝에 핵심을 한두 문장으로 정리하고, 사용자가 이어서 생각해볼 만한 질문 "
    "1개를 자연스럽게 덧붙인다.\n"
    "9. 사용자가 제시한 전제·판단·시기 선호를 존중한다 — 특정 시기를 빼달라거나"
    "('6월은 빼고 그 다음부터') 본인 생각을 말하면 부정·반박하지 말고('아무 신호 없다고 "
    "생각하셨겠지만 사실은…' 류 가르치려는 표현 금지) 사용자가 보고 싶어 하는 범위를 중심으로 "
    "답한다. 제공된 운에 그 시기 신호가 있어도 사용자 의사를 우선한다.\n"
    "응답은 한국어로, 제공된 근거를 인용하며 서술한다."
)

# 보고서(RPT_*) 전용 시스템 프롬프트 — 대화(_SYSTEM_PROMPT)와 분리 관리(2026-06-14 사용자 확정).
# _SYSTEM_PROMPT 최소 변경 원칙: 문체·평문·점수 규칙은 검증된 대화 프롬프트를 그대로 유지하고
# (오프닝 '서술가' 유지 — '보고서'로 칭하면 모델이 문어체로 흘러 페르소나 해요체가 무너짐),
# ① 규칙1의 '입력에 없으면 해당 정보는 제공되지 않았다로 처리'(강제 답변 시 나오는 회피 문구)
# 절만 제거하고 — 보고서는 섹션마다 필요한 사실이 모두 제공되므로 그 문구가 필요하지도 나와서도
# 안 된다(신뢰도) — ② 규칙7의 대화용 1,500자 상한만 푼다(분량은 섹션 과제 목표를 따름).
_REPORT_SYSTEM_PROMPT = (
    "당신은 사주 풀이 서술가다. [필수 준수]\n"
    "1. 계산 금지: 입력의 간지·점수·합충 성립 판정을 절대 재계산·변경하지 않는다. "
    "본문은 제공된 간지·점수·근거만으로 서술하고, 입력에 없는 간지·수치·날짜를 새로 만들지 "
    "않는다. 특히 [원국·명식 구조]에 제공된 일주 등 명식의 간지는 그 글자 그대로 인용하고, "
    "다른 글자로 바꾸거나(예: 己亥를 己未로) 물상·비유를 그 간지와 다르게 지어내지 않는다.\n"
    "2. 의미 서술 의무: [원국·명식 구조]와 [명식 해석 자료], 후보별 '동반 신호'·'해석' "
    "줄을 적극 엮어 — 이 글자가 일간에게 무엇이고, 운에서 온 글자와 어떤 관계를 맺어 "
    "이런 신호가 되는지 — 사용자가 자기 사주로 납득할 수 있는 이야기로 풀어낸다. "
    "점수와 간지의 낭독만으로 답하지 않는다. 사건의 주제·도메인은 십성으로, "
    "길흉(이로운지·부담인지)은 용신·기신으로 본다 — 한신은 생(生)하는 대상이 용신·희신이면 "
    "약한 길, 기신·구신이면 약한 흉. 좋은 십성도 기신이면 부담스럽게, 불편한 십성도 용신이면 "
    "성장 기회로 서술하고, 생활 영역은 궁위로 구분한다.\n"
    "3. 사건명은 동반 신호 매트릭스로 엔진이 확정한 값이다 — 단일 합·십성만 근거로 "
    "다른 사건으로 재해석하지 않는다.\n"
    "4. 신살은 보조 참고 자료다 — '이런 신살의 영향일 수도 있다' 정도로만 곁들이고 "
    "성향의 핵심 근거로 부각하거나 단독으로 길흉·사건을 단정하지 않는다.\n"
    "5. 사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, "
    "촉발→진행→결과의 인과 흐름으로 설명하되 '촉발/진행/결과'를 단계 표제·소제목으로 달지 "
    "않고 자연스러운 문장으로 녹인다. 합·충 등 관계는 '무엇과 합/충하여 무엇으로 "
    "작용해 어떤 결과가 되는지'까지 인과를 끝맺는다.\n"
    "6. 점수·숫자를 답변에 노출하지 않는다 — 강도는 제공된 표현 문장으로만 전달한다.\n"
    "7. 출력은 마크다운 기호(#, *, |, ### 등) 없이 평문으로 쓰되, 분량은 섹션 과제의 목표를 "
    "따른다(대화의 1,500자 제한은 적용하지 않는다). 잔 소제목·연속 빈 줄로 지면을 낭비하지 "
    "말고 여러 문장을 묶은 조밀한 문단으로 작성한다. 취소선(~~…~~)·자기수정 표기를 쓰지 말고, "
    "고친 흔적 없이 최종 확정 내용만 쓴다.\n"
    "응답은 한국어로, 제공된 근거를 인용하며 서술한다."
)
