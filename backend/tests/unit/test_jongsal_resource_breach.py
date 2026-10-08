"""종살 인성 운 감점 방식 정리 — 2026-10-08 데굴님 결정.

종살격(override) 명식에 인성 천간이 운으로 들어오면(특수격 역행 성립) 한신 기준값(−0.3)에
공통 −GEOK_BREAK_PENALTY 를 얹는 대신 기준값을 JONGSAL_RESOURCE_BREACH_FAV(−0.5)로 대체한다.
운 천간이 원국과 합거로 묶이면 대체·감점 모두 없다. 범위: 종살·천간 인성만 — 비겁 천간(극성
GI_STRONG + 공통 역행은 독립 근거라 유지)·지지 인성·가종·다른 종격은 기존 그대로.

검증 분류: ① 돕는 천간 없음(壬子) → 변화 없음, ② 인성 천간(乙卯) → 대체, ③ 합거 → 경향만,
④ 종격 아닌 명식 HAN_BAD 불변, ⑤ 비겁 운 클램프 이전 점수, ⑥ 다른 종격(종재) 공통 처리 불변.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, period_v2_config
from saju_engines import event_engine_v2 as ev
from saju_engines.event_engine_v2 import _ROLE_FAV, PolarityRole
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_REF = date(2026, 7, 27)


@pytest.fixture(scope="module")
def jongsal():
    """丙일간 癸亥 丙辰 丙子 戊子 — 종살격(진종, override). 인성 木·비겁 火·식상 土."""
    r = calculate(BirthInput(
        birth_date="1983-04-17", birth_time="23:40", birth_place_name="서울",
        gender="male", reference_date=_REF,
    ))
    assert r.geokguk is not None and r.geokguk.special_pattern["name"] == "종살격"
    assert r.geokguk.special_pattern["override"] is True
    return r


def _year_cands(result, year: int, monkeypatch):
    monkeypatch.setattr(period_v2_config, "STRUCTURE_BACKGROUND_ENABLED", True)
    return [c for c in EventEngineV2(_DICTS).score_years(result, [year]) if c.period == str(year)]


def test_resource_stem_replaces_han_baseline(jongsal, monkeypatch) -> None:
    """② 2035 乙卯(인성 木木): HAN_BAD 기준값 −0.3 → −0.5 대체, 공통 역행 코드 없음."""
    cands = _year_cands(jongsal, 2035, monkeypatch)
    assert cands
    for c in cands:
        assert c.polarity_role is PolarityRole.HAN_BAD
        assert "特_종살역행_인성_강도대체" in c.reason_codes
        assert "特_특수격역행" not in c.reason_codes
        # 대체 = 기준값 차이만 fav_adj 에 반영 → 다른 보정이 없으면 최종 favorability 가 대체값.
        base = _ROLE_FAV[PolarityRole.HAN_BAD]
        assert c.contributions["fav_adj"] == pytest.approx(
            period_v2_config.JONGSAL_RESOURCE_BREACH_FAV - base
        )
        assert c.favorability == pytest.approx(period_v2_config.JONGSAL_RESOURCE_BREACH_FAV)


def test_non_helping_stem_year_unchanged(jongsal, monkeypatch) -> None:
    """① 2032 壬子(관살 水水): 역행 자체가 없다 — 종살 코드 전무, 용신 강운."""
    cands = _year_cands(jongsal, 2032, monkeypatch)
    assert cands
    for c in cands:
        assert c.polarity_role is PolarityRole.YONG_STRONG
        assert not any(code.startswith("特_") for code in c.reason_codes)


def test_peer_stem_keeps_generic_breach_and_preclamp_score(jongsal, monkeypatch) -> None:
    """⑤ 2026 丙午(비겁 火火): GI_STRONG(극성 규칙 — 천간·지지 모두 구신)에 공통 역행 −0.2 유지.

    극성 산출 근거에 종살 역행이 들어 있지 않으므로(독립 보정) 중복으로 보지 않는다. 클램프 이전
    합산은 −1.2, 표시 favorability 는 −1.0.
    """
    cands = _year_cands(jongsal, 2026, monkeypatch)
    assert cands
    for c in cands:
        assert c.polarity_role is PolarityRole.GI_STRONG
        assert "特_특수격역행" in c.reason_codes
        assert "特_종살역행_인성_강도대체" not in c.reason_codes
        pre_clamp = _ROLE_FAV[PolarityRole.GI_STRONG] + c.contributions["fav_adj"]
        assert pre_clamp == pytest.approx(-1.0 - period_v2_config.GEOK_BREAK_PENALTY)
        assert c.favorability == pytest.approx(-1.0)


def test_bound_resource_stem_is_tendency_only(jongsal, monkeypatch) -> None:
    """③ 인성 천간이 원국과 합거로 묶이면 대체도 공통 감점도 없다(경향 코드만)."""
    monkeypatch.setattr(ev, "_jongsal_resource_breach_mode", lambda *_a, **_k: "mitigated")
    cands = _year_cands(jongsal, 2035, monkeypatch)
    assert cands
    for c in cands:
        assert "特_종살역행_인성_합거완화" in c.reason_codes
        assert "特_종살역행_인성_강도대체" not in c.reason_codes
        assert "特_특수격역행" not in c.reason_codes
        assert c.favorability == pytest.approx(_ROLE_FAV[PolarityRole.HAN_BAD])


def test_other_follow_structure_keeps_generic_breach(jongsal, monkeypatch) -> None:
    """⑥ 종살이 아닌 종격(종재 라벨)은 공통 역행 −0.2 그대로 — 일괄 변경 금지."""
    patched = jongsal.model_copy(update={
        "geokguk": jongsal.geokguk.model_copy(update={
            "special_pattern": {**jongsal.geokguk.special_pattern, "name": "종재격"},
        }),
    })
    cands = _year_cands(patched, 2035, monkeypatch)
    assert cands
    for c in cands:
        assert "特_특수격역행" in c.reason_codes
        assert "特_종살역행_인성_강도대체" not in c.reason_codes
        assert c.contributions["fav_adj"] == pytest.approx(-period_v2_config.GEOK_BREAK_PENALTY)


def test_non_special_chart_han_bad_unchanged(monkeypatch) -> None:
    """④ 종격이 아닌 명식: HAN_BAD 기준값 −0.3 그대로, 종살 코드 없음."""
    r = calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울",
        gender="male", reference_date=_REF,
    ))
    sp = r.geokguk.special_pattern if r.geokguk else None
    assert not (sp and sp.get("override"))
    # 생애 세운 표에서 극성이 HAN_BAD 인 해를 골라 비교 표본으로 쓴다(해마다 극성이 달라 고정 불가).
    from saju_engines.event_scoring import favorability_map

    fav = favorability_map(r)
    years = sorted({
        int(p.label) for d in r.luck_cycles.daewoon_table for p in d.sewoon
        if p.label.isdigit() and int(p.label) >= 2026
        and ev._period_role(p, fav) is PolarityRole.HAN_BAD
    })[:3]
    assert years, "비교용 HAN_BAD 세운이 있어야 한다"
    monkeypatch.setattr(period_v2_config, "STRUCTURE_BACKGROUND_ENABLED", True)
    cands = EventEngineV2(_DICTS).score_years(r, years)
    han = [c for c in cands if c.polarity_role is PolarityRole.HAN_BAD]
    assert han
    for c in han:
        assert not any(code.startswith("特_") for code in c.reason_codes)
        # 기준값 −0.3 축 유지(대체 없음)
        assert c.favorability <= _ROLE_FAV[PolarityRole.HAN_BAD] + 0.5


def test_breach_mode_helper_scope(jongsal) -> None:
    """헬퍼 범위: 종살+인성 천간 → replace, 비겁 천간 → None, 종살 아님/override 아님 → None."""
    from saju_shared_types.luck import LuckPillar

    def pillar(ganji: str) -> LuckPillar:
        return LuckPillar(
            label="t", period_type="year", ganji=ganji, stem=ganji[0], branch=ganji[1],
            stem_ten_god="", branch_ten_god="",
        )

    sp = jongsal.geokguk.special_pattern
    assert ev._jongsal_resource_breach_mode(pillar("乙卯"), jongsal, sp) == "replace"
    assert ev._jongsal_resource_breach_mode(pillar("甲戌"), jongsal, sp) == "replace"  # 천간만
    assert ev._jongsal_resource_breach_mode(pillar("丙午"), jongsal, sp) is None
    assert ev._jongsal_resource_breach_mode(pillar("壬寅"), jongsal, sp) is None  # 지지 인성
    other = {**sp, "name": "종재격"}
    assert ev._jongsal_resource_breach_mode(pillar("乙卯"), jongsal, other) is None
    off = {**sp, "override": False}
    assert ev._jongsal_resource_breach_mode(pillar("乙卯"), jongsal, off) is None
