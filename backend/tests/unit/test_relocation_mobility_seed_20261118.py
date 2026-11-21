"""식상+관성 운 × 이동 동반 신호 → 이사 시드 (2026-11-18 데굴님 승인).

기준 회귀 사례 `regression_2025_08_move_not_job`(실측 2025-08 이사)를 엔진 수준에서 고정한다 —
종전에는 사례 픽스처 행만 있고 운영 엔진이 그 명식의 2025-08 에 이사 후보를 내는지는 검사하지
않았다(EMPLOYMENT_HISTORY_CALIBRATION.md §9-1b·§9-1c).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import period_v2_config
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.relocation_mobility_seed import (
    COMPANION_CLASH,
    COMPANION_HAP,
    COMPANION_YEOKMA,
    load_relocation_mobility_rule,
    mobility_companions,
    produce_relocation_mobility_seeds,
)
from saju_engines.ten_god_brancher import TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import LuckLayer, TenGod
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
#: scripts/backtest_movement_timing.py 의 골든 사례 명식(원국 지지 申·亥·亥·巳, 일간 己).
_GOLDEN = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울 구로구", gender="male",
    latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
)
_RULE_ID = "OUTPUT_AUTHORITY_RELOCATION"


def _chart(year: int = 2025):
    return calculate(_GOLDEN.model_copy(update={"reference_date": date(year, 7, 1)}))


def _pillar(ganji: str) -> LuckPillar:
    return LuckPillar(
        label="2025-08", period_type="month", ganji=ganji, stem=ganji[0], branch=ganji[1],
        stem_ten_god="", branch_ten_god="",
    )


def _signals(stem: TenGod, branch: TenGod) -> list[TransitSignal]:
    return [
        TransitSignal(ten_god=stem, layer=LuckLayer.WOLWOON, source="stem"),
        TransitSignal(ten_god=branch, layer=LuckLayer.WOLWOON, source="branch_main"),
    ]


def _relocation(cands, period: str):
    return next(
        (c for c in cands if c.period == period and str(c.event_key) == "relocation"), None,
    )


def test_flag_defaults_off_and_rule_is_loaded_from_dictionary() -> None:
    assert period_v2_config.RELOCATION_MOBILITY_SEED_ENABLED is False
    assert EventEngineV2(_DICTS)._relocation_mobility_rule is None
    rule = load_relocation_mobility_rule(_DICTS)
    assert rule is not None and rule.rule_id == _RULE_ID
    assert rule.incoming_groups == {"output", "authority"}
    assert rule.min_companions >= 1  # 십성만으로는 이사를 만들지 않는다


def test_companions_read_yeokma_activation_without_double_counting() -> None:
    chart = _chart()
    # 甲申: 甲己 천간합 + 申이 원국 역마 글자 巳(일지 亥 기준)를 육합으로 건드림.
    assert mobility_companions(_pillar("甲申"), chart) == [COMPANION_YEOKMA, COMPANION_HAP]
    # 반례: 巳申 육합 하나를 역마와 합으로 두 번 세지 않는다 — 천간합이 없으면 역마만 남는다.
    assert mobility_companions(_pillar("丙申"), chart) == [COMPANION_YEOKMA]
    # 庚寅: 寅申 충(연지) + 寅亥 육합(월지·일지). 2026-11-21 부터 12신살 기준 자리가 연지·일지라
    # 寅은 연지 申 기준 역마 글자(도래)이기도 하다 — 역마가 함께 선다.
    assert mobility_companions(_pillar("庚寅"), chart) == [
        COMPANION_YEOKMA, COMPANION_CLASH, COMPANION_HAP,
    ]
    # 반례: 甲辰 — 辰은 두 기준 어느 쪽 역마 글자도 아니고 원국 역마 글자(巳)도 건드리지 않는다.
    # 일간 己와의 천간합만 남는다.
    assert mobility_companions(_pillar("甲辰"), chart) == [COMPANION_HAP]
    # 반례: 원국과 충·합·역마가 없는 기둥.
    assert mobility_companions(_pillar("丙午"), chart) == []


def test_seed_needs_output_and_authority_on_one_pillar_plus_a_companion() -> None:
    chart, rule = _chart(), load_relocation_mobility_rule(_DICTS)
    seeds = produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.SHANGGUAN), LuckLayer.WOLWOON, _pillar("甲申"),
        chart, "2025-08", rule,
    )
    assert len(seeds) == 1 and str(seeds[0].event_key) == "relocation"
    assert seeds[0].reason_codes[0] == _RULE_ID
    assert {"RELOC_COMPANION_YEOKMA", "RELOC_COMPANION_HAP"} <= set(seeds[0].reason_codes)
    assert rule is not None and seeds[0].score == rule.base_by_companions[2]
    # 반례 1: 관성만 두 글자(식상 없음) — 만들지 않는다.
    assert produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.QISHA), LuckLayer.WOLWOON, _pillar("甲申"),
        chart, "2025-08", rule,
    ) == []
    # 반례 2: 식상+관성이어도 이동 동반 신호가 없으면 만들지 않는다.
    assert produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.SHANGGUAN), LuckLayer.WOLWOON, _pillar("丙午"),
        chart, "2025-08", rule,
    ) == []
    # 반례 3: 규칙의 층이 아닌 층(일운)·규칙 없음.
    assert produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.SHANGGUAN), LuckLayer.ILWOON, _pillar("甲申"),
        chart, "2025-08", rule,
    ) == []
    assert produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.SHANGGUAN), LuckLayer.WOLWOON, _pillar("甲申"),
        chart, "2025-08", None,
    ) == []
    # 반례 4: 필수 동반 신호를 충으로 두면 역마+합만으로는 만들지 않는다(사전 값이 판정을 정한다).
    strict = dataclasses.replace(rule, required_companions=frozenset({COMPANION_CLASH}))
    assert produce_relocation_mobility_seeds(
        _signals(TenGod.ZHENGGUAN, TenGod.SHANGGUAN), LuckLayer.WOLWOON, _pillar("甲申"),
        chart, "2025-08", strict,
    ) == []


def test_golden_case_2025_08_gets_relocation_candidate_only_when_enabled() -> None:
    """실측 2025-08 이사 — 켜면 그 달에 이사 후보가 서고, 끄면 종전대로 없다."""
    chart = _chart()
    off = EventEngineV2(_DICTS).score(chart, levels={GanjiLevel.MONTH})
    on = EventEngineV2(_DICTS, enable_relocation_mobility_seed=True).score(
        chart, levels={GanjiLevel.MONTH},
    )
    assert _relocation(off, "2025-08") is None
    seeded = _relocation(on, "2025-08")
    assert seeded is not None and _RULE_ID in seeded.reason_codes
    assert seeded.score >= 75  # 서술 강도 '강' 띠
    # 반례: 식상+관성 기둥이 아닌 달은 켜도 끈 것과 같다(다른 사건 후보의 점수도 그대로).
    other = {(c.period, str(c.event_key)): c.score for c in off if c.period == "2025-05"}
    assert other == {(c.period, str(c.event_key)): c.score for c in on if c.period == "2025-05"}
