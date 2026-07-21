"""대운 발현 진행 모드 resolver 테스트 — 모드 판정 fixture + 점수 불변 + 문구 회귀.

하드 "전반 0-4년/후반 5-9년" 분할 폐기(2026-07-21) 회귀 가드: 판정표(GPT §10 채택)의
각 모드가 기존 신호 조합에서 재현되고, resolver가 입력을 절대 변경하지 않으며,
디렉티브·렌더 문구에 하드 분할 표현이 재유입되지 않음을 고정한다.
"""

from __future__ import annotations

from datetime import date
from typing import get_args

from saju_api.services.manse_service import calculate
from saju_engines.daewoon_progression import (
    resolve_all_daewoon_progressions,
    resolve_daewoon_progression,
)
from saju_engines.structural_context import (
    DAEWOON_FRAMING_DIRECTIVE,
    PROGRESSION_MODE_KO,
    daewoon_progression_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.daewoon_progression import ProgressionMode
from saju_shared_types.luck import DaewoonItem, LuckPolarity
from saju_shared_types.pillars import FourPillarsResult, Pillar


def _pillar(stem: str, branch: str) -> Pillar:
    return Pillar(
        stem=stem, branch=branch, ganji=f"{stem}{branch}",
        stem_element="", branch_element="", stem_yinyang="", branch_yinyang="",
        stem_ten_god="", branch_main_ten_god="", twelve_unseong="", hidden_stems=[],
    )


def _natal(
    year: tuple[str, str], month: tuple[str, str], day: tuple[str, str],
) -> FourPillarsResult:
    return FourPillarsResult(
        year=_pillar(*year), month=_pillar(*month), day=_pillar(*day),
        day_master=day[0],
    )


# 기본 원국: 년 甲子 · 월 丙寅 · 일 戊午 (일지=午, 월지=寅).
_PILLARS = _natal(("甲", "子"), ("丙", "寅"), ("戊", "午"))


def _daewoon(
    stem: str,
    branch: str,
    *,
    relations: list[str] | None = None,
    gongmang: list[str] | None = None,
    void: bool = False,
    stem_tg: str = "정재",
    branch_tg: str = "편인",
) -> DaewoonItem:
    return DaewoonItem(
        index=0, start_age=5,
        approx_start_date=date(2000, 1, 1), approx_end_date=date(2010, 1, 1),
        ganji=f"{stem}{branch}", stem=stem, branch=branch,
        stem_ten_god=stem_tg, branch_ten_god=branch_tg, twelve_unseong="",
        relations_to_chart=relations or [],
        gongmang_activation=gongmang or [],
        branch_effect=LuckPolarity(element="", type="한신", score=0.0, is_void=void),
    )


# ── 모드 판정 fixture (판정표) ──────────────────────────────────────────────


def test_no_exception_yields_default_gradient() -> None:
    # 癸巳: 운지지(巳)에 水 뿌리 없음(지속 아님)·원국 子에 통근(무근 아님)·관계 없음.
    item = _daewoon("癸", "巳")
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "default_gradient"
    assert "STEM_ROOTED_IN_NATAL" in prof.reason_codes


def test_day_palace_clash_yields_branch_early_activation() -> None:
    # 丙子 대운: 운지지 子가 원국 일지 午를 충 — 초입부터 현실 변동 가능.
    item = _daewoon("丙", "子", relations=["충:子-午"])
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "branch_early_activation"
    assert "BRANCH_CLASH_DAY_PALACE" in prof.reason_codes


def test_samhap_complete_with_rooted_stem_yields_coactivated() -> None:
    # 壬申 대운: 삼합완성(지지 조기 발동) + 壬이 申 중기에 통근(천간 작동) → 동시 발현.
    item = _daewoon("壬", "申", relations=["삼합완성:水"])
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "coactivated"
    assert "SAMHAP_COMPLETE" in prof.reason_codes
    assert "STEM_ROOTED_IN_LUCK_BRANCH" in prof.reason_codes


def test_ganyeojidong_yields_coactivated() -> None:
    # 甲寅 대운: 천간·지지 본기 십성 동일(간여지동) → 표출·현실 기반 동시 활성.
    item = _daewoon("甲", "寅", stem_tg="비견", branch_tg="비견")
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "coactivated"
    assert "GANYEOJIDONG" in prof.reason_codes


def test_rootless_combined_void_yields_weak_manifestation() -> None:
    # 丁酉 대운 vs 원국 壬子·辛亥·庚申: 丁 무근(火 뿌리 전무)+丁壬 합거+지지 공망 전실.
    natal = _natal(("壬", "子"), ("辛", "亥"), ("庚", "申"))
    item = _daewoon(
        "丁", "酉", relations=["천간합:丁-壬"], gongmang=["공망전실:酉"], void=True,
    )
    prof = resolve_daewoon_progression(item, natal)
    assert prof.mode == "weak_manifestation"
    assert "STEM_NO_ROOT" in prof.reason_codes
    assert "STEM_COMBINED_AWAY" in prof.reason_codes


def test_luck_branch_rooted_uncombined_yields_stem_persistent() -> None:
    # 壬申 대운(관계 없음): 壬이 申 중기 통근·천간합 없음 → 외부 주제 전 기간 지속형.
    item = _daewoon("壬", "申")
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "stem_persistent"
    assert "STEM_ROOTED_IN_LUCK_BRANCH" in prof.reason_codes


def test_void_with_harmony_complete_yields_indeterminate() -> None:
    # 癸丑 대운: 공망 전실(저하)과 방합완성(발동)이 동시 — 단정 불가.
    item = _daewoon(
        "癸", "丑", relations=["방합완성:水"], gongmang=["공망전실:丑"], void=True,
    )
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "indeterminate"


def test_void_activated_by_clash_yields_early_not_weak() -> None:
    # 공망이라도 충으로 발동하면 저하가 아니라 조기 사건화(luck_cycles 동태와 동일 방향).
    item = _daewoon(
        "丙", "子", relations=["충:子-午"], gongmang=["공망발동(충):子-午"], void=True,
    )
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert prof.mode == "branch_early_activation"
    assert "VOID_ACTIVATED_BY_CLASH" in prof.reason_codes


# ── 불변식: 입력 불변(점수·판정 무개입) ─────────────────────────────────────


def test_resolver_never_mutates_input() -> None:
    item = _daewoon("壬", "申", relations=["삼합완성:水", "충:申-寅"])
    before = item.model_dump()
    prof = resolve_daewoon_progression(item, _PILLARS)
    assert item.model_dump() == before
    assert prof.usage == "narrative_only"


def test_real_chart_end_to_end_inert() -> None:
    # 실계산 명식에서 전 대운 판정이 유효 모드이고 대운표를 변경하지 않는다.
    r = calculate(BirthInput(
        gender="male", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울",
    ))
    lc = r.luck_cycles
    assert lc is not None and r.pillars is not None
    before = [d.model_dump() for d in lc.daewoon_table]
    profiles = resolve_all_daewoon_progressions(lc.daewoon_table, r.pillars)
    assert len(profiles) == len(lc.daewoon_table)
    valid = set(get_args(ProgressionMode))
    assert all(p.mode in valid for p in profiles)
    assert [d.model_dump() for d in lc.daewoon_table] == before


# ── 문구 회귀: 하드 전/후반 분할 재유입 금지 + 서술 전용 헤더 ───────────────


def test_directive_has_no_hard_half_split() -> None:
    assert "0-4" not in DAEWOON_FRAMING_DIRECTIVE
    assert "5-9" not in DAEWOON_FRAMING_DIRECTIVE
    assert "상대적으로 드러나기 쉽다" in DAEWOON_FRAMING_DIRECTIVE


def test_progression_lines_silent_when_all_default() -> None:
    prof = resolve_daewoon_progression(_daewoon("癸", "巳"), _PILLARS)
    assert prof.mode == "default_gradient"
    assert daewoon_progression_lines([prof]) == []


def test_progression_lines_carry_inert_header() -> None:
    prof = resolve_daewoon_progression(
        _daewoon("丙", "子", relations=["충:子-午"]), _PILLARS,
    )
    lines = daewoon_progression_lines([prof])
    assert lines and "서술 전용" in lines[0] and "점수" in lines[0]
    assert any("지지 조기 발동" in ln for ln in lines)
    joined = "\n".join(lines)
    assert "0-4" not in joined and "5-9" not in joined


def test_mode_label_map_covers_all_modes() -> None:
    assert set(PROGRESSION_MODE_KO) == set(get_args(ProgressionMode))
