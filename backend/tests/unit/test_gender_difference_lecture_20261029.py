"""남녀 차이 강의 반영 고정 (2026-10-29 데굴님 결정 3건).

1. 성별 성향 일반화('여자는 합리적·남자는 뜬구름')는 명식 근거가 아니라 싣지 않는다 — 금지 가드.
2. 강의 결론(다름의 인정)만 관계·궁합 관점으로 싣는다(A안).
3. '천간=생각·지지=행동'은 고정 등식 금지를 유지하되 개념 설명용 비유는 해설 한정 예외.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.structural_context import (
    BEHAVIOR_PATTERN_DIRECTIVE,
    RELATIONSHIP_DIFFERENCE_PERSPECTIVE,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _intent(domain: Domain) -> IntentJson:
    return IntentJson(
        intent_id="t", query_type=QueryType.CHART_ANALYSIS, domain=domain,
        constraints=Constraints(),
    )


def test_perspective_carries_difference_and_gender_generalization_guard() -> None:
    p = RELATIONSHIP_DIFFERENCE_PERSPECTIVE
    assert "다름을 인정" in p and "끝내 다 이해하지 못하는" in p
    assert "성별로 성향을 일반화하지 말 것" in p and "명식 근거로만" in p
    # 답 마무리 위치는 규칙 8 소유 — 이 블록이 위치를 지정하지 않는다.
    assert "답 말미" not in p and "마지막에" not in p


def test_perspective_wired_into_relationship_context_only() -> None:
    r = calculate(BirthInput(
        birth_date=date(1990, 3, 3), birth_time="07:30:00", birth_place_name="서울",
        gender="female",
    ))
    today = date(2026, 10, 29)
    ctx = chat_service._structural_context
    rel = "\n".join(ctx(r, _intent(Domain.RELATIONSHIP), today, "연애운"))
    career = "\n".join(ctx(r, _intent(Domain.CAREER), today, "이직운"))
    assert "[관계 관점 — 다름의 인정]" in rel
    assert "[관계 관점 — 다름의 인정]" not in career


def test_compat_block_carries_perspective() -> None:
    me = calculate(BirthInput(
        birth_date=date(1990, 3, 3), birth_time="07:30:00", birth_place_name="서울",
        gender="female",
    ))
    partner = BirthInput(
        birth_date=date(1988, 7, 14), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    )
    block = chat_service._compat_prompt_block(me, partner, date(2026, 10, 29), "상대")
    assert block is not None and "[관계 관점 — 다름의 인정]" in block


def test_fixed_equation_ban_kept_with_metaphor_only_exception() -> None:
    d = BEHAVIOR_PATTERN_DIRECTIVE
    assert "고정 등식으로 치환하지 말 것" in d
    assert "비유를 해설로 쓰는 것은 허용" in d and "판정하지는 않는다" in d


def test_terminology_metaphor_is_marked_as_non_judgment() -> None:
    items = {
        it["term"]: it["definition"]
        for it in json.loads((_DICTS / "terminology.json").read_text("utf-8"))["items"]
    }
    for term, word in (("천간", "생각"), ("지지", "행동")):
        assert word in items[term] and "성향 판정 기준은 아니에요" in items[term]
