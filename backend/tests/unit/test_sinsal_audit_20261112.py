"""신살 전수 점검(2026-11-12) 교정·복원·추가 검증 — 근거: doc/v2_2/SINSAL_AUDIT_20261112.md.

각 교정마다 성립 사례와 함께 **반례**(성립하면 안 되는 쪽)를 둔다 — 반례 없는 테스트는 판정을
넓게 잡아도 통과하기 때문이다.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from saju_manse_analysis.sinsal import sinsal_catalog as cat
from saju_manse_analysis.sinsal.sinsal_aggregator import _detect, sinsal_for_luck

from saju_engines import period_v2_config, risk_auxiliary
from saju_engines import sinsal_modifier_config as cfg
from saju_engines.chart_interpretation import canonical_sinsal_names
from saju_engines.sinsal_modifier import select_llm_sinsal_modifiers
from saju_shared_types.constants import (
    BRANCH_CLASHES,
    SIX_COMBINATIONS,
    STEM_CLASHES,
    STEM_COMBINATIONS,
)
from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S
from saju_shared_types.sinsal import SinsalModifier
from saju_shared_types.twelve_sinsal import (
    BASE_MAPS,
    BRANCH_ORDER,
    TWELVE_SINSAL_ORDER,
    TWELVE_SINSAL_POSITIONAL,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _pillars(year: str, month: str, day: str, hour: str | None = None) -> SimpleNamespace:
    """간지 문자열(예: '甲子')로 판정 함수가 읽는 최소 필드만 가진 원국을 만든다."""

    def pillar(gz: str) -> SimpleNamespace:
        return SimpleNamespace(stem=gz[0], branch=gz[1], ganji=gz)

    return SimpleNamespace(
        year=pillar(year), month=pillar(month), day=pillar(day),
        hour=pillar(hour) if hour else None, gongmang_branches=[],
    )


def _natal(pillars: SimpleNamespace, gender: str | None = None) -> set[tuple[str, str]]:
    """원국 판정 결과를 (자리, 이름) 집합으로."""
    return {(pos, name) for name, _cat, pos, _basis in _detect(pillars, gender)}  # type: ignore[arg-type]


def _luck(
    pillars: SimpleNamespace, stem: S, branch: B, period_type: str | None = None,
) -> set[str]:
    return {x.name for x in sinsal_for_luck(pillars, stem, branch, period_type)}  # type: ignore[arg-type]


# ── 1. 원진(元辰) — 陽男陰女 +7 / 陰男陽女 +5 ─────────────────────────────────────


def test_yuanchen_follows_gender_and_year_polarity() -> None:
    # 甲子년(양간년): 충 午의 다음 자리 未(+7)는 陽男, 앞 자리 巳(+5)는 陽女.
    p = _pillars("甲子", "辛未", "戊寅", "丁巳")
    assert ("month", "원진(元辰)") in _natal(p, "male")
    assert ("hour", "원진(元辰)") not in _natal(p, "male")
    assert ("hour", "원진(元辰)") in _natal(p, "female")
    assert ("month", "원진(元辰)") not in _natal(p, "female")  # 종전 구현은 여기서 성립했다
    # 乙丑년(음간년): 충 未의 앞 자리 午(+5)는 陰男, 다음 자리 申(+7)는 陰女.
    q = _pillars("乙丑", "壬午", "戊寅", "庚申")
    assert ("month", "원진(元辰)") in _natal(q, "male")
    assert ("hour", "원진(元辰)") in _natal(q, "female")
    assert ("hour", "원진(元辰)") not in _natal(q, "male")


@pytest.mark.parametrize("gender", [None, "unknown"])
def test_yuanchen_is_not_judged_without_gender(gender: str | None) -> None:
    p = _pillars("甲子", "辛未", "戊寅", "丁巳")
    assert not any(name == "원진(元辰)" for _pos, name in _natal(p, gender))
    # 구교살은 두 자리(±3)를 모두 같은 이름으로 내므로 성별 없이도 판정한다(子년 → 卯·酉).
    r = _pillars("甲子", "丁卯", "戊寅", "辛酉")
    assert {("month", "구교살"), ("hour", "구교살")} <= _natal(r, gender)


# ── 2. 자리별 12신살 9종 복원 ────────────────────────────────────────────────────


def test_cheonsal_is_judged_from_day_trine_only() -> None:
    # 일지 酉(巳酉丑국)의 천살은 辰.
    p = _pillars("丙午", "辛丑", "乙酉", "庚辰")
    got = _natal(p)
    assert ("hour", "천살") in got
    # 반례 ①: 월지 丑은 연지 午(寅午戌국) 기준으로만 천살 — 연지 기준은 인정하지 않는다.
    assert ("month", "천살") not in got
    assert all("연지" not in basis for _n, c, _p, basis in _detect(p) if c == "twelve_sinsal")  # type: ignore[arg-type]
    # 반례 ②: 일지 卯(亥卯未국)에서 未는 천살이 아니라 화개살, 천살은 戌이다.
    q = _pillars("丙午", "乙未", "乙卯", "丙子")
    assert not any(name == "천살" for _pos, name in _natal(q))
    assert ("month", "화개살") in _natal(q)


def test_self_sinsal_base_is_day_only_everywhere() -> None:
    """자기 명식 상대 12신살의 기준 자리는 일지 하나 — 모든 소비처가 같은 상수를 읽는다."""
    from saju_shared_types.twelve_sinsal import SELF_SINSAL_BASE_SLOTS, self_sinsal_bases

    assert SELF_SINSAL_BASE_SLOTS == ("day",)
    assert self_sinsal_bases("午", "酉") == [("day", "일지", B.YU)]
    assert self_sinsal_bases("午", "酉", "역마살") == [("day", "일지", B.YU)]
    # 운: 연지 午(寅午戌국) 기준 역마 申은 인정하지 않고, 일지 酉(巳酉丑국) 기준 역마 亥만 인정한다.
    p = _pillars("丙午", "辛丑", "乙酉", "庚辰")
    assert "역마살" in _luck(p, S.GYE, B.HAE)
    assert "역마살" not in _luck(p, S.GAP, B.SIN)


def test_luck_twelve_sinsal_matches_shared_table_for_every_branch() -> None:
    """운 지지 12개 × 삼합국 4개 전부를 공용 표(BASE_MAPS)와 대조한다."""
    display = {"년살": "도화"}  # 집계기 표시명
    all_names = {display.get(n, n) for n in TWELVE_SINSAL_ORDER}
    for base in (B.JA, B.O, B.YU, B.MYO):
        # 연지·일지를 같은 지지로 두어 한 기준의 결과만 남긴다.
        p = _pillars(f"甲{base.value}", "丙寅", f"甲{base.value}")
        for target in BRANCH_ORDER:
            expected = display.get(BASE_MAPS[base][target], BASE_MAPS[base][target])
            got = _luck(p, S.GAP, target) & all_names
            assert got == {expected}, (base, target, got)


def test_positional_twelve_sinsal_are_the_nine_without_yeokma_dohwa_hwagae() -> None:
    assert TWELVE_SINSAL_POSITIONAL == set(TWELVE_SINSAL_ORDER) - {"역마살", "년살", "화개살"}
    assert all(cat.CATALOG_META[n]["polarity"] for n in TWELVE_SINSAL_POSITIONAL)


# ── 3. 상문·조객 — 세운·월운 판정 ────────────────────────────────────────────────


def test_mourning_stars_apply_to_year_and_month_luck_only() -> None:
    p = _pillars("甲子", "丙寅", "戊午", "壬子")  # 子년생 → 상문 寅, 조객 戌
    for period in ("year", "month"):
        assert "상문" in _luck(p, S.GAP, B.IN, period)
        assert "조객" in _luck(p, S.GAP, B.SUL, period)
        assert not {"상문", "조객"} & _luck(p, S.GAP, B.JIN, period)  # 반례: 다른 지지
    # 대운(None)·일운에는 붙이지 않는다.
    for period in (None, "day"):
        assert "상문" not in _luck(p, S.GAP, B.IN, period)
        assert "조객" not in _luck(p, S.GAP, B.SUL, period)


# ── 4. 통설에 맞춘 성립 조건 교정 ────────────────────────────────────────────────


def test_tanghwa_requires_companion_branch_in_month_or_hour() -> None:
    # 寅일은 월지·시지에 寅·巳·申이 있어야 한다.
    assert ("day", "탕화살") in _natal(_pillars("甲子", "己巳", "戊寅", "壬子"))
    assert ("day", "탕화살") not in _natal(_pillars("甲子", "丁卯", "戊寅", "壬子"))  # 일지 단독
    # 午일은 午·辰·丑, 丑일은 丑·戌·未.
    assert ("day", "탕화살") in _natal(_pillars("甲子", "戊辰", "庚午", "壬子"))
    assert ("day", "탕화살") in _natal(_pillars("甲子", "丁卯", "己丑", "甲戌"))
    # 반례 ①: 짝 글자가 연지에만 있으면 성립하지 않는다(월지·시지만 본다).
    assert ("day", "탕화살") not in _natal(_pillars("甲辰", "丁卯", "庚午", "壬子"))
    # 반례 ②: 午는 丑일의 짝 글자가 아니다(1차 반영 때 잘못 넣었던 칸).
    assert ("day", "탕화살") not in _natal(_pillars("甲子", "庚午", "己丑", "甲子"))
    assert cat.TANGHWA_COMPANIONS[B.CHUK] == {B.CHUK, B.SUL, B.MI}


def test_gyeokgak_is_hour_branch_only() -> None:
    # 일지 子의 격각 寅 — 시지에 있을 때만.
    assert ("hour", "격각살") in _natal(_pillars("甲辰", "丁卯", "甲子", "丙寅"))
    got = _natal(_pillars("甲寅", "丙寅", "甲子", "甲子"))
    assert not any(name == "격각살" for _pos, name in got)  # 연·월의 寅은 판정하지 않는다


def test_hyeoprok_needs_adjacent_pair_and_absent_rok() -> None:
    # 甲일 정록 寅 — 丑·卯가 이웃 기둥에 있고 寅이 원국에 없어야 한다.
    assert {("year", "협록"), ("month", "협록")} <= _natal(_pillars("乙丑", "己卯", "甲子", "庚午"))
    # 반례 ①: 丑(연)·卯(시)는 이웃하지 않는다.
    got = _natal(_pillars("乙丑", "壬午", "甲子", "丁卯"))
    assert not any(name == "협록" for _pos, name in got)
    # 반례 ②: 寅이 원국에 있으면(塡實) 성립하지 않는다.
    got = _natal(_pillars("乙丑", "己卯", "甲寅", "庚午"))
    assert not any(name == "협록" for _pos, name in got)
    # 운: 원국 丑 + 운 卯로 완성되지만, 원국에 寅이 있으면 아니다.
    assert "협록" in _luck(_pillars("乙丑", "壬午", "甲子", "庚午"), S.JEONG, B.MYO)
    assert "협록" not in _luck(_pillars("乙丑", "戊寅", "甲子", "庚午"), S.JEONG, B.MYO)


def test_hongyeom_eul_reads_both_o_and_sin_in_aggregator_only() -> None:
    assert ("hour", "홍염") in _natal(_pillars("甲子", "丁卯", "乙丑", "甲申"))
    assert ("hour", "홍염") in _natal(_pillars("甲子", "丁卯", "乙丑", "壬午"))
    # 반례: 甲 일간은 申을 홍염으로 보지 않는다(병기는 乙만).
    assert ("hour", "홍염") not in _natal(_pillars("甲子", "丁卯", "甲子", "壬申"))
    # 궁합 점수·오늘의 운세가 직접 읽는 표는 그대로다(점수·사전 버전 불변).
    assert cat.HONGYEOM[S.EUL] == B.O


# ── 5. 추가 12종 조견표 ──────────────────────────────────────────────────────────


def test_deok_hap_and_wolgong_are_derived_from_deok_tables() -> None:
    stem_hap = {a: b for pair in STEM_COMBINATIONS for a, b in (tuple(pair), tuple(pair)[::-1])}
    six_hap = {a: b for pair in SIX_COMBINATIONS for a, b in (tuple(pair), tuple(pair)[::-1])}
    stem_clash = {a: b for pair in STEM_CLASHES for a, b in (tuple(pair), tuple(pair)[::-1])}
    for month in BRANCH_ORDER:
        deok = cat.CHEONDEOK[month]
        expected = stem_hap[deok] if isinstance(deok, S) else six_hap[deok]  # type: ignore[index]
        assert cat.CHEONDEOK_HAP[month] == expected, month
        assert cat.WOLDEOK_HAP[month] == stem_hap[cat.WOLDEOK[month]]
        # 월공 = 월덕의 천간충(丙↔壬·甲↔庚).
        assert cat.WOLGONG[month].value == stem_clash[cat.WOLDEOK[month].value]


def test_hongran_and_cheonhui_table() -> None:
    expected = "卯寅丑子亥戌酉申未午巳辰"  # 子년부터 亥년까지의 홍란
    for year_branch, want in zip(BRANCH_ORDER, expected, strict=True):
        assert cat.hongran_branch(year_branch).value == want
    clash = {a: b for pair in BRANCH_CLASHES for a, b in (tuple(pair), tuple(pair)[::-1])}
    # 子년생: 홍란 卯, 천희 酉(홍란의 충). 연주 자신은 판정 대상이 아니다.
    got = _natal(_pillars("甲子", "丁卯", "戊寅", "辛酉"))
    assert ("month", "홍란") in got and ("hour", "천희") in got
    assert clash[B.MYO] == B.YU
    assert "홍란" in _luck(_pillars("甲子", "丙寅", "戊寅"), S.GAP, B.MYO)
    assert "홍란" not in _luck(_pillars("甲子", "丙寅", "戊寅"), S.GAP, B.YU)


def test_added_day_pillar_and_position_limited_stars() -> None:
    # 일주 자체: 효신·십악대패·육수·진신.
    assert ("day", "효신살") in _natal(_pillars("甲子", "丙寅", "甲子"))
    assert ("day", "진신") in _natal(_pillars("甲子", "丙寅", "甲子"))
    assert ("day", "십악대패") in _natal(_pillars("甲子", "丙寅", "甲辰"))
    assert ("day", "육수") in _natal(_pillars("甲子", "丙寅", "丙午"))
    assert not {"효신살", "십악대패", "육수", "진신"} & {
        n for _p, n in _natal(_pillars("甲子", "丙寅", "乙丑"))
    }
    # 급각살: 寅월은 亥·子 — 일지·시지에만(연지의 子는 아니다).
    got = _natal(_pillars("甲子", "丙寅", "乙亥", "丙子"))
    assert {("day", "급각살"), ("hour", "급각살")} <= got and ("year", "급각살") not in got
    # 절로공망: 甲일은 申·酉 시 — 시지에만.
    assert ("hour", "절로공망") in _natal(_pillars("甲子", "丙寅", "甲午", "壬申"))
    assert not any(n == "절로공망" for _p, n in _natal(_pillars("甲申", "壬申", "甲午", "甲子")))
    # 유하살: 甲일 酉.
    assert ("month", "유하살") in _natal(_pillars("甲子", "癸酉", "甲午", "甲子"))
    assert "유하살" in _luck(_pillars("甲子", "丙寅", "甲午"), S.GYE, B.YU)


def test_added_names_have_catalog_meta() -> None:
    added = {
        "급각살", "효신살", "유하살", "십악대패", "절로공망", "천덕합", "월덕합", "월공귀인",
        "육수", "진신", "홍란", "천희",
    }
    assert added <= set(cat.CATALOG_META)
    assert added | TWELVE_SINSAL_POSITIONAL == cfg.SINSAL_PAYLOAD_LOW_PRIORITY


# ── 6. 소비처 — 죽은 참조 해소·LLM 선별 순위 ─────────────────────────────────────


def test_risk_amplifier_luck_names_revived_by_this_audit_are_reachable() -> None:
    """위험 보조 증폭 사전이 운 신살 조건으로 드는 12신살·상문·조객이 실제로 판정되는가."""
    items = json.loads((_DICTS / "risk_auxiliary_amplifiers.json").read_text("utf-8"))["items"]
    referenced = {n for it in items for n in it.get("luckSinsalIn", [])}
    revived = (TWELVE_SINSAL_POSITIONAL | {"상문", "조객"}) & referenced
    assert {"겁살", "재살", "천살", "망신살", "지살", "육해살", "상문", "조객"} <= revived
    produced: set[str] = set()
    p = _pillars("甲子", "丙寅", "戊午", "壬子")
    for branch in BRANCH_ORDER:
        produced |= _luck(p, S.GAP, branch, "year")
    assert revived <= produced


def _modifier(name: str) -> SinsalModifier:
    return SinsalModifier(
        name=name, polarity="caution", position="month", domain_match=True,
        activation_status="activated", internal_weight=0.5,
    )


def test_positional_twelve_sinsal_do_not_displace_other_stars_in_payload() -> None:
    limit = cfg.SINSAL_PAYLOAD_MAX_PER_EVENT
    full = [_modifier(n) for n in ("천살", "겁살", "백호", "양인", "현침")]
    assert [m.star for m in select_llm_sinsal_modifiers(full)] == ["백호", "양인", "현침"][:limit]
    # 빈 칸이 있으면 실린다.
    partial = [_modifier(n) for n in ("천살", "백호")]
    assert [m.star for m in select_llm_sinsal_modifiers(partial)] == ["백호", "천살"]


def test_revived_names_feed_risk_amplifiers_only_when_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """되살린 이름은 위험 점수 변화라 플래그 뒤에 둔다 — OFF 면 보조 사실에서 빠진다."""
    natal_item = SimpleNamespace(name="재살")
    kept_item = SimpleNamespace(name="백호")
    result = SimpleNamespace(
        traditional_extras=SimpleNamespace(
            sinsal=SimpleNamespace(full_list=[natal_item, kept_item]),
        ),
        pillars=None, geokguk=None,
    )
    target = SimpleNamespace(luck_sinsal=[
        SimpleNamespace(name="겁살"), SimpleNamespace(name="상문"), SimpleNamespace(name="양인"),
    ])
    monkeypatch.setattr(period_v2_config, "RISK_AUX_REVIVED_SINSAL_ENABLED", False)
    off = risk_auxiliary.build_auxiliary_facts(result, target, {}, polarity_role="GI")  # type: ignore[arg-type]
    assert off.natal_sinsal == {"백호"} and off.luck_sinsal == {"양인"}
    monkeypatch.setattr(period_v2_config, "RISK_AUX_REVIVED_SINSAL_ENABLED", True)
    on = risk_auxiliary.build_auxiliary_facts(result, target, {}, polarity_role="GI")  # type: ignore[arg-type]
    assert on.natal_sinsal == {"재살", "백호"} and on.luck_sinsal == {"겁살", "상문", "양인"}


def test_canonical_names_cover_judged_names_without_text() -> None:
    # 문구는 아직 없지만 판정되는 이름 — 출력 정리 단계가 '격각살의 훼손'으로 보지 않아야 한다.
    assert {"급각살", "효신살", "천살", "원진(元辰)"} <= canonical_sinsal_names()


# ── 7. 숨김 처리 — 현대 자료에서 거의 쓰이지 않는 이름 ───────────────────────────


def test_hidden_names_are_judged_but_not_exposed() -> None:
    from saju_api.services.manse_service import calculate
    from saju_engines.sinsal_modifier import derive_natal_sinsal_modifiers
    from saju_shared_types.birth_input import BirthInput

    # 1990-07-15 14:30 여성 — 庚午 癸未 辛巳 乙未: 십악대패(일주)·격각살(시지)이 판정된다.
    r = calculate(BirthInput(
        birth_date="1990-07-15", birth_time="14:30", birth_place_name="서울", gender="female",
        reference_date="2026-11-12",
    ))
    s = r.traditional_extras.sinsal
    judged = {it.name for it in s.full_list}
    assert {"십악대패", "격각살"} <= judged  # 판정은 그대로(엔진 전용)
    assert all(it.hidden == (it.name in cat.HIDDEN_NAMES) for it in s.full_list)
    exposed = {n for names in s.by_pillar.values() for n in names}
    exposed |= {n for names in s.by_category.values() for n in names}
    exposed |= set(s.summary.major_positive + s.summary.major_caution + s.summary.repeated)
    exposed |= set(s.summary.palace_sensitive + s.summary.structure_overlapped)
    assert not exposed & cat.HIDDEN_NAMES
    assert {"현침", "급각살", "월살"} <= exposed  # 반례: 숨김 대상이 아닌 이름은 남는다
    # 시주 乙未는 백호 간지지만 일주(辛巳)가 백호가 아니라 판정하지 않는다(일주 기준).
    assert "백호" not in judged
    assert not {m.name for m in derive_natal_sinsal_modifiers(r, "career")} & cat.HIDDEN_NAMES
    # 운 신살도 같은 표지를 달고 내려간다(화면 필터가 읽는다).
    for pillar in r.luck_cycles.yearly_luck:
        assert all(x.hidden == (x.name in cat.HIDDEN_NAMES) for x in pillar.luck_sinsal)


def test_hidden_luck_sinsal_is_not_rendered_in_luck_grounding() -> None:
    from saju_api.services.manse_service import calculate
    from saju_engines.chart_interpretation import build_luck_grounding
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        birth_date="1990-07-15", birth_time="14:30", birth_place_name="서울", gender="female",
        reference_date="2026-11-12",
    ))
    # 2027 丁未 세운에는 격각살(일지 巳 +2 = 未)이 들어온다 — 문구 사전에 있는 이름이지만 숨김.
    y2027 = next(p for p in r.luck_cycles.yearly_luck if p.label == "2027")
    assert any(x.name == "격각살" and x.hidden for x in y2027.luck_sinsal)
    text = str(build_luck_grounding(r, y2027))
    assert "격각살" not in text


def test_hidden_names_are_all_judgeable_catalog_names() -> None:
    assert cat.HIDDEN_NAMES <= set(cat.CATALOG_META)
    # 12신살·주요 신살은 숨기지 않는다.
    assert not cat.HIDDEN_NAMES & (TWELVE_SINSAL_POSITIONAL | {"천을귀인", "백호", "괴강", "양인"})


# ── 8. 괴강·백호 — 일주 기준 ─────────────────────────────────────────────────────


def test_goegang_and_baekho_need_the_day_pillar() -> None:
    # 일주가 괴강(庚辰)이면 일주와, 그 전제에서 다른 기둥의 괴강 간지(壬辰)도 인정한다.
    got = _natal(_pillars("壬辰", "丙午", "庚辰", "丁丑"))
    assert {("day", "괴강"), ("year", "괴강")} <= got
    # 반례: 일주가 괴강이 아니면 연·월·시에 괴강 간지가 있어도 판정하지 않는다.
    got = _natal(_pillars("壬辰", "庚戌", "甲子", "戊戌"))
    assert not any(name == "괴강" for _pos, name in got)
    # 백호도 같다 — 일주 甲辰이면 시주 丁丑까지, 일주가 아니면 없음.
    got = _natal(_pillars("壬申", "丙午", "甲辰", "丁丑"))
    assert {("day", "백호"), ("hour", "백호")} <= got
    got = _natal(_pillars("甲辰", "丁丑", "庚午", "丙戌"))
    assert not any(name == "백호" for _pos, name in got)


def test_luck_goegang_and_baekho_count_only_on_matching_day_pillar() -> None:
    goegang_day = _pillars("甲子", "丙寅", "庚辰")
    plain_day = _pillars("甲子", "丙寅", "庚午")
    assert "괴강" in _luck(goegang_day, S.IM, B.JIN)      # 운 壬辰 × 일주 庚辰
    assert "괴강" not in _luck(plain_day, S.IM, B.JIN)    # 반례: 일주가 괴강이 아니다
    assert "괴강" not in _luck(goegang_day, S.GAP, B.JIN)  # 반례: 운 간지가 괴강이 아니다
    baekho_day = _pillars("甲子", "丙寅", "甲辰")
    assert "백호" in _luck(baekho_day, S.JEONG, B.CHUK)   # 운 丁丑 × 일주 甲辰
    assert "백호" not in _luck(plain_day, S.JEONG, B.CHUK)
    # 일주가 괴강이어도 백호 간지 운은 백호가 아니다(두 표는 따로 본다).
    assert "백호" not in _luck(goegang_day, S.JEONG, B.CHUK)


# ── 9. 도화만 연지·일지 병용 / 괴강·나체도화 현대 한국 자료 기준 (2026-11-13) ───────────


def test_dohwa_alone_keeps_year_and_day_bases() -> None:
    from saju_shared_types.twelve_sinsal import DOHWA_BASE_SLOTS, self_sinsal_bases

    assert DOHWA_BASE_SLOTS == ("year", "day")
    for name in ("년살", "도화"):
        assert self_sinsal_bases("午", "酉", name) == [
            ("year", "연지", B.O), ("day", "일지", B.YU),
        ]
    # 丙午·辛丑·乙酉·庚辰: 도화 — 연지 午(寅午戌국) 卯, 일지 酉(巳酉丑국) 午 → 연주 午가 일지 기준
    # 도화.
    p = _pillars("丙午", "辛丑", "乙酉", "庚辰")
    assert ("year", "도화") in _natal(p)
    # 운: 卯(연지 기준)·午(일지 기준) 모두 도화. 역마는 일지 기준만(申은 연지 기준이라 아님).
    assert "도화" in _luck(p, S.JEONG, B.MYO) and "도화" in _luck(p, S.GAP, B.O)
    assert "역마살" not in _luck(p, S.GAP, B.SIN)
    # 일지 자신이 도화가 되는 경우가 다시 생긴다 — 연지 丑(巳酉丑국)의 년살 午가 일지에.
    q = _pillars("辛丑", "乙未", "丙午", "戊辰")
    day_dohwa = [basis for n, _c, pos, basis in _detect(q) if n == "도화" and pos == "day"]  # type: ignore[arg-type]
    assert len(day_dohwa) == 1 and "연지 丑 기준" in day_dohwa[0]
    # 반례: 같은 명식에서 화개(연지 丑 기준 丑)는 연지 기준이라 인정하지 않는다.
    assert not any("연지" in basis for n, _c, _p, basis in _detect(q) if n == "화개살")  # type: ignore[arg-type]


def test_goegang_days_follow_modern_korean_sources() -> None:
    assert cat.GOEGANG == {
        (S.GYEONG, B.JIN), (S.GYEONG, B.SUL), (S.IM, B.JIN), (S.IM, B.SUL),
    }
    assert ("day", "괴강") in _natal(_pillars("甲子", "丙寅", "壬戌"))
    # 반례: 戊戌(원전의 네 번째 일주)·戊辰은 현대 한국 공통 4일주에 없다.
    assert not any(n == "괴강" for _p, n in _natal(_pillars("甲子", "丙寅", "戊戌")))
    assert not any(n == "괴강" for _p, n in _natal(_pillars("甲子", "丙寅", "戊辰")))
    # 壬戌은 백호 7일주에도 들어 있어 일주면 둘 다 붙는다.
    assert ("day", "백호") in _natal(_pillars("甲子", "丙寅", "壬戌"))
