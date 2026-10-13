"""관계 대상 질문 — '누가 제안을 해올까'에 운 십성을 나와의 관계 유형으로 (2026-10-13 데굴님 확정).

실로그: 해고 후 대화의 마지막 질문 "누가 제안을 해올까?"에 답이 문서운·시기만 말하고 '누구'를 답하지
않았다. 근거표(십성군 5 → 사회적/가족 관계), 천간·지지 병렬, 가족 칸은 관계 도메인 질문에서만.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate, luck_months
from saju_engines.agent_relations import (
    _PATH,
    agent_relation_lines,
    detect_agent_question,
    relation_target,
)
from saju_engines.dictionaries import TenGodRelationsFile, _lint_ten_god_relations
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, IntentJson, QueryType

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울",
    gender="male",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("누가 제안을 해올까?", True),
        ("누구한테서 연락이 올까", True),
        ("어떤 사람이 도와줄까", True),
        ("어디서 연락이 올까", True),
        ("누가 이길까?", False),                                  # 행위 동사 없는 비교
        ("이력서를 넣을까 아니면 누군가가 연락을 줄까?", False),    # 경로 질문
        ("이직할까?", False),
    ],
)
def test_detect_agent_question(text, expected):
    assert detect_agent_question(text) is expected


def test_relation_target_table():
    assert relation_target("비견", "male", False) == "동료·동기·친구·같은 업계의 수평 관계"
    assert "겁재는 경쟁자이자 협력자" in relation_target("겁재", "male", False)
    assert relation_target("정관", "female", False) == "상사·회사·조직·기관"  # 사회적 관계만
    assert relation_target("정관", "female", True).endswith("/ 가족: 남편")
    assert relation_target("정관", "male", True).endswith("/ 가족: 자녀")
    assert relation_target("편재", "male", True).endswith("/ 가족: 아내·아버지")
    assert relation_target("정재", "female", True) == "거래처·고객·조건과 보상을 쥔 실무 쪽"
    assert relation_target("식신", "male", True) == "후배·부하·제자·내 기술을 필요로 하는 쪽"
    assert relation_target("", "male", True) == ""


def test_agent_lines_list_stem_and_branch_side_by_side():
    """2026-11 己亥(데굴 명식) — 천간 己 비견·지지 亥 정재를 둘 다 관계 대상으로, 역할 병기."""
    result = calculate(_BIRTH)
    pillar = next(p for p in luck_months(_BIRTH, 2026) if p.label == "2026-11")
    lines, keys = agent_relation_lines([pillar], favorability_map(result), "male", False)
    assert lines == [
        "- 2026-11 己亥 — 천간 己 비견(비겁·용신): 동료·동기·친구·같은 업계의 수평 관계 / "
        "지지 亥 정재(재성·구신): 거래처·고객·조건과 보상을 쥔 실무 쪽"
    ]
    assert keys == ["relation:비겁@2026-11", "relation:재성@2026-11"]


def _intent(domain: Domain) -> IntentJson:
    return IntentJson(intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS, domain=domain)


def test_chat_block_uses_top_candidate_periods():
    """사건 후보 점수 상위 서로 다른 기간 2개의 운 기둥으로 블록을 만든다."""
    cands = [
        SimpleNamespace(period="2026-11", score=80), SimpleNamespace(period="2026-11", score=70),
        SimpleNamespace(period="2026-10", score=60), SimpleNamespace(period="2027-02", score=10),
    ]
    out = chat_service._agent_relation_context(
        _BIRTH, calculate(_BIRTH), _intent(Domain.CAREER), "누가 제안을 해올까?", cands,
        "2026-10",
    )
    assert out[0].startswith("[관계 대상 — 사건 후보 기간의 운 십성을 나와의 관계 유형으로")
    assert [ln.split(" ")[1] for ln in out[1:]] == ["2026-11", "2026-10"]
    assert all("가족:" not in ln for ln in out)  # 직업 질문 — 사회적 관계만


def test_chat_block_family_only_for_relationship_domain():
    cands = [SimpleNamespace(period="2026-11", score=80)]
    rel = chat_service._agent_relation_context(
        _BIRTH, calculate(_BIRTH), _intent(Domain.RELATIONSHIP), "누가 연락을 해올까?", cands,
        "2026-10",
    )
    assert any("가족: 아내" in ln for ln in rel)  # 남성 명식 — 정재=아내


def test_chat_block_absent_without_agent_question():
    out = chat_service._agent_relation_context(
        _BIRTH, calculate(_BIRTH), _intent(Domain.CAREER), "11월 취업운 어때?",
        [SimpleNamespace(period="2026-11", score=80)], "2026-10",
    )
    assert out == []


def test_chat_block_falls_back_to_current_month():
    out = chat_service._agent_relation_context(
        _BIRTH, calculate(_BIRTH), _intent(Domain.CAREER), "누가 도와줄까?", [], "2026-10",
    )
    assert len(out) == 2 and out[1].startswith("- 2026-10 戊戌")


def test_chat_prompt_has_agent_block_and_directive():
    resp = chat_service.chat(
        _BIRTH, "앞으로 2달안에 누가 취업 제안을 해올까?", date(2026, 10, 13), True,
    )
    p = resp.prompt_preview or ""
    assert "[관계 대상 — 사건 후보 기간의 운 십성을 나와의 관계 유형으로" in p
    assert "[관계 대상 질문] 사용자는 '누가'를 물었다." in p


def test_lint_catches_bad_relation_table():
    data = json.loads(_PATH.read_text(encoding="utf-8"))
    data["items"][2]["family"].append({"label": "외삼촌", "tenGods": ["정관"]})
    errors = _lint_ten_god_relations(TenGodRelationsFile.model_validate(data))
    assert any("조건 십성이 소속 밖" in e for e in errors)
