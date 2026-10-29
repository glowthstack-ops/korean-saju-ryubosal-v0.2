"""LLM 입력 표기 정규화 — 범위 물결표(~) 제거 (2026-10-29).

마크다운 뷰어는 같은 줄의 ``~``와 ``~`` 사이를 취소선으로 그린다. 입력 본문의 ``~``는
범위(``2026~2035``·``345°~15°``·``1~2문장``)와 어미 자리표시(``'~할 수 있다'``)뿐인데,
검수 화면에서는 방위 값·표현 규칙이 통째로 지워진 것처럼 보였다(데굴님 2026-10-29).

규칙(docs/06 표현 원칙 8):
- 범위 ``A~B`` → ``A–B``(엔 대시 U+2013, 붙여 씀). 구분자 `` — ``(띄어 쓴 엠 대시)와 구분된다.
- 어미 자리표시 ``~할`` → ``…할``(U+2026).

정적 지시문·사전 문구는 원문을 고쳤고, 이 모듈은 **데이터에서 조립되는 범위 라벨**
(대운 기간 키 ``YYYY~YYYY``·날짜 구간·시각 구간)을 LLM 경계에서 바꾼다. 기간 키 자체는
엔진·저장소·감사 로그의 식별자라 바꾸지 않는다(``_period_level``·life_event_store 등).
"""

from __future__ import annotations

import re

# 숫자·도(°) 뒤 ~ 숫자 앞 — 공백이 있던 구간(`2026-01-01 ~ 2026-03-31`)은 ` – `로 유지한다.
_RANGE_TILDE_RE = re.compile(r"(?<=[0-9°])([ \t]*)~([ \t]*)(?=[0-9])")
# 숫자 뒤 ~ 끝(열린 범위 `2035~`) — 줄 끝·닫는 괄호·쉼표·공백 앞.
_OPEN_RANGE_TILDE_RE = re.compile(r"(?<=[0-9°세])~(?=[\s,)\]]|$)")

RANGE_DASH = "–"


def normalize_range_tilde(text: str) -> str:
    """숫자 범위의 ``~``를 ``–``로 바꾼다. 그 밖의 ``~``(사용자 발화 인용 등)는 그대로 둔다.

    Args:
        text: 프롬프트 본문 또는 시스템 프롬프트.

    Returns:
        범위 물결표만 엔 대시로 바뀐 문자열. ``~``가 없으면 같은 객체를 돌려준다.
    """
    if "~" not in text:
        return text
    out = _RANGE_TILDE_RE.sub(
        lambda m: f" {RANGE_DASH} " if (m.group(1) or m.group(2)) else RANGE_DASH, text,
    )
    return _OPEN_RANGE_TILDE_RE.sub(RANGE_DASH, out)
