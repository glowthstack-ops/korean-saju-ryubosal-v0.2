"""'조건부 유리함' 류 판정 라벨 직역 교정 (2026-10-29 데굴님 지적).

명확한 답 계약 ①의 3진 판정(유리/불리/조건부)은 유지하되 '조건부'라는 낱말은 답에 쓰지 않고 결과와
조건을 풀어 말한다. AI 말투 사전 D-15 가 문체 지시·감지 로그를 맡는다(자동 교정 없음).
"""

from __future__ import annotations

import pytest

from saju_engines.ai_tell_audit import audit_ai_tells, build_style_directive
from saju_engines.structural_context import ANSWER_CLARITY_DIRECTIVE

_USER_EXAMPLE_BEFORE = (
    "현실적인 실속을 차리기까지는 꼼꼼한 조건 확인과 시간이 필요한 조건부 유리함이 나타납니다."
)
_USER_EXAMPLE_AFTER = (
    "결과는 긍정적이겠지만, 현실적인 성과를 얻기 위해서는 꼼꼼한 조건 확인과 기다릴 줄 아는 "
    "여유가 필요합니다."
)


def _ids(text: str) -> set[str]:
    return {f.id for f in audit_ai_tells(text).findings}


def test_clarity_contract_keeps_three_way_but_bans_the_word() -> None:
    d = ANSWER_CLARITY_DIRECTIVE
    assert "유리/불리/조건부" in d  # 3진 판정 자체는 유지(기존 고정 단언)
    assert "'조건부'라는 낱말은 쓰지 말고" in d and "기다릴 줄 아는 여유" in d
    assert "조건부다'" not in d and "조건이 갖춰지면 있다" in d


@pytest.mark.parametrize("scope", ["chat", "report"])
def test_style_directive_carries_d15(scope: str) -> None:
    assert "조건부 유리함" in build_style_directive(scope)


@pytest.mark.parametrize("text", [
    _USER_EXAMPLE_BEFORE,
    "실속 면에서는 꼼꼼한 확인이 필요한 조건부 흐름을 보입니다.",
    "2027년은 조건부 진행의 해로 보고 움직이세요.",
    "성격은 조건부예요.",
    "꼼꼼한 검토가 필요한 조건부의 성격이 강해요.",
    "- 10월(戊戌, 조건부·취업·합격 우세): 촉발",
])
def test_label_phrasings_are_flagged(text: str) -> None:
    assert "D-15" in _ids(text)


@pytest.mark.parametrize("text", [
    _USER_EXAMPLE_AFTER,
    "조건을 꼼꼼히 확인하면 결과는 긍정적일 거예요.",
    "계약 조건의 실속을 따져보는 조건부 수락의 태도가 좋아요.",  # 실제 계약 용어는 허용
])
def test_natural_phrasings_are_not_flagged(text: str) -> None:
    assert "D-15" not in _ids(text)
