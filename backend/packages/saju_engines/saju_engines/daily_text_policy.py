"""오늘의 운세 노출 문장 정책 — 이모지·특수기호 금지 (2026-09-10 데굴님 지시).

풀이 문장(한마디·연애 한 줄·로또·행운의 장소 문구)에는 이모지와 장식 기호(♪ ♥ ★ 화살표
등)를 쓰지 않는다. 문장부호(. , ! ? · ' " ( ) ~)는 허용한다.

세 지점에서 같은 함수를 쓴다: ①사전 원본(저작 시 제거) ②LLM 교정 출력(모델이 덧붙인
기호 제거) ③서비스 응답·스레드 export(이미 캐시된 과거 계약 보드까지 정리 — 엔진 렌더는
바이트 불변이라 건드리지 않는다).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from saju_shared_types.daily_fortune import DailyFortuneBoard

#: 제거 대상 — 이모지 전 범위 + 딩벳·기호·화살표·장식 문자. 가운뎃점(·)·물결(~)은 허용.
_SYMBOL_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # 이모지(기호·픽토그램·보조)
    "☀-➿"          # 기타 기호·딩벳(☀ ★ ♥ ✨ ✔ …)
    "⬀-⯿"          # 화살표·기호 추가
    "←-⇿"          # 화살표
    "─-◿"          # 괘선·도형(■ ● ◆ …)
    "♠-♯"          # 카드·음표(♠ ♣ ♥ ♦ ♪ ♫ ♬ …) — 2600 범위에 포함되나 명시
    "✀-➿"          # 딩벳
    "〰〽㊗㊙"  # 〰 〽 ㊗ ㊙
    "‍️"           # ZWJ·이모지 변형 선택자
    "⁉‼™ℹ"  # ⁉ ‼ ™ ℹ
    "❤❥❣"     # ❤ ❥ ❣
    "©®"           # © ®
    "　"                 # 전각 공백은 일반 공백으로 접힌다
    "]"
)
#: 기호가 문장 끝(어절 끝)에 붙어 있었으면 마침표로 대체한다 — "잘 풀려요♪" → "잘 풀려요."
_WORD_END_RE = re.compile(r"[가-힣A-Za-z0-9)]")


def strip_symbols(text: str) -> str:
    """이모지·장식 기호를 제거한다. 문장 끝 기호는 마침표로, 그 외는 공백 정리.

    Args:
        text: 노출 문장.

    Returns:
        기호가 없는 문장. 원문에 기호가 없으면 그대로(바이트 불변).
    """
    if not text or not _SYMBOL_RE.search(text):
        return text
    out: list[str] = []
    i = 0
    for m in _SYMBOL_RE.finditer(text):
        out.append(text[i:m.start()])
        prev = text[m.start() - 1] if m.start() > 0 else ""
        nxt = text[m.end()] if m.end() < len(text) else ""
        # 어절 끝에 붙은 기호(뒤가 끝/공백) → 마침표. 이미 문장부호가 앞에 있으면 그냥 제거.
        if _WORD_END_RE.match(prev or " ") and (nxt == "" or nxt.isspace()):
            out.append(".")
        i = m.end()
    out.append(text[i:])
    cleaned = "".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([.,!?])", r"\1", cleaned)
    cleaned = re.sub(r"\.{2,}(?!\.)", ".", cleaned)
    return cleaned.strip()


def has_symbols(text: str) -> bool:
    """이모지·장식 기호 포함 여부(테스트·감사용)."""
    return bool(_SYMBOL_RE.search(text or ""))


def sanitize_board(board: DailyFortuneBoard) -> DailyFortuneBoard:
    """보드의 노출 문장에서 기호를 제거한 **복사본**을 돌려준다(원본·캐시 불변).

    기호가 하나도 없으면 원본 객체를 그대로 돌려준다(복사 비용·바이트 불변 보존).
    """
    fields = []
    for f in board.fortunes:
        fields += [f.headline, f.love_line or "", f.lotto_phrase or "", f.lucky_place.phrase]
    if not any(has_symbols(x) for x in fields):
        return board
    out = board.model_copy(deep=True)
    for f in out.fortunes:
        f.headline = strip_symbols(f.headline)
        if f.love_line:
            f.love_line = strip_symbols(f.love_line)
        if f.lotto_phrase:
            f.lotto_phrase = strip_symbols(f.lotto_phrase)
        f.lucky_place.phrase = strip_symbols(f.lucky_place.phrase)
    return out
