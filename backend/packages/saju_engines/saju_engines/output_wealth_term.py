"""식신생재·상관생재 용어 결정론 교정 — 같은 문단의 십성과 어긋난 '○○생재'를 바로잡는다.

배경(2026-10-04 실답): "辛(신)금 식신과 亥(해)수 정재가 찾아와 상관생재의 흐름을 만드니"처럼
엔진이 준 십성은 **식신**인데 LLM이 구조 용어를 '상관생재'로 썼다. 식신이 재성을 생하면
식신생재(食神生財), 상관이 생하면 상관생재(傷官生財)다. 엔진 사전·블록에는 '상관생재' 문자열이
없어 모델 자체 어휘에서 나온 오류이며, 지시로 막기 어려운 준수 결함은 생성 후 결정론으로 고친다
(재호출 없음 — 2026-07-27 데굴님 확정 원칙).

규칙(좁게): 문단 단위로 본다. 문단에 '상관생재'가 있는데 그 문단이 십성 **식신**만 언급하고
상관은 (용어 자체를 빼면) 언급하지 않으면 '식신생재'로 바꾼다. 반대(식신생재인데 상관만 언급)도
같다. 둘 다 언급하거나 둘 다 없으면 판단 근거가 없으므로 손대지 않는다. 십성·점수·판정은 바꾸지
않는다 — 이미 문단에 적힌 십성에 용어를 맞출 뿐이다. 순수 함수.
"""

from __future__ import annotations

import re

_TERM_RE = re.compile(r"(식신|상관)생재")
_PARA_SPLIT_RE = re.compile(r"(\n\s*\n)")


def _fix_paragraph(para: str) -> tuple[str, list[tuple[str, str]]]:
    """한 문단의 '○○생재'를 그 문단이 언급한 십성(식신/상관)에 맞춘다."""
    if not _TERM_RE.search(para):
        return para, []
    bare = _TERM_RE.sub("", para)  # 용어 자체에 든 '식신'·'상관'은 언급으로 세지 않는다
    has_sik, has_sang = "식신" in bare, "상관" in bare
    if has_sik == has_sang:  # 둘 다 있거나 둘 다 없음 — 근거 없음
        return para, []
    right = "식신" if has_sik else "상관"
    changes: list[tuple[str, str]] = []

    def _repl(m: re.Match[str]) -> str:
        if m.group(1) == right:
            return m.group(0)
        changes.append((m.group(0), f"{right}생재"))
        return f"{right}생재"

    return _TERM_RE.sub(_repl, para), changes


def fix_wealth_generation_term(text: str) -> tuple[str, list[tuple[str, str]]]:
    """답변 전체에서 식신생재·상관생재 용어를 문단의 십성 언급에 맞춰 교정한다.

    Args:
        text: LLM 답변 원문.

    Returns:
        (교정된 텍스트, [(이전 용어, 바꾼 용어), ...]). 교정이 없으면 원문과 빈 목록.
    """
    if not text or "생재" not in text:
        return text, []
    parts = _PARA_SPLIT_RE.split(text)
    all_changes: list[tuple[str, str]] = []
    for idx in range(0, len(parts), 2):
        parts[idx], changes = _fix_paragraph(parts[idx])
        all_changes += changes
    if not all_changes:
        return text, []
    return "".join(parts), all_changes
