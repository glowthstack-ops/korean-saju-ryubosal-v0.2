"""두 명식 궁합 엔진 검증 (관계운 상대 모드).

확정 신호 세트(일주 상호작용·십성 관계·용신 상호보완)가 엔진 계산값으로 산출되는지,
방향(보완/마찰)이 일관되게 카운트되는지 확인한다. reviewed:false 가중은 비교 대상 아님.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.compatibility_engine import (
    _day_branch_signal,
    _is_punishment,
    analyze_compatibility,
    compatibility_lines,
)
from saju_engines.context_reducer import build_birth_summary
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind
from saju_shared_types.enums import Branch


def test_day_branch_six_combine_is_harmony() -> None:
    sig = _day_branch_signal(Branch.HAE, Branch.IN)  # 亥寅 육합
    assert sig is not None
    assert sig.kind is CompatSignalKind.DAY_BRANCH_SIX
    assert sig.direction is CompatDirection.HARMONY


def test_day_branch_clash_is_friction() -> None:
    sig = _day_branch_signal(Branch.SA, Branch.HAE)  # 巳亥 충
    assert sig is not None
    assert sig.kind is CompatSignalKind.DAY_BRANCH_CLASH
    assert sig.direction is CompatDirection.FRICTION


def test_day_branch_punishment_and_duplicate() -> None:
    # 子卯 무례지형.
    assert _is_punishment(Branch.JA, Branch.MYO)
    # 같은 일지 + 자형 글자(辰) → 복음이되 마찰.
    dup = _day_branch_signal(Branch.JIN, Branch.JIN)
    assert dup is not None
    assert dup.kind is CompatSignalKind.DAY_BRANCH_DUPLICATE
    assert dup.direction is CompatDirection.FRICTION


def test_day_branch_no_relation_returns_none() -> None:
    assert _day_branch_signal(Branch.HAE, Branch.CHUK) is None  # 亥丑 무관계


def _chart(y: int, m: int, d: int, hm: str, gender: str):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name="서울", gender=gender,
    ))


def test_analyze_compatibility_full_signals() -> None:
    a = _chart(1980, 11, 22, "09:08", "male")    # 己亥 일주
    b = _chart(1985, 3, 15, "14:30", "female")   # 癸丑 일주
    sa, sb = build_birth_summary(a), build_birth_summary(b)
    rep = analyze_compatibility(a, b, sa.useful_gods, sb.useful_gods)
    assert rep is not None
    # 십성 관계 신호는 양방향 항상 2개.
    tg_kinds = {s.kind for s in rep.signals}
    assert CompatSignalKind.TEN_GOD_TO_PARTNER in tg_kinds
    assert CompatSignalKind.TEN_GOD_TO_SELF in tg_kinds
    # 카운트는 신호 방향과 일치.
    assert rep.harmony_count == sum(
        1 for s in rep.signals if s.direction is CompatDirection.HARMONY
    )
    assert rep.friction_count == sum(
        1 for s in rep.signals if s.direction is CompatDirection.FRICTION
    )
    assert rep.summary  # 전반 톤 비어있지 않음
    assert rep.self_day and rep.partner_day
    # 직렬화 블록에 방향 태그가 박힌다.
    block = "\n".join(compatibility_lines(rep))
    assert "[궁합 신호" in block and "보완" in block
