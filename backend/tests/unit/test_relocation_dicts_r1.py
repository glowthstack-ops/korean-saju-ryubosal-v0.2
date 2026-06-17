"""Phase R1 — 이사 고도화 사전(십성 분류 + 계약일/이삿날 점수표) 검증.

신설 사전 두 개가 스키마 검증·충돌 검사를 통과하고, 사용자 스펙(2026-06-17)의
구조·커버리지·가중·충 이중성을 보존하는지 확인한다. 명리 매핑 값은 reviewed:false
초안이므로 여기서는 구조·범위·일관성만 검증한다(점수 자체의 타당성은 검수 단계).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines.dictionaries import (
    DateSelectionTenGodsFile,
    RelocationTenGodsFile,
    lint_dictionaries,
    validate_dictionaries,
)

_DICT_DIR = Path(__file__).resolve().parents[2] / "dictionaries"
_TEN_GODS = {"비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인"}


def _load(rel: str) -> dict:
    """사전 JSON 파일 로드."""
    return json.loads((_DICT_DIR / rel).read_text(encoding="utf-8"))


def test_real_dictionaries_still_validate_and_lint_clean() -> None:
    """신설 사전 추가 후에도 사전 전체가 스키마 검증·충돌 검사를 통과한다."""
    assert validate_dictionaries(_DICT_DIR) == []
    assert lint_dictionaries(_DICT_DIR) == []


def test_relocation_ten_gods_covers_all_ten() -> None:
    """relocation_ten_gods.json이 십성 10종을 정확히 커버한다."""
    file = RelocationTenGodsFile.model_validate(_load("interpretations/relocation_ten_gods.json"))
    assert {item.ten_god for item in file.items} == _TEN_GODS
    for item in file.items:
        # 분류 라벨 전용 — 점수·날짜 필드가 섞이지 않는다(절대원칙 1·12).
        assert item.move_reason and item.property_tendency and item.required_checks
        assert item.risk_level in ("low", "medium_low", "medium", "high")


def test_date_selection_weights_sum_to_one() -> None:
    """계약일·이삿날 작업별 가중 합이 1.0(천간/지지/오행 배분, 사용자 스펙 11장)."""
    file = DateSelectionTenGodsFile.model_validate(
        _load("calendar/date_selection_ten_gods.json")
    )
    assert round(sum(file.contract_day.weights.values()), 6) == 1.0
    assert round(sum(file.move_day.weights.values()), 6) == 1.0
    # 계약일은 천간 십성 비중이 가장 큼, 이삿날은 지지 관계 비중이 가장 큼(11장).
    assert file.contract_day.weights["dayStemTenGod"] == max(file.contract_day.weights.values())
    assert file.move_day.weights["dayBranchRelation"] == max(file.move_day.weights.values())


def test_chung_duality_preserved() -> None:
    """충 이중성(10장): 탐지=긍정, 택일=감점. 이삿날 충 관계는 모두 감점."""
    file = DateSelectionTenGodsFile.model_validate(
        _load("calendar/date_selection_ten_gods.json")
    )
    assert file.chung_policy.event_detection == "positive_for_relocation_trigger"
    assert file.chung_policy.date_selection == "negative_for_move_day"
    for rel, val in file.move_day.branch_relations.items():
        if "충" in rel:
            assert val < 0, f"{rel} 충 관계가 감점이 아님"


def test_preferred_ten_gods_match_spec() -> None:
    """계약일=정관·정인, 이삿날=정재·정관 우선(사용자 스펙 9·10장)."""
    file = DateSelectionTenGodsFile.model_validate(
        _load("calendar/date_selection_ten_gods.json")
    )
    assert set(file.contract_day.preferred_ten_gods) == {"정관", "정인"}
    assert set(file.move_day.preferred_ten_gods) == {"정재", "정관"}
