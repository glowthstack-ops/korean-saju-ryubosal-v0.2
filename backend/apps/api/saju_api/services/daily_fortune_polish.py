"""일주별 오늘의 운세 — LLM 배치 문장 교정 (하루 1회, JSONL).

원칙(docs/17 §0-4·검토 확정):
- LLM 은 표현만 다듬는다 — 숫자·사건·장소·로또 유무를 바꾸지 않는다. 확률
  숫자는 아예 전달하지 않는다.
- 정상 = 날짜당 1회 호출. finish 잘림이어도 자동 재호출 없음 — 완전한 JSONL
  줄만 부분 채택(최후 방어)하고 나머지는 엔진 원문 유지. 재교정은 운영자
  수동 실행으로만.
- 교정 락은 소유권 판정에만 쓰고 LLM 호출 동안 보드 값은 원문 그대로 서비스
  된다. 검증 완료 보드를 통째로 교체(SET 원자성)한다.
- 엔진이 결정론이므로 원문(raw)은 언제든 재계산 가능 — 별도 보존 불필요.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date
from typing import Any

from saju_engines.daily_fortune_cache import DailyFortuneCache
from saju_engines.daily_fortune_v2 import active_content_version
from saju_engines.daily_text_policy import strip_symbols
from saju_shared_types.daily_fortune import (
    PROMPT_VERSION,
    DailyFortuneBoard,
)

from . import llm_client
from .daily_fortune_export import write_threads_export
from .daily_fortune_service import board_ttl_seconds, get_board

logger = logging.getLogger("saju.daily_fortune.polish")

_POLISH_LOCK_TTL = 600  # 초 — LLM 타임아웃(90s)·검증·저장을 모두 덮는 lease
_CALL_TYPE = "daily_fortune_polish"

# 레코드별 출력 상한(자) — 출력 토큰 예산 산정의 근거(llm_guard 한도표 주석 참조)
# 프롬프트 개정 표식 — 감사(audit)에만 기록한다. PROMPT_VERSION 은 content_version(캐시
# namespace·베타 풀 대조)의 구성 요소라 문구 개정만으로 올리면 당일 보드가 재생성·재교정되고
# 동결된 베타 풀과 어긋난다. 개정은 다음 교정 호출부터 자연 적용된다.
PROMPT_REVISION = "2026-09-10.no-symbols"  # 이모지·특수기호 금지(데굴님 지시)
MAX_HEADLINE_CHARS = 120
MAX_PLACE_CHARS = 60
MAX_LOTTO_CHARS = 80

# 사용자 노출 금지 명리 용어(사전 테스트와 동일 기준) + 확정·과장·위험 표현
_FORBIDDEN = [
    "비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인",
    "지장간", "세운", "월운", "대운", "용신", "기신",
    "삼합", "육합", "반합", "형살", "원진", "명리", "오행", "십성", "간지",
    "반드시", "무조건", "확실히", "틀림없",  # 결과 확정 표현
    "큰돈", "대박", "일확천금", "전 재산",  # 사건 의미 과장(재물)
    "수술", "입원", "소송",  # 건강·법률 과장
]
_LOTTO_FORBIDDEN = ["당첨", "보장", "매일", "전액", "대출", "빚"]
_DIGITS = re.compile(r"[0-9]")
_SENTENCE_END = re.compile(r"[.!?]")
_HANJA_PAIR = re.compile(r"[一-鿿]{2}")  # ilju 정규화 — "甲子(갑자)" 류 방어

_SYSTEM = (
    "너는 아침 방송 운세 코너의 문장 교정가다. 아래 JSONL(한 줄 = 한 일주)의 "
    "문장을 더 자연스럽고 발랄하게 다듬어라.\n"
    "규칙(위반 시 해당 줄은 폐기된다):\n"
    "1) 다듬기만 한다 — 사건의 의미·강도·장소·로또 문구 유무를 바꾸지 않는다.\n"
    "2) 숫자·금액·퍼센트를 쓰지 않는다.\n"
    "3) 사주·명리 전문 용어를 쓰지 않는다.\n"
    "4) '반드시·무조건·확실히' 같은 결과 확정 표현을 쓰지 않는다.\n"
    "5) headline 은 최대 3문장, 짧고 구체적으로. place_phrase 에는 장소 이름을 "
    "그대로 남긴다. lotto 가 null 이면 null 로 유지한다.\n"
    "5-1) ilju 값은 입력의 ilju 를 한 글자도 바꾸지 말고 그대로 복사한다(괄호·독음 "
    "추가 금지).\n"
    "6) 응답은 입력과 동일한 구조의 JSONL 만 출력한다 — 설명·코드펜스·빈 줄 금지. "
    "각 줄: {\"ilju\":..., \"headline\":..., \"place_phrase\":..., \"lotto\":...}\n"
    # 7) 문장 결(PROMPT_REVISION 2026-09-01 데굴님 승인) — 페르소나 공통 문단(persona.py)과 같은
    # 자료(주어·목적어 생략 / 어순 변주 / 길이 변주 / 상투구 회피)를 1~3문장 카드 길이에
    # 맞춰 축약했다. 도치·말줄임표·긴 호흡은 여기 맞지 않아 뺐고, 마지막 문장은 문장 수·
    # 길이·신규 숫자 검증(validate_and_apply)과 충돌하지 않도록 기호를 원문 수준으로 묶는다.
    "7) 문장 결: 방송 대본을 읽는 게 아니라 아는 사람이 아침에 한마디 건네는 말처럼 쓴다. "
    "앞뒤로 알 수 있는 주어('당신은'·'오늘 당신의')와 되풀이되는 목적어는 빼고 이어 쓴다. "
    "문장 길이를 똑같이 맞추지 말고 한 문장은 짧게, 한 문장은 조금 길게 호흡을 달리한다. "
    "'A는 B예요' 식 설명문만 잇지 말고 문맥에 맞을 때는 행동이나 결론을 앞에 둔다. "
    "'결론적으로'·'중요한 것은'·'~하는 것이 중요해요'·'~라고 할 수 있어요' 같은 상투구는 "
    "더 구체적인 말로 바꾼다. 말줄임표·감탄 기호는 원문에 있던 만큼만 쓴다.\n"
    "8) 이모지와 장식 기호(♪ ♥ ★ ✨ 화살표 등)는 쓰지 않는다 — 문장부호는 마침표·쉼표·"
    "물음표·느낌표·가운뎃점만 쓴다.\n"
)


def build_polish_payload(board: DailyFortuneBoard) -> str:
    """LLM 입력 JSONL — 텍스트와 키만, 확률 숫자 미전달."""
    lines = []
    for f in board.fortunes:
        lines.append(json.dumps({
            "ilju": f.ilju,
            "event_key": f.headline_event_key,
            "headline": f.headline,
            "place": f.lucky_place.name,
            "place_phrase": f.lucky_place.phrase,
            "lotto": f.lotto_phrase,
        }, ensure_ascii=False))
    return "\n".join(lines)


def _reject_reason(text: str, raw: str, max_chars: int) -> str | None:
    """교정 텍스트 1개의 검증 — 통과면 None, 실패면 사유."""
    if not text or not text.strip():
        return "empty"
    if len(text) > max_chars:
        return "too_long"
    if _DIGITS.search(text) and not _DIGITS.search(raw):
        return "new_digits"
    for term in _FORBIDDEN:
        if term in text and term not in raw:
            return f"forbidden:{term}"
    return None


def validate_and_apply(
    board: DailyFortuneBoard, response_text: str
) -> tuple[DailyFortuneBoard, dict[str, Any]]:
    """LLM 응답(JSONL)을 줄 단위 검증 후 보드에 적용한 새 보드를 만든다.

    실패한 줄·누락 일주는 엔진 원문 유지. 반환 audit 은 기존 LLM 사용량 로그를
    보완하는 운영 감사용(운세 본문 이력 아님).
    """
    by_ilju = {f.ilju: f for f in board.fortunes}
    parsed: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    malformed_lines = 0
    duplicate_iljus: list[str] = []

    lines = [ln.strip() for ln in response_text.strip().splitlines() if ln.strip()]
    for ln in lines:
        if ln.startswith("```"):
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            malformed_lines += 1  # 잘린 마지막 줄 등 — 이후 줄도 개별 판단(부분 채택)
            continue
        ilju = rec.get("ilju")
        if ilju not in by_ilju and isinstance(ilju, str):
            # 모델이 "甲子(갑자)"처럼 독음을 덧붙이는 사례 방어 — 한자 2자만 추출
            m = _HANJA_PAIR.search(ilju)
            if m and m.group(0) in by_ilju:
                ilju = m.group(0)
        if ilju not in by_ilju:
            malformed_lines += 1
            continue
        if ilju in parsed:
            duplicate_iljus.append(ilju)
            continue
        parsed[ilju] = rec

    accepted: dict[str, dict[str, Any]] = {}
    for ilju, rec in parsed.items():
        raw = by_ilju[ilju]
        headline = rec.get("headline")
        place_phrase = rec.get("place_phrase")
        lotto = rec.get("lotto")
        if not isinstance(headline, str) or not isinstance(place_phrase, str):
            rejected[ilju] = "missing_fields"
            continue
        # 노출 문장 정책 — 모델이 덧붙인 이모지·장식 기호는 폐기 대신 제거하고 받는다.
        headline = strip_symbols(headline)
        place_phrase = strip_symbols(place_phrase)
        if isinstance(lotto, str):
            lotto = strip_symbols(lotto)
        rec = {**rec, "headline": headline, "place_phrase": place_phrase, "lotto": lotto}
        reason = _reject_reason(headline, raw.headline, MAX_HEADLINE_CHARS)
        if reason is None and len(_SENTENCE_END.findall(headline)) > max(
            3, len(_SENTENCE_END.findall(raw.headline))
        ):
            reason = "too_many_sentences"
        if reason is None:
            reason = _reject_reason(place_phrase, raw.lucky_place.phrase, MAX_PLACE_CHARS)
            reason = f"place_{reason}" if reason else None
        if reason is None and raw.lucky_place.name not in place_phrase:
            reason = "place_name_missing"
        # 로또 유무 불변 + 금지 표현
        if reason is None:
            if (raw.lotto_phrase is None) != (lotto is None or lotto == ""):
                reason = "lotto_presence_changed"
            elif isinstance(lotto, str) and lotto:
                lr = _reject_reason(lotto, raw.lotto_phrase or "", MAX_LOTTO_CHARS)
                if lr is not None:
                    reason = f"lotto_{lr}"
                elif any(bad in lotto for bad in _LOTTO_FORBIDDEN):
                    reason = "lotto_forbidden"
        if reason is not None:
            rejected[ilju] = reason
            continue
        accepted[ilju] = rec

    # 교정 후 당일 중복 감사 — 동일 headline 이 생기면 뒤의 것을 원문으로 회귀
    seen: set[str] = set()
    for f in board.fortunes:
        text = accepted.get(f.ilju, {}).get("headline", f.headline)
        if text in seen and f.ilju in accepted:
            del accepted[f.ilju]
            rejected[f.ilju] = "duplicate_after_polish"
            text = f.headline
        seen.add(text)

    updated = board.model_copy(deep=True)
    for f in updated.fortunes:
        rec = accepted.get(f.ilju)
        if rec is None:
            continue
        f.headline = rec["headline"]
        f.lucky_place.phrase = rec["place_phrase"]
        if f.lotto_phrase is not None:
            f.lotto_phrase = rec["lotto"]
        f.polished = True

    n_ok = len(accepted)
    updated.polish_status = (
        "POLISHED" if n_ok == len(board.fortunes) else ("PARTIAL" if n_ok else "FAILED")
    )
    audit = {
        "requested": len(board.fortunes),
        "received_lines": len(lines),
        "parsed": len(parsed),
        "accepted": n_ok,
        "rejected": len(rejected),
        "reject_reasons": rejected,
        "malformed_lines": malformed_lines,
        "duplicate_iljus": duplicate_iljus,
        "missing_iljus": sorted(set(by_ilju) - set(parsed)),
        "prompt_version": PROMPT_VERSION,
        "prompt_revision": PROMPT_REVISION,
    }
    return updated, audit


def polish_board(cache: DailyFortuneCache, d: date) -> dict[str, Any] | None:
    """보드 1개를 교정한다 — 소유권(polish 락) 획득 실패·불필요 시 None.

    날짜당 1회 원칙: 락 TTL(10분) 안의 중복 시도는 차단되고, 실패(FAILED)
    보드는 자동 재호출하지 않는다(운영자 수동 재실행 전용 경로만 허용).

    캐시 키는 조회 경로와 같은 `active_content_version` 을 쓴다 — v2 플래그가
    켜졌을 때 교정이 v1 키의 유령 보드에 붙는 사고 방지(§22-6).
    """
    version = active_content_version(d)
    board = cache.load_board(d, version)
    if board is None or board.polish_status != "RAW":
        return None
    token = cache.acquire_lock("polish", d, version, _POLISH_LOCK_TTL)
    if token is None:
        return None
    try:
        payload = build_polish_payload(board)
        try:
            response = llm_client.generate_reading(
                payload,
                call_type=_CALL_TYPE,
                system=_SYSTEM,
                product_code="DAILY",
                surface="daily_fortune",
                ref_id=d.isoformat(),
            )
        except Exception as exc:  # 공급자 실패 — 원문 유지, FAILED 마킹(자동 재시도 없음)
            logger.warning("daily fortune polish 공급자 실패 date=%s err=%s", d, exc)
            failed = board.model_copy(deep=True)
            failed.polish_status = "FAILED"
            cache.save_board(d, version, failed, board_ttl_seconds(d))
            return {"accepted": 0, "error": str(exc)}
        updated, audit = validate_and_apply(board, response)
        cache.save_board(d, version, updated, board_ttl_seconds(d))
        write_threads_export(updated)  # 교정 반영분으로 스레드 텍스트 갱신
        logger.info(
            "daily fortune polish date=%s audit=%s",
            d,
            json.dumps(audit, ensure_ascii=False),
        )
        return audit
    finally:
        cache.release_lock("polish", d, version, token)


_attempted: set[str] = set()
_attempted_mutex = threading.Lock()


def maybe_schedule_polish(cache: DailyFortuneCache, d: date) -> bool:
    """lazy 경로용 — 프로세스당 날짜·버전 1회, 데몬 스레드로 교정 예약."""
    if not llm_client.is_available():
        return False
    key = f"{d.isoformat()}|{active_content_version(d)}|{PROMPT_VERSION}"
    with _attempted_mutex:
        if key in _attempted:
            return False
        _attempted.add(key)
    threading.Thread(
        target=lambda: polish_board(cache, d), name=f"daily-polish-{d}", daemon=True
    ).start()
    return True


def generate_and_polish(cache: DailyFortuneCache, d: date) -> None:
    """익일 선생성 경로(23:50 KST 태스크·운영자 수동 실행) — 생성 후 즉시 교정."""
    get_board(cache, d)
    if llm_client.is_available():
        polish_board(cache, d)
