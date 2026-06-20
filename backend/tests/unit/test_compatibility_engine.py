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
    _sinsal_cross_signals,
    analyze_compatibility,
    compatibility_lines,
)
from saju_engines.context_reducer import build_birth_summary
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind
from saju_shared_types.enums import Branch, Stem


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


def test_sinsal_cross_is_auxiliary_neutral() -> None:
    # 子酉 귀문 + 子 도화(사정지) → 보조 신호(NEUTRAL·auxiliary), 마찰/보완 방향 아님.
    sigs = _sinsal_cross_signals(Stem.GAP, Stem.GAP, Branch.JA, Branch.YU)
    assert sigs, "신살 교차 신호가 나와야 한다"
    assert all(s.auxiliary and s.direction is CompatDirection.NEUTRAL for s in sigs)
    kinds = {s.kind for s in sigs}
    assert CompatSignalKind.SINSAL_FRICTION in kinds  # 귀문
    assert CompatSignalKind.SINSAL_CHARM in kinds  # 도화


def test_sinsal_cross_excluded_from_counts() -> None:
    a = _chart(1980, 11, 22, "09:08", "male")
    b = _chart(1988, 9, 9, "12:00", "female")
    sa, sb = build_birth_summary(a), build_birth_summary(b)
    rep = analyze_compatibility(a, b, sa.useful_gods, sb.useful_gods)
    assert rep is not None
    # 보조(신살) 신호는 보완/마찰 카운트에서 제외된다.
    aux = [s for s in rep.signals if s.auxiliary]
    if aux:
        non_aux_harm = sum(
            1 for s in rep.signals
            if s.direction is CompatDirection.HARMONY and not s.auxiliary
        )
        assert rep.harmony_count == non_aux_harm
        # 직렬화 블록에 '참고 — 보조 신살' 섹션이 분리되어 나온다.
        block = "\n".join(compatibility_lines(rep))
        assert "참고 — 보조 신살" in block


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


# E1 끌림(자극) 채널 — 안정(보완/마찰)과 분리(궁합 자료 ②: 충·살이 많아도 확 끌림).
def test_attraction_band_thresholds() -> None:
    from saju_engines.compatibility_engine import _attraction_band
    assert _attraction_band(4) == "강"
    assert _attraction_band(2) == "중"
    assert _attraction_band(1) == "약"


def test_attraction_line_separates_spark_from_stability() -> None:
    from saju_engines.compatibility_engine import _attraction_line
    # 끌림 강 + 안정 약 → '확 끌림'을 좋은 궁합으로 단정하지 말라는 분리 프레이밍.
    msg = _attraction_line("강", harmony=0, friction=2)
    assert "단정" in msg


def test_report_populates_attraction() -> None:
    self_c = _chart(1990, 3, 3, "08:00", "male")
    partner_c = _chart(1992, 7, 7, "20:00", "female")
    rep = analyze_compatibility(
        self_c, partner_c,
        build_birth_summary(self_c).useful_gods,
        build_birth_summary(partner_c).useful_gods,
    )
    assert rep is not None
    assert rep.attraction_band in ("강", "중", "약")
    # 직렬화 라인에 '끌림(자극)' 채널이 노출된다(LLM이 안정과 분리해 서술).
    assert any("끌림(자극)" in ln for ln in compatibility_lines(rep))
