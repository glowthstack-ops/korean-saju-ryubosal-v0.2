"""섹션 금지 주장 감사 — 배포 전 결정적 차단 2건 (2026-07-30).

    W-05   windfall 근거로 상속 시기 단정 금지
    RL-05  이동 위험 근거로 계약 하자·법적 분쟁 시기 단정 금지

핵심은 **오탐하지 않는 것**이다. 단어 포함만 보면 '단정하기 어렵다' 같은 안전 문장이
차단되고, 그러면 감사가 정확성을 해친다. 그래서 부정 창 기계를 재사용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_engines.section_claim_audit import (  # noqa: E402
    CLAIM_CONTRACT_DEFECT_OCCURRENCE,
    CLAIM_INHERITANCE_OCCURRENCE,
    CLAIM_INHERITANCE_TIMING,
    CLAIM_LEGAL_DISPUTE_OCCURRENCE,
    CLAIM_LEGAL_DISPUTE_TIMING,
    SectionClaimPolicy,
    audit_section_claims,
    claim_directive,
)

_W05 = SectionClaimPolicy(
    section_id="W-05",
    allowed_claims=frozenset({
        "windfall_signal_present", "windfall_signal_limited", "windfall_timing",
    }),
    forbidden_claims=frozenset({
        CLAIM_INHERITANCE_TIMING, CLAIM_INHERITANCE_OCCURRENCE,
    }),
)
_RL05 = SectionClaimPolicy(
    section_id="RL-05",
    allowed_claims=frozenset({"relocation_volatility", "contract_terms_check"}),
    forbidden_claims=frozenset({
        CLAIM_CONTRACT_DEFECT_OCCURRENCE, CLAIM_LEGAL_DISPUTE_TIMING,
        CLAIM_LEGAL_DISPUTE_OCCURRENCE,
    }),
)


# ── 차단해야 하는 것 ──────────────────────────────────────────────────────


def test_inheritance_timing_is_blocked() -> None:
    """windfall 근거로 상속 시기를 말하면 위반."""
    text = "2028년 11월에는 상속으로 자산이 들어올 가능성이 높습니다."
    v = audit_section_claims(text, _W05)
    assert {x.claim_id for x in v} == {
        CLAIM_INHERITANCE_TIMING, CLAIM_INHERITANCE_OCCURRENCE,
    }
    assert v[0].sentence.startswith("2028년 11월")


def test_occurrence_claims_need_no_timing_expression() -> None:
    """이름이 `_occurrence` 면 판정도 시기를 요구하지 않아야 한다."""
    assert {x.claim_id for x in audit_section_claims(
        "이번 이사에서는 계약 하자가 발생할 가능성이 높습니다.", _RL05
    )} == {CLAIM_CONTRACT_DEFECT_OCCURRENCE}
    assert CLAIM_INHERITANCE_OCCURRENCE in {
        x.claim_id for x in audit_section_claims(
            "상속으로 재산이 들어올 수 있습니다.", _W05)
    }
    assert CLAIM_LEGAL_DISPUTE_OCCURRENCE in {
        x.claim_id for x in audit_section_claims(
            "두 사람 사이에 법적 분쟁이 생길 수 있습니다.", _RL05)
    }


@pytest.mark.parametrize("text", [
    "계약 하자가 발생한다고 단정할 수 없습니다.",
    "상속 가능성을 확인할 근거는 제한적입니다.",
    "법적 분쟁이 생긴다는 뜻은 아닙니다.",
])
def test_hedged_occurrence_is_allowed(text: str) -> None:
    """유보·부정 문장을 차단하면 감사가 정확성을 해친다."""
    assert audit_section_claims(text, _RL05) == ()
    assert audit_section_claims(text, _W05) == ()


def test_timing_and_event_in_different_sentences_are_not_combined() -> None:
    """다른 문장의 '시기' 와 '상속' 을 합쳐 차단하면 안 된다."""
    text = "2028년 11월은 변화가 큰 시기입니다. 원국에는 상속 관련 구조가 있습니다."
    assert audit_section_claims(text, _W05) == ()


def test_contract_defect_timing_is_blocked() -> None:
    text = "2027년 3월에는 계약 하자가 발생할 수 있으니 주의하세요."
    v = audit_section_claims(text, _RL05)
    assert CLAIM_CONTRACT_DEFECT_OCCURRENCE in {x.claim_id for x in v}


def test_legal_dispute_timing_is_blocked() -> None:
    text = "내년 상반기에 법적 분쟁으로 이어질 수 있습니다."
    v = audit_section_claims(text, _RL05)
    assert CLAIM_LEGAL_DISPUTE_TIMING in {x.claim_id for x in v}


# ── 오탐하면 안 되는 것 ───────────────────────────────────────────────────


def test_negated_claim_is_not_a_violation() -> None:
    """'상속 시기로 단정할 수 없다' 는 안전 문장이다 — 차단하면 정확성을 해친다."""
    text = "2028년 11월을 상속 시기로 단정할 수는 없습니다."
    assert audit_section_claims(text, _W05) == ()


def test_general_structure_talk_without_timing_is_allowed() -> None:
    """시기 표현이 없으면 일반 구조 설명이다 — 차단 대상은 시기 단정이다."""
    text = "원국에 상속·증여와 연결되는 재성 구조가 있습니다."
    assert audit_section_claims(text, _W05) == ()


def test_contract_check_advice_is_allowed() -> None:
    """'계약 조건을 확인하라' 는 대응 조언이고 사건 예측이 아니다."""
    text = (
        "2027년 3월은 이동 부담이 큰 구간이라 비용·해지 조건을 꼼꼼히 확인하세요."
    )
    assert audit_section_claims(text, _RL05) == ()


def test_other_sections_are_untouched() -> None:
    """금지 claim 이 없는 정책은 아무것도 차단하지 않는다."""
    text = "2028년 11월에는 상속으로 자산이 들어올 가능성이 높습니다."
    empty = SectionClaimPolicy(section_id="W-04")
    assert audit_section_claims(text, empty) == ()


def test_unimplemented_forbidden_claims_are_not_silently_counted() -> None:
    """구현되지 않은 claim 을 hard block 으로 계상하지 않는다(과대 보고 방지)."""
    pol = SectionClaimPolicy(
        section_id="W-04", forbidden_claims=frozenset({"income_increase_timing"})
    )
    assert pol.hard_blocked() == frozenset()
    assert audit_section_claims("2027년 2월 수입이 늘어납니다.", pol) == ()


# ── 프롬프트 지시 ────────────────────────────────────────────────────────


def test_directive_is_generated_from_the_same_policy() -> None:
    """감사와 지시가 서로 다른 정책을 읽으면 drift 가 난다."""
    d = claim_directive(_RL05)
    assert CLAIM_CONTRACT_DEFECT_OCCURRENCE in d and CLAIM_LEGAL_DISPUTE_TIMING in d
    assert "relocation_volatility" in d
    assert "사건 발생 예측은 금지" in d
    assert claim_directive(SectionClaimPolicy(section_id="W-02")) == ""
