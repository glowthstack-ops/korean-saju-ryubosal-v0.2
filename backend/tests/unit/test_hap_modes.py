"""천간합 작용 모드 판정 검증 (HAP_INTERACTION_SPEC Phase 1).

합화(confirmed)·합반/합거·일간 본신지합·쟁투·간격극 차단을 통제 케이스로 확인하고,
실제 예제 사례(己亥 일주 + 운 甲 정관)가 일간 본신지합으로 분류되는지 검증한다.
"""

from __future__ import annotations

from datetime import date

from saju_manse_analysis.relations.hap_modes import resolve_stem_hap

from saju_api.services.manse_service import calculate
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.constants import (
    STEM_ELEMENT,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult, HiddenStem, Pillar


def _pillar(stem: str, branch: str, dm: str) -> Pillar:
    """리졸버가 읽는 필드(stem·branch·hidden_stems)만 실제값으로, 나머지는 placeholder."""
    b = Branch(branch)
    hs = [
        HiddenStem(
            stem=h.value, element=STEM_ELEMENT[h].value, type=t.value, weight=wt,
            ten_god=str(ten_god(Stem(dm), h)),
        )
        for h, t, wt in hidden_stems_for(b)
    ]
    return Pillar(
        stem=stem, branch=branch, ganji=stem + branch,
        stem_element="", branch_element="", stem_yinyang="", branch_yinyang="",
        stem_ten_god="", branch_main_ten_god="", twelve_unseong="", hidden_stems=hs,
    )


def _pillars(y: str, m: str, d: str, h: str, dm: str) -> FourPillarsResult:
    return FourPillarsResult(
        year=(_pillar(y.split()[0], y.split()[1], dm) if " " in y
              else _pillar(y[0], y[1], dm)),
        month=_pillar(m[0], m[1], dm),
        day=_pillar(d[0], d[1], dm),
        hour=_pillar(h[0], h[1], dm),
        day_master=dm,
    )


def test_transform_confirmed() -> None:
    """甲己合(化土)이 土 왕지월(辰)·통근에서 합화 확정 — 일간 아닌 쌍."""
    # 일간 丙: 甲(년)·己(월) 합, 月支 辰(土 왕)·土 통근 → confirmed.
    p = _pillars("甲辰", "己辰", "丙午", "丙申", dm="丙")
    res = resolve_stem_hap(p, favorability={"土": "용신", "木": "기신"})
    hap = next(r for r in res if set(r.pair) == {"甲", "己"})
    assert hap.transform_tier == "confirmed"
    assert hap.hap_mode == "transform"
    assert hap.transform_element == "土"


def test_bind_and_remove_effect() -> None:
    """化 실패 시 합반 + 합거 효과 — 기신(金) 묶임=boon."""
    # 일간 丙: 庚(년)·乙(월) 합(化金), 月支 午(火) → 金 死 → tier none → bind.
    p = _pillars("庚午", "乙午", "丙寅", "丙申", dm="丙")
    res = resolve_stem_hap(p, favorability={"金": "기신", "木": "한신"})
    hap = next(r for r in res if set(r.pair) == {"庚", "乙"})
    assert hap.transform_tier == "none"
    assert hap.hap_mode == "bind"
    geng = next(a for a in hap.affected if a.stem == "庚")
    assert geng.role == "기신" and geng.effect == "boon"  # 기신 합거 = 길


def test_day_master_self_combine_not_remove() -> None:
    """일간 자합(본신지합)은 합거·기반 아님 — 운 甲(정관)과 합해도 십성 그대로."""
    p = _pillars("庚申", "丁亥", "己亥", "己巳", dm="己")
    res = resolve_stem_hap(p, favorability={"木": "기신"}, luck_stems=["甲"])
    hap = next(r for r in res if set(r.pair) == {"甲", "己"})
    assert hap.hap_mode == "combine_self"
    assert hap.luck_origin is True
    assert hap.direction is None  # 합거 아님
    other = hap.affected[0]
    assert other.stem == "甲" and other.ten_god == "정관"


def test_contend_detected() -> None:
    """두 庚이 한 乙을 다투면 쟁합 — 단 제3 천간이 隔位면 쟁투 소멸(SPEC §B, 2026-10-25)."""
    # 시주 庚은 월간 乙과 隔位(day 를 건너뜀) → 年庚-月乙 쌍은 쟁합이 아니다.
    p = _pillars("庚申", "乙酉", "丙寅", "庚寅", dm="丙")
    res = resolve_stem_hap(p, favorability={})
    ym = next(
        r for r in res
        if set(r.pair) == {"乙", "庚"} and set(r.positions) == {"year", "month"}
    )
    assert ym.contend is False and ym.blocked is False
    # 일간 자리 庚(월간 乙과 인접)이 다투면 쟁합 — 쌍은 年庚-月乙, 제3자 日庚.
    p2 = _pillars("庚申", "乙酉", "庚寅", "丙寅", dm="庚")
    res2 = resolve_stem_hap(p2, favorability={})
    ym2 = next(
        r for r in res2
        if set(r.pair) == {"乙", "庚"} and set(r.positions) == {"year", "month"}
    )
    assert ym2.contend is True and ym2.contested_stem == "乙"


def test_day_master_competitor_is_not_dissolved_by_geokwi() -> None:
    """일간이 격위에서 끼어도 쟁합은 유지된다(CASE-028 재생 교정) — 운 丙 vs 연간 辛, 일간 丙."""
    p = _pillars("辛丑", "丁酉", "丙寅", "甲午", dm="丙")
    res = resolve_stem_hap(p, favorability={"水": "구신"}, luck_stems=["丙"])
    luck = next(r for r in res if r.luck_origin and set(r.pair) == {"丙", "辛"})
    assert luck.contend is True and luck.contested_stem == "辛"
    assert luck.transform_tier != "confirmed"


def test_geokwi_caps_tier_to_conditional() -> None:
    """隔位(年干↔時干) 합은 월령·통근을 갖춰도 化 확정이 아니다(2026-10-25 교정)."""
    # 甲(년)·己(시) 합, 辰월 土 왕·통근, 사이 丙·壬은 木·土를 극하지 않음(간격극 아님).
    p = _pillars("甲辰", "丙辰", "壬午", "己未", dm="壬")
    hap = next(r for r in resolve_stem_hap(p, favorability={"土": "용신"})
               if set(r.pair) == {"甲", "己"})
    assert hap.weakened is True and hap.blocked is False
    assert hap.transform_tier == "conditional" and hap.hap_mode == "bind"


def test_natal_bind_notes_weaker_rooted_side() -> None:
    """원국 합반 — 뿌리가 약한 쪽을 '묶이기 쉬운 쪽' 노트로만 표기(판정·점수 불변)."""
    p = _pillars("庚午", "乙午", "丙寅", "丙申", dm="丙")  # 乙庚 bind, 木 뿌리 寅 1 / 金 뿌리 申 1
    hap = next(r for r in resolve_stem_hap(p, favorability={"金": "기신"})
               if set(r.pair) == {"庚", "乙"})
    assert hap.hap_mode == "bind" and hap.direction is None
    # 午午寅申: 木 뿌리=寅(甲) 1개, 金 뿌리=申(庚) 1개 → 동률이면 노트 없음
    assert not any("묶이기 쉬운 쪽" in n for n in hap.notes)
    p2 = _pillars("庚午", "乙卯", "丙寅", "丙辰", dm="丙")  # 木 뿌리 卯·寅·辰(乙) ≥3, 金 0
    hap2 = next(r for r in resolve_stem_hap(p2, favorability={"金": "기신"})
                if set(r.pair) == {"庚", "乙"})
    assert any("묶이기 쉬운 쪽(통설·참고): 庚" in n for n in hap2.notes)


def test_intervening_control_blocks() -> None:
    """甲己 사이에 극하는 庚(金剋木)이 끼면 간격극으로 합 차단."""
    p = _pillars("甲子", "庚午", "己卯", "丙寅", dm="丙")
    res = resolve_stem_hap(p, favorability={})
    hap = next(r for r in res if set(r.pair) == {"甲", "己"} and "year" in r.positions)
    assert hap.blocked is True
    assert hap.block_reason == "간격극"
    assert hap.hap_mode == "blocked"


def test_real_example_chart() -> None:
    """실제 사례(1980-11-22 09:40, 己亥 일주) + 운 甲(2026-06 월운) → 본신지합 정관."""
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )
    r = calculate(birth)
    assert r.pillars is not None and r.pillars.day_master == "己"
    res = resolve_stem_hap(r.pillars, favorability_map(r), luck_stems=["甲"])
    hap = next(r2 for r2 in res if set(r2.pair) == {"甲", "己"})
    assert hap.hap_mode == "combine_self"  # 일간 정관합 = 본신지합(합거 아님)
    assert any(a.stem == "甲" and a.ten_god == "정관" for a in hap.affected)


