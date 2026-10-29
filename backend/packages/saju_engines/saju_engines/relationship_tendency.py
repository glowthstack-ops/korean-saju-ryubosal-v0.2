"""관계에서 나타나기 쉬운 결 — 외부 강의 「사귈 때 조심해야 할 사주」 번역층(2026-10-29).

대조 문서: doc/v2_2/EXTERNAL_TEXT_GAP_RELATIONSHIP_TENDENCY.md. 강의의 세 축을 비낙인 서술로 옮긴다.

- 상관견관(엔진 구조 패턴 `SANGGWAN_GYEONGWAN` 성립) — 불합리를 고치자고 말하는 결,
  신약이면 구설 주의.
- 관성 가시 3개 이상 + 신약 — 원칙·고집과 강한 상대에 대한 순응이 공존, 스스로 판단·책임 습관.
- 관성 가시 0개 — 남성은 결혼 뒤 역할·책임 부담의 결, 여성은 자립의 결(배우자가 없다는 뜻 아님).
  식상 가시 3개 이상이 겹치면 결혼 뒤 역할 분담 대화 한 구절.

강의의 '조심해야 할 사주' 프레임·마마보이·무속인 예시는 낙인이라 쓰지 않는다(배우자 인연 결 비낙인
정책, 성별 성향 일반화 금지 2026-10-29). 판정·점수 불변(서술 전용). 문구는 사전
`interpretations/relationship_tendency_text.json` 에서 고르기만 한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_shared_types.manse_result import ManseV2Result

from .love_type import LOVE_TYPE_COUNT_THRESHOLD, group_visible_counts
from .wealth_capacity import _is_strong

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
#: 관성 과다 문턱(가시 글자 수) — 강의 '정관이나 편관이 세 개 이상'. 연애 유형 1단계 문턱과 같다.
OFFICER_HEAVY_COUNT = 3


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    path = dictionaries_dir / "interpretations" / "relationship_tendency_text.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["id"]: it["text"] for it in data["items"]}


def relationship_tendency_lines(result: ManseV2Result, label: str = "") -> list[str]:
    """관계에서 나타나기 쉬운 결 블록 — 조건이 하나도 없으면 빈 목록.

    Args:
        result: 대상 명식(본인 또는 궁합 상대).
        label: 대상 표기(궁합에서 '본인'·상대 이름). 비면 머리말에 붙이지 않는다.
    """
    p = result.pillars
    fa = result.force_analysis
    if p is None or fa is None:
        return []
    t = _texts()
    weak = not _is_strong(fa.strength.band, bool(fa.strength.strong_chart_gate.get("passed")))
    counts = group_visible_counts(result)
    gender = str(result.input_summary.get("gender") or "unknown")
    body: list[str] = []
    from .structure_patterns import detect_structure_patterns

    if any(x.pattern_id == "SANGGWAN_GYEONGWAN" for x in detect_structure_patterns(result)):
        body.append(t["sanggwan_gyeongwan"] + (" " + t["sanggwan_gyeongwan_weak"] if weak else ""))
    officer = counts.get("관성", 0)
    if officer >= OFFICER_HEAVY_COUNT and weak:
        body.append(t["officer_heavy_weak"])
    if officer == 0 and gender in ("male", "female"):
        line = t["no_officer_male" if gender == "male" else "no_officer_female"]
        if counts.get("식상", 0) >= LOVE_TYPE_COUNT_THRESHOLD:
            line += " " + t["no_officer_output_strong"]
        body.append(line)
    if not body:
        return []
    head = t["header"] if not label else t["header"].replace("[관계에서", f"[{label} — 관계에서", 1)
    return [head, *(f"- {x}" for x in body)]
