"""OA-10a — `display-selection.legacy-v0` 표시 정책 adapter.

**"현재 코드에서 C10 만 끈 상태"가 아니다.** 그렇게 정의하면 이후 코드가 변할 때
legacy 도 함께 변해 과거 재현이 무너진다. 여기서는 독립된 순수 계약으로 고정한다.

    history 참조 없음
    display_good_representative = raw_good_winner
    display_displacement_loss   = 0
    good_selection_reason       = RAW_GOOD_WINNER_SELECTED
    support·caution 은 그 날짜의 슬롯 계약으로 재선발
    final headline 은 그 날짜의 board rebalance 계약까지 적용

날짜별 차이는 이 모듈이 분기하지 않는다 — `daily_contract_resolver` 가 해소한
계약을 받아 쓴다. feature flag 기본값이나 taxonomy 변경으로 결과가 달라지지 않는다
(taxonomy 는 여기서 참조하지 않으며, `semantic_family` 주석은 원장 기록 단계에서
`taxonomy_version` 과 함께 붙인다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from saju_engines.daily_contract_resolver import DayContracts, resolve_day_contracts
from saju_engines.daily_ilju_fortune import (
    _DOMAIN_HEADLINE_CAP,
    EVENT_SELECTION_COMPAT_SALT,
    _band,
    _headline_candidates,
    _lucky_place,
    _rebalance_headlines,
    _score_event,
    _select_slots,
    load_daily_dicts_for,
)
from saju_engines.daily_selection_contracts import (
    DISPLAY_SELECTION_POLICY_LEGACY_V0,
)
from saju_engines.daily_selection_policy_shadow import strength_band
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

#: legacy 정책의 유일한 선택 사유.
RAW_GOOD_WINNER_SELECTED = "RAW_GOOD_WINNER_SELECTED"

_BAND_NAMES = {4: "s5", 3: "s4", 2: "s3", 1: "s2"}


@dataclass(frozen=True)
class LegacyDisplayRow:
    """legacy-v0 가 산출한 일주 1개의 표시 결정.

    `semantic_family` 는 담지 않는다 — taxonomy 는 legacy 계약의 입력이 아니다.
    원장 기록 단계에서 `taxonomy_version` 과 함께 주석한다.
    """

    ilju: str
    raw_good_winner: str
    raw_good_probability: int
    raw_good_band: str
    display_good_representative: str
    display_good_probability: int
    display_good_band: str
    support_event: str
    caution_event: str
    raw_headline: str
    final_headline: str
    final_headline_probability: int
    band: str
    place_key: str
    good_selection_reason: str
    display_displacement_loss: int
    raw_supporting_groups: int
    display_supporting_groups: int


def build_legacy_board(
    target_date: date, *, strict: bool = True
) -> tuple[DayContracts, list[LegacyDisplayRow]]:
    """그 날짜의 legacy-v0 보드를 산출한다.

    Args:
        target_date: 대상 날짜.
        strict: 정확 재현이 불가능하면 예외(기본). 감사용으로만 False 를 쓴다.

    Returns:
        (해소된 계약, 일주 60건). 60갑자 순서로 정렬돼 있다.

    Raises:
        ContractResolutionError: `strict` 이고 그 날짜를 정확히 재현할 수 없을 때.
    """
    contracts = resolve_day_contracts(target_date, strict=strict)
    dicts = load_daily_dicts_for(target_date)
    events = dicts.catalog["events"]
    from saju_engines.daily_ilju_fortune import build_day_context

    ctx = build_day_context(target_date)

    slot_rows: dict[str, tuple] = {}
    candidates: dict[str, list] = {}
    order: list[str] = []
    scored_by: dict[str, dict] = {}
    seeds: dict[str, str] = {}

    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ilju = f"{stem.value}{branch.value}"
        seed = f"{target_date.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        seeds[ilju] = seed
        scored = [_score_event(k, e, stem, branch, ctx) for k, e in events.items()]
        scored_by[ilju] = {s.event_key: s for s in scored}
        # legacy 는 good_override 를 쓰지 않는다 — 원시 1위가 곧 표시 대표다.
        good, caution, support = _select_slots(scored, seed)
        band = _band(good, caution)
        slot_rows[ilju] = (good, caution, support, band)
        candidates[ilju] = _headline_candidates(good, support, caution, band)
        order.append(ilju)

    headline_pick, _reasons, _unres = _rebalance_headlines(
        candidates, order, _DOMAIN_HEADLINE_CAP
    )

    rows: list[LegacyDisplayRow] = []
    for ilju in order:
        good, caution, support, band = slot_rows[ilju]
        final = headline_pick[ilju]
        place = _lucky_place(dicts, final.domain, seeds[ilju], 0)
        rows.append(LegacyDisplayRow(
            ilju=ilju,
            raw_good_winner=good.event_key,
            raw_good_probability=good.probability,
            raw_good_band=_BAND_NAMES[strength_band(good.probability)],
            display_good_representative=good.event_key,
            display_good_probability=good.probability,
            display_good_band=_BAND_NAMES[strength_band(good.probability)],
            support_event=support.event_key,
            caution_event=caution.event_key,
            raw_headline=candidates[ilju][0].event_key,
            final_headline=final.event_key,
            final_headline_probability=final.probability,
            band=band,
            place_key=place.place_key,
            good_selection_reason=RAW_GOOD_WINNER_SELECTED,
            display_displacement_loss=0,
            raw_supporting_groups=good.supporting_groups,
            display_supporting_groups=good.supporting_groups,
        ))
    return contracts, rows


def legacy_policy_version() -> str:
    """이 adapter 가 구현하는 표시 정책 버전."""
    return DISPLAY_SELECTION_POLICY_LEGACY_V0
