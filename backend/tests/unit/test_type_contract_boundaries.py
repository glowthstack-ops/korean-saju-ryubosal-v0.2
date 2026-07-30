"""전 패키지 mypy 게이트 고정 전에 정합화한 타입 경계 회귀 (2026-07-30).

숨어 있던 9건은 검사 범위에 따라 드러났다 — 그래서 mypy 만으로 재발을 막을 수 없고,
각 경계의 **의미**를 여기서 고정한다.

    time_parser                AgeRange 두 경계는 optional 이며 한쪽만 오는 질의가 있다
    PeriodKeyedCandidate       함수는 period·event_key 만 읽는다(계약 확대는 명시적으로)
    daily_g0_shadow            장간 유형과 관계 종류는 다른 값이다
    daily_fortune_service      베타 경로와 캐시 경로는 변수 수명이 다르다
"""

from __future__ import annotations

import datetime as dt
import inspect
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
    _BACKEND / "packages" / "manse_core",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_engines.time_parser import parse_time_with_constraints  # noqa: E402

_TODAY = dt.date(2026, 7, 30)
_BIRTH_YEAR = 1980


def _age(text: str):
    """나이 기반 TimeRange 만 꺼낸다(그 외는 None)."""
    tr, _scope, _items = parse_time_with_constraints(
        text, _TODAY, birth_year=_BIRTH_YEAR
    )
    return tr


# ── time_parser — AgeRange optional 경계 ─────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("60대 초반에 어떨까", (60, 63)),
        ("60대", (60, 69)),
        ("88세쯤 어떨까", (87, 89)),          # 근사어 → ±1
        ("70살에 어떨까", (70, 70)),          # 단일 나이
        ("환갑 무렵 어떨까", (59, 61)),        # 한자어 나이 ±1
    ],
)
def test_both_age_bounds_and_derived_years_are_concrete(
    text: str, expected: tuple[int, int]
) -> None:
    """두 경계가 다 있는 질의는 파생 연도까지 채워져야 한다."""
    tr = _age(text)
    assert tr is not None, text
    assert tr.age is not None
    assert (tr.age.from_age, tr.age.to_age) == expected
    assert tr.start == str(_BIRTH_YEAR + expected[0])
    assert tr.end == str(_BIRTH_YEAR + expected[1])


def test_derived_years_are_absent_without_birth_year() -> None:
    """생년 미상이면 나이 창은 남고 연도만 비어야 한다 — 기본값으로 덮지 않는다."""
    tr, _scope, _items = parse_time_with_constraints(
        "60대 초반", _TODAY, birth_year=None
    )
    assert tr is not None and tr.age is not None
    assert (tr.age.from_age, tr.age.to_age) == (60, 63)
    assert tr.start is None and tr.end is None


def test_one_sided_age_query_keeps_the_other_bound_open() -> None:
    """'20살 전까지' 류는 한쪽 경계만 온다 — 그래서 스키마가 optional 이다."""
    tr = _age("20살 전까지 어땠어")
    assert tr is not None and tr.age is not None
    assert tr.age.from_age is None or tr.age.to_age is None


def test_non_age_query_yields_no_age_range() -> None:
    """일반 시점 질의는 나이 창을 만들지 않는다."""
    tr = _age("내년 상반기 어때")
    assert tr is None or tr.age is None


# ── PeriodKeyedCandidate — 계약 범위 ─────────────────────────────────────


def test_both_dtos_satisfy_the_protocol_without_conversion() -> None:
    """채점 DTO 와 LLM payload DTO 가 변환 없이 두 필드를 노출한다."""
    from saju_shared_types.events import EventCandidate
    from saju_shared_types.llm_input import LlmEventCandidate

    for cls in (EventCandidate, LlmEventCandidate):
        fields = set(cls.model_fields)
        assert {"period", "event_key"} <= fields, cls.__name__


def test_finalize_reads_only_period_and_event_key_from_final_candidates() -> None:
    """계약을 조용히 넓히는 것을 막는다.

    점수·상태를 읽게 되면 Protocol 을 확장하기 전에 계약 변경으로 검토해야 한다
    (LLM payload 와 채점 DTO 는 책임이 다르다).
    """
    from saju_api.services import relationship_vector_sidecar as sidecar

    src = inspect.getsource(sidecar.finalize_relationship_envelopes)
    # `for x in final_candidates` / enumerate(final_candidates) 의 x 속성 접근 수집
    attrs = set(re.findall(r"\bx\.([a-zA-Z_][a-zA-Z0-9_]*)", src))
    assert attrs <= {"period", "event_key"}, attrs


# ── daily_g0_shadow — 장간 유형 ≠ 관계 종류 ──────────────────────────────


def test_hidden_stem_type_and_relation_kind_stay_distinct() -> None:
    """한 함수에서 같은 이름으로 재바인딩되면 어느 쪽인지 구분되지 않는다."""
    from saju_engines import daily_g0_shadow as g0

    fn = next(
        f for name, f in vars(g0).items()
        if callable(f) and getattr(f, "__module__", "") == g0.__name__
        and "relation in ADVERSE_RELATIONS" in (inspect.getsource(f)
                                                if inspect.isfunction(f) else "")
    )
    src = inspect.getsource(fn)
    assert "for relation in ADVERSE_RELATIONS" in src
    assert "for kind in ADVERSE_RELATIONS" not in src   # 옛 재바인딩 흔적
    assert "source_relation=relation" in src


def test_relation_evidence_uses_the_relation_string() -> None:
    """shadow evidence 의 source_relation 은 관계 문자열이어야 한다(enum 아님)."""
    from saju_engines.daily_g0_shadow import ADVERSE_RELATIONS

    assert all(isinstance(r, str) for r in ADVERSE_RELATIONS)
    assert ADVERSE_RELATIONS, "관계 목록이 비면 이 경로가 공허해진다"


# ── daily_fortune_service — 베타·캐시 변수 수명 ──────────────────────────


def test_beta_path_returns_before_touching_the_cache() -> None:
    """베타 경로는 즉시 반환하므로 캐시 경로와 변수를 공유하지 않는다.

    공유하면 첫 대입(비-Optional)으로 타입이 좁혀져 캐시의 `| None` 이 어긋난다.
    """
    from saju_api.services import daily_fortune_service as svc

    src = inspect.getsource(svc.get_board)
    assert "beta_board, _audit = render_beta(" in src
    assert "return beta_board" in src
    # 캐시 경로는 별도 변수로 Optional 을 그대로 받는다.
    assert "board = cache.load_board(" in src
    assert "if board is not None:" in src
    # assert 로 좁히거나 기본 보드를 새로 만들지 않는다(일운 의미 변경 금지).
    assert "assert board" not in src