# ─── 지지합 Phase 3 ───────────────────────────────────────────


def test_branch_six_with_co_relations() -> None:
    """申·巳 육합(化水) + 동시 파·형 — co_relations 에는 남되 자체 파·부분형은 등급을 막지 않는다.

    원 픽스처(丁亥월)는 월지 亥가 巳를 충해 '제3 글자 충' 방해로 확정 불가(합·충 경쟁) —
    충이 없는 壬子월 픽스처에서는 자체 파·형만으로는 막히지 않아 확정된다.
    """
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
    p = _pillars("庚申", "丁亥", "丙子", "癸巳", dm="丙")
    res = resolve_branch_hap(p, favorability={"水": "기신"})
    six = next(r for r in res if r.kind == "six" and set(r.members) == {"申", "巳"})
    assert any("파" in c for c in six.co_relations)
    assert any("형" in c for c in six.co_relations)
    assert six.transform_tier != "confirmed"
    assert any("합·충 경쟁" in n for n in six.notes)  # 巳亥충
    p2 = _pillars("庚申", "壬子", "丙子", "癸巳", dm="丙")  # 子월 水 왕, 충 없음
    six2 = next(r for r in resolve_branch_hap(p2, favorability={"水": "기신"})
                if r.kind == "six" and set(r.members) == {"申", "巳"})
    assert six2.transform_tier == "confirmed" and six2.hap_mode == "transform"
    assert any("보조 신호" in n for n in six2.notes)


