"""층위 라벨 정합 감사(2026-10-25 데굴님 승인) — 재호출 없는 결정론 교정.

답변의 "대운의 壬·세운의 丁·월운 午" 같은 표기에서 그 글자가 해당 층위 간지에 없으면 잘못 붙인
층위다(실답: 원국 월간 丁을 "세운의 丁"으로). 글자의 실제 자리가 **하나**로 정해지면 그 라벨로 바꿔
쓰고(원국 월간 丁 / 대운 壬), 여러 자리에 있으면 층위 표현만 지우며(丁), 어디에도 없으면 판단하지
않고 둔다. 한글 병기('丁(정화)')는 보존한다. 로그 `layer_label_fixed`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from .layer_labels import (
    LUCK_LAYER_ORDER,
    is_stem_char,
    luck_layers_of,
    natal_label,
    natal_positions_of,
)

_LAYER_WORDS = {"대운": "대운", "세운": "세운", "월운": "월운", "일운": "일진", "일진": "일진"}
#: '세운의 丁(정화)' / '대운 壬' / '월운에서 午(오)' — 층위어 + 조사 + 글자 1자 + 선택 병기.
_LAYER_CHAR_RE = re.compile(
    r"(?P<layer>대운|세운|월운|일운|일진)(?P<josa>의|에서|에|\s)\s*"
    r"(?P<char>[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥])(?![甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥])"
    r"(?P<gloss>\([가-힣]{1,3}\))?"
)


class LayerLabelAudit(BaseModel):
    """감사 결과 — `text` 는 교정본, `fixes` 는 '세운의 丁→원국 월간 丁' 기록."""

    text: str
    fixes: list[str]


def _true_label(
    char: str, stack_ganji: dict[str, str], natal_pillars: dict[str, str],
) -> str | None:
    """글자의 실제 자리 라벨. 하나면 그 라벨, 여럿이면 ''(층위어 삭제), 없으면 None(판단 보류)."""
    layers = luck_layers_of(char, stack_ganji)
    natal = natal_positions_of(char, natal_pillars)
    total = len(layers) + len(natal)
    if total == 0:
        return None
    if total > 1:
        return ""
    return layers[0] if layers else natal_label(natal[0], char)


def audit_layer_labels(
    answer: str, stack_ganji: dict[str, str], natal_pillars: dict[str, str],
) -> LayerLabelAudit:
    """층위어가 잘못 붙은 글자 표기를 바로잡는다.

    Args:
        answer: LLM 답변.
        stack_ganji: 이번 턴 운 스택 {'대운': '壬辰', '세운': '丙午', ...}.
        natal_pillars: 원국 {'year': '庚申', 'month': '丁亥', ...}.
    """
    if not answer or not stack_ganji:
        return LayerLabelAudit(text=answer, fixes=[])
    fixes: list[str] = []

    def _fix(m: re.Match[str]) -> str:
        layer = _LAYER_WORDS[m.group("layer")]
        char = m.group("char")
        g = stack_ganji.get(layer) or ""
        idx = 0 if is_stem_char(char) else 1
        if len(g) >= 2 and g[idx] == char:
            return m.group(0)  # 맞는 표기
        true = _true_label(char, stack_ganji, natal_pillars)
        if true is None:
            return m.group(0)
        gloss = m.group("gloss") or ""
        new = f"{true} {char}{gloss}" if true else f"{char}{gloss}"
        fixes.append(f"{m.group('layer')}{m.group('josa').strip()} {char}→{new}")
        return new

    text = _LAYER_CHAR_RE.sub(_fix, answer)
    return LayerLabelAudit(text=text, fixes=fixes)


__all__ = ["LUCK_LAYER_ORDER", "LayerLabelAudit", "audit_layer_labels"]
