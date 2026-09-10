"""3층 판정 모델(v2) 단위 테스트 — docs/17 §22 계약 검증."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from saju_engines import daily_ilju_fortune as v1
from saju_engines.daily_fortune_v2 import (
    EXCLUDED_FROM_V1,
    day_channels,
    load_catalog_v2,
    score_event_v2,
    select_slots_v2,
    signature_satisfied,
    unsatisfiable_signatures,
    validate_against_v1,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_shared_types.daily_fortune_v2 import DailyEventModelV2
from saju_shared_types.enums import Branch, Stem

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"


def _catalog():
    return load_catalog_v2(str(_DICTS / "daily_event_catalog_v2.json"))


def test_catalog_has_64_events_and_approved_overrides() -> None:
    """§22-3·§22-7: 64종(48 + 2026-09-10 확장 16), weather 제외, family_talk 이중 슬롯."""
    catalog = _catalog()
    assert len(catalog.events) == 64
    assert EXCLUDED_FROM_V1.isdisjoint(catalog.events)
    assert catalog.events["family_talk"].slots == ["support", "good"]
    # 구조 검증 통과 ≠ 명리 감수 — 감수 전 상태가 위조되면 안 된다.
    assert catalog.reviewed is False


def test_catalog_matches_v1_identity() -> None:
    """key/label/domain/valence 는 v1 과 갈라질 수 없다."""
    v1_catalog = json.loads(
        (_DICTS / "daily_event_catalog.json").read_text(encoding="utf-8")
    )
    assert validate_against_v1(_catalog(), v1_catalog) == []


def test_v2_schema_forbids_v1_scoring_fields() -> None:
    """v2 는 채점 전용 스키마 — expr_confidence 등 v1 필드 유입은 즉시 실패(§22-1)."""
    base = {
        "label": "x", "domain": "money", "valence": "good", "slots": ["good"],
        "prior": "상", "required_signature": None, "evidence": {"편재": 0.5},
    }
    DailyEventModelV2.model_validate(base)
    with pytest.raises(ValidationError):
        DailyEventModelV2.model_validate({**base, "expr_confidence": 0.9})


def test_comm_exclusive_triggers() -> None:
    """소통 4종 배타 규칙(§22-3): 해+상관만 있는 날 — 구설 성립, 말다툼 불성립."""
    catalog = _catalog()
    ch = {"hae": 1.0, "상관": 1.0}
    assert signature_satisfied(ch, catalog.events["rumor_caution"].required_signature)
    assert not signature_satisfied(
        ch, catalog.events["argument_caution"].required_signature
    )
    # 충이 생기면 말다툼이 성립한다.
    assert signature_satisfied(
        {**ch, "chung": 1.0}, catalog.events["argument_caution"].required_signature
    )


def test_signature_surface_threshold_blocks_weak_hidden_stems() -> None:
    """표면성 규칙(§22-2): 중기·여기(0.3) 단독으로는 십성 리프가 성립하지 않는다."""
    assert not signature_satisfied({"편인": 0.3}, "편인")
    assert signature_satisfied({"편인": 0.7}, "편인")
    # 그룹 별칭은 구성원 최댓값으로 판정한다.
    assert signature_satisfied({"겁재": 1.0}, "비겁")
    assert not signature_satisfied({"겁재": 0.3}, "비겁")


def test_gongmang_channel_rules() -> None:
    """공망일 채널: 공망지 아닌 날 0 / 충발 1.0 유지 / 육합 0.4 감쇄(合則不能空)."""
    ctx_base = v1.build_day_context(dt.date(2026, 8, 24))

    def _ch(ilju_stem: str, ilju_branch: str, day_stem: str, day_branch: str) -> dict:
        ctx = ctx_base.model_copy(
            update={"day_stem": day_stem, "day_branch": day_branch}
        )
        return day_channels(Stem(ilju_stem), Branch(ilju_branch), ctx)

    # 甲子일주 공망 = 戌亥: 戌일은 공망일, 午일은 아니다.
    assert Branch("戌") in gongmang_branches(Stem("甲"), Branch("子"))
    assert _ch("甲", "子", "甲", "戌")["gongmang"] == 1.0
    assert _ch("甲", "子", "甲", "午")["gongmang"] == 0.0
    # 己亥일주 공망 = 辰巳: 巳일은 巳亥 충 동반 — 충발은 감쇄 없이 1.0(§22-2).
    assert _ch("己", "亥", "己", "巳")["gongmang"] == 1.0
    assert _ch("己", "亥", "己", "巳")["chung"] == 1.0
    # 육합 감쇄(0.4) 사례가 60일주 × 공망지 안에 실제로 존재해야 규칙이 산다.
    damped = []
    for i in range(60):
        stem, branch = ganzi_from_index(i)
        for void in gongmang_branches(stem, branch):
            ch = _ch(str(stem), str(branch), "甲", str(void))
            if ch["gongmang"] == 0.4:
                damped.append((str(stem) + str(branch), str(void)))
    assert damped, "육합 감쇄 사례 부재 — 감쇄 규칙이 죽은 코드"


def test_ineligible_event_never_beats_eligible_pool() -> None:
    """게이트 미성립 후보는 감점(0.3배)돼 폴백 밖에서는 선발되지 않는다."""
    catalog = _catalog()
    ctx = v1.build_day_context(dt.date(2026, 8, 24))
    for i in range(60):
        stem, branch = ganzi_from_index(i)
        ch = day_channels(stem, branch, ctx)
        sel = select_slots_v2(catalog, ch, f"2026-08-24|{stem.value}{branch.value}|t")
        if sel.fallback_used:
            continue
        for scored in (sel.good, sel.caution, sel.support):
            assert scored.event_key in sel.eligible_keys


def test_fallback_fills_caution_when_all_gated() -> None:
    """전 caution 게이트 미성립(빈 채널)에서도 카드 3슬롯 계약이 유지된다(§22-1)."""
    catalog = _catalog()
    sel = select_slots_v2(catalog, {}, "seed|fallback")
    assert sel.fallback_used is True
    assert sel.caution.valence == "caution"
    assert sel.good.valence == "good"


def test_all_signatures_satisfiable_within_a_year() -> None:
    """§22-4: eligible=0 signature 는 결함 — 고정 연도 전수에서 전부 성립해야 한다."""
    assert unsatisfiable_signatures(_catalog()) == []


def test_flag_default_off_and_cache_namespace_split() -> None:
    """플래그는 pytest 환경에서 OFF(v1 바이트 불변)이고, v2 캐시 키는 v1 과 갈라진다."""
    import saju_engines.daily_fortune_v2 as dfv2
    from saju_shared_types.daily_fortune import content_version_for

    d = dt.date(2026, 8, 24)
    assert dfv2.DAILY_FORTUNE_MODEL_V2_ENABLED is False
    assert dfv2.active_content_version(d) == content_version_for(d)
    v2_version = dfv2.content_version_v2_for(d)
    assert v2_version != content_version_for(d)
    # 모델 버전은 날짜가 고른다(§22-7 경계) — 8/24 는 확장 이전이라 model.v2.0 이다.
    from saju_shared_types.daily_fortune_v2 import active_model_v2_version

    assert v2_version.endswith(active_model_v2_version(d))
    assert active_model_v2_version(d) != dfv2.MODEL_V2_VERSION


def test_compute_board_v2_reuses_v1_pipeline_with_v2_pool() -> None:
    """v2 보드: 60일주·검증 스키마 통과, 노출 사건은 전부 v2 카탈로그(48종) 소속."""
    from saju_engines.daily_fortune_v2 import compute_board_v2, load_catalog_v2

    d = dt.date(2026, 8, 24)
    catalog = load_catalog_v2()
    board = compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
    assert len(board.fortunes) == 60
    assert board.content_version.endswith("model.v2.0")
    for fortune in board.fortunes:
        for event in fortune.events:
            assert event.event_key in catalog.events  # weather 등 제외 사건 불노출
        assert fortune.headline_event_key in catalog.events


def test_service_generate_uses_v1_when_flag_off(monkeypatch) -> None:
    """플래그 OFF 면 서비스 생성 경로가 v2 를 호출하지 않는다(라이브 불변 담보)."""
    from saju_api.services import daily_fortune_service as svc

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("플래그 OFF 에서 compute_board_v2 호출")

    monkeypatch.setattr(svc, "compute_board_v2", _boom)
    board = svc._generate(dt.date(2026, 8, 24))
    assert len(board.fortunes) == 60
    assert "model.v2.0" not in board.content_version


def test_scoring_ignores_expr_confidence_field_entirely() -> None:
    """ec 는 v2 evidence 경로에 존재하지 않는다 — 같은 입력이면 같은 activation."""
    catalog = _catalog()
    ch = {"편재": 1.0, "saeng_a": 0.6}
    result = score_event_v2("money_small_gain", catalog.events["money_small_gain"], ch)
    assert result.eligible
    again = score_event_v2("money_small_gain", catalog.events["money_small_gain"], ch)
    assert result.scored.activation == again.scored.activation
    assert 5 <= result.scored.probability <= 95


# ── §22-8 잔여 12운성 채널(2026-09-10 4차) — 정의·가산·inert ─────────────────────


def test_residual_stage_channels_follow_stage_definition() -> None:
    """목욕=흔들림 / 관대=단장·의욕 / 쇠=노련 / 태 1.0·양 0.8=구상·양육. 기존 7채널 값은 불변."""
    from saju_engines.daily_fortune_v2 import _STAGE_CHANNEL_VALUES, day_channels
    from saju_shared_types.daily_fortune import DayGanjiContext
    from saju_shared_types.daily_fortune_v2 import RESIDUAL_STAGE_CHANNELS

    expected = {
        "MOKYOK": ("unsettled", 1.0), "GWANDAE": ("poised", 1.0), "SOE": ("seasoned", 1.0),
        "TAE": ("incubation", 1.0), "YANG": ("incubation", 0.8),
    }
    for stage, (name, value) in expected.items():
        assert _STAGE_CHANNEL_VALUES[stage][name] == value
    # 기존 7채널 값은 가산 전과 같다(목욕 재생 .6, 관대 활동↑ .7, 쇠 체력↓ .6, 태·양 재생 .5).
    assert _STAGE_CHANNEL_VALUES["MOKYOK"]["renewal"] == 0.6
    assert _STAGE_CHANNEL_VALUES["GWANDAE"]["activity_up"] == 0.7
    assert _STAGE_CHANNEL_VALUES["SOE"]["stamina_down"] == 0.6
    assert _STAGE_CHANNEL_VALUES["TAE"]["renewal"] == 0.5
    assert _STAGE_CHANNEL_VALUES["YANG"]["renewal"] == 0.5
    # day_channels 에 4채널이 항상 실린다. 甲 천간은 子 에서 목욕 → unsettled 1.0.
    ctx = DayGanjiContext(
        the_date=dt.date(2026, 9, 12), day_stem="甲", day_branch="子",
        month_stem="丁", month_branch="酉", year_stem="丙", year_branch="午",
    )
    ch = day_channels(Stem("乙"), Branch("子"), ctx)
    assert all(name in ch for name in RESIDUAL_STAGE_CHANNELS)
    assert ch["unsettled"] == 1.0 and ch["renewal"] == 0.6


def test_residual_stage_channels_are_inert_until_wired() -> None:
    """사전이 잔여 채널을 참조하지 않는 동안(§22-8 배선 승인 전) 선발·점수는 바이트 불변."""
    from saju_engines import daily_fortune_v2 as V2
    from saju_engines.daily_fortune_v2 import compute_board_v2
    from saju_shared_types.daily_fortune_v2 import RESIDUAL_STAGE_CHANNELS

    catalog = load_catalog_v2()
    for key, ev in catalog.events.items():
        assert not set(ev.evidence) & set(RESIDUAL_STAGE_CHANNELS), key
        assert not set(json.dumps(ev.required_signature, ensure_ascii=False).split('"')) & set(
            RESIDUAL_STAGE_CHANNELS
        ), key
    d = dt.date(2026, 9, 12)
    with_channels = compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
    stripped = {
        stage: {k: w for k, w in values.items() if k not in RESIDUAL_STAGE_CHANNELS}
        for stage, values in V2._STAGE_CHANNEL_VALUES.items()
    }
    original = V2._STAGE_CHANNEL_VALUES
    V2._STAGE_CHANNEL_VALUES = stripped
    try:
        without = compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
    finally:
        V2._STAGE_CHANNEL_VALUES = original
    assert with_channels.model_dump() == without.model_dump()

