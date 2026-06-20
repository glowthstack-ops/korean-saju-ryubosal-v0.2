"""프로필 → user_profile_event_gate 상태 문자열 파생 검증.

공직(O02)·학생(O17)·무직(O18)은 category_id가 employment_form보다 우선함을 확인한다.
"""

from __future__ import annotations

from saju_engines.profile_engine import (
    derive_occupation_status,
    derive_relationship_status,
)


def test_public_official_overrides_employment_form() -> None:
    # 공무원 정규직 → employee가 아니라 public_official(구조적 분류 우선).
    assert derive_occupation_status("정규직", "O02") == "public_official"


def test_student_and_unemployed_by_category() -> None:
    assert derive_occupation_status(None, "O17") == "student"
    assert derive_occupation_status(None, "O18") == "unemployed"


def test_employment_form_when_no_structural_category() -> None:
    assert derive_occupation_status("정규직", "O01") == "employee"
    assert derive_occupation_status("프리랜서", "O09") == "freelancer"
    assert derive_occupation_status("자영업", "O15") == "business_owner"
    assert derive_occupation_status("법인대표", "O03") == "business_owner"


def test_unknown_returns_none() -> None:
    # 어디에도 안 걸리면 None(게이트 미적용 — 규칙11).
    assert derive_occupation_status(None, None) is None
    assert derive_occupation_status(None, "O01") is None


def test_relationship_status_map() -> None:
    assert derive_relationship_status("기혼") == "married"
    assert derive_relationship_status("재혼") == "married"
    assert derive_relationship_status("미혼") == "single"
    assert derive_relationship_status("사별") == "single"
    assert derive_relationship_status("연애중") == "dating"
    assert derive_relationship_status("이혼") == "divorced"
    assert derive_relationship_status(None) is None
