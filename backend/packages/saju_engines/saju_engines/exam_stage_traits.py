"""합격 준비 성향 서술층 — 원국 식상·재성 다자일 때 준비 방식 해설 한 줄(2026-11-11).

외부 '합격운' 글 대조(doc/v2_2/EXTERNAL_TEXT_GAP_EXAM_LUCK_POST.md)에서 5번(식상이 강하면 면접·
실기)·6번(재성이 강하면 실무 경력)만 채택했다. 같은 글의 시기 주장(관성·인성이 겹치는 달 등)은
실사례 측정(`scripts/measure_exam_outcome_patterns.py`)에서 변별력이 확인되지 않아 싣지 않는다.

- 판정은 십성다자 SSOT(`love_type.excess_groups` — 같은 십성군 가시 글자 3개 이상)를 그대로 쓴다.
  새 임계·새 규칙을 만들지 않는다.
- 문구는 `interpretations/exam_stage_traits.json` 에서 고르기만 한다.
- 서술 전용이다 — 점수·순위·시기·길흉 판정에 개입하지 않고, 당락을 말하지 않는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_shared_types.manse_result import ManseV2Result

from .love_type import excess_groups

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

#: 블록 머리 — 판정이 아니라 준비 방식 해설임을 밝힌다.
EXAM_STAGE_HEADER = "[합격 준비 성향 — 원국 십성 구성 해설(참고·판정 아님)]"
#: 블록 사용 규칙 — 당락·시기 근거로 쓰지 못하게 막는다.
EXAM_STAGE_RULE = (
    "(위 줄은 준비 방식 조언으로만 1~2문장 쓸 것. 합격·불합격이나 합격 시기의 근거로 쓰지 말고, "
    "'~에서 강점이 드러나기 쉽다'·'~를 함께 살펴볼 만하다'처럼 가능성으로 말할 것.)"
)


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    """십성군 → 문구(사전 원본, 캐시)."""
    path = dictionaries_dir / "interpretations" / "exam_stage_traits.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["group"]: it["text"] for it in data["items"]}


def exam_stage_trait_lines(result: ManseV2Result) -> list[str]:
    """원국 식상·재성 다자일 때 합격 준비 성향 블록(머리 + 항목 + 규칙). 해당 없으면 빈 목록.

    Args:
        result: 만세 결과(pillars 필수 — 없으면 빈 목록).

    Returns:
        프롬프트에 그대로 싣는 줄 목록. 식상·재성 모두 다자면 글자 수가 많은 군부터 두 줄.
    """
    if result.pillars is None:
        return []
    texts = _texts()
    items = [
        f"- {texts[group]} (원국 {group} {count}글자)"
        for group, count in excess_groups(result)
        if group in texts
    ]
    if not items:
        return []
    return [EXAM_STAGE_HEADER, *items, EXAM_STAGE_RULE]