def test_six_inhae_break_does_not_block_and_full_punishment_does() -> None:
    """寅亥: 자체 파는 합을 막지 않음 / 巳申: 寅 동석(寅巳申 완전형)이면 방해(2026-10-25)."""
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
    # 寅亥 육합(化木), 寅월 木 왕 → confirmed(종전: 파 때문에 영구 불확정)
    p = _pillars("辛亥", "庚寅", "丙子", "戊戌", dm="丙")
    six = next(r for r in resolve_branch_hap(p, favorability={"木": "희신"})
               if r.kind == "six" and set(r.members) == {"寅", "亥"})
    assert six.transform_tier == "confirmed"
    # 巳申 + 寅 동석 → 寅巳申 완전형이 방해 → 확정 불가
    p2 = _pillars("庚申", "丁亥", "丙寅", "癸巳", dm="丙")
    six2 = next(r for r in resolve_branch_hap(p2, favorability={"水": "기신"})
                if r.kind == "six" and set(r.members) == {"申", "巳"})
    assert six2.transform_tier != "confirmed"
    assert any("완전형" in n for n in six2.notes)


def test_branch_three_harmony_full() -> None:
    """申子辰 삼합 水국(왕지 子) 완전 성립."""
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
    p = _pillars("庚申", "丙子", "壬辰", "丙午", dm="壬")
    res = resolve_branch_hap(p, favorability={"水": "용신"})
    th = next(r for r in res if r.kind == "three_harmony")
    assert th.transform_element == "水" and set(th.members) == {"申", "子", "辰"}


def test_branch_half_requires_royal() -> None:
    """申辰(왕지 子 없음)은 반합이 아니라 공합(가합) — kind gonghap·tier none·strength 0.3."""
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
    p = _pillars("庚申", "丙寅", "壬辰", "丙午", dm="壬")
    res = resolve_branch_hap(p, favorability={"水": "용신"})
    assert not any(
        r.kind in ("three_harmony", "half") and "子" not in r.members
        and set(r.members) <= {"申", "辰"}
        for r in res
    )
    gh = next(r for r in res if r.kind == "gonghap" and set(r.members) == {"申", "辰"})
    assert gh.transform_tier == "none" and gh.hap_mode == "partial"
    assert gh.strength == 0.3 and gh.royal_included is False
    assert any("공합" in n for n in gh.notes)


def test_chart_transform_hwagigyeok() -> None:
    """일간 합 + 化神 통근 + 일간 무근 → 화기격 후보(진화)."""
    p = _pillars("丙午", "戊午", "癸巳", "丙午", dm="癸")  # 戊癸合化火, 午월 火왕, 일간 水 무근
    hap = next(r for r in resolve_stem_hap(p, favorability={"火": "기신"})
               if set(r.pair) == {"戊", "癸"})
    assert hap.hap_mode == "combine_self" and hap.chart_transform is True
    assert any("진화" in n for n in hap.notes)


def test_branch_six_bind_affected_jeonggi() -> None:
    """육합 합반/합거 시 묶인 지지의 정기(正氣) 십성이 affected로 산출."""
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
    p = _pillars("庚申", "甲午", "丙子", "癸巳", dm="丙")  # 申巳 육합化水, 午월→水 미성립
    six = next(r for r in resolve_branch_hap(p, favorability={})
               if r.kind == "six" and set(r.members) == {"申", "巳"})
    assert six.hap_mode == "bind"
    assert {a.stem for a in six.affected} == {"庚", "丙"}  # 申 정기 庚 · 巳 정기 丙
