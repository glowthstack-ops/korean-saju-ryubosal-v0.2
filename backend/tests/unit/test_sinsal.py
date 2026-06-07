"""전체 신살 계산/표시 (spec §9 검증 기준)."""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_BASE = dict(birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울", gender="male")


def _sinsal(**over):
    r = calculate(BirthInput(**{**_BASE, **over}))
    assert r.traditional_extras is not None and r.traditional_extras.sinsal is not None
    return r, r.traditional_extras.sinsal


def test_all_detections_in_full_list_and_views_share_source() -> None:
    _r, s = _sinsal()
    full_names = {it.name for it in s.full_list}
    # 주별/카테고리별 이름은 모두 full_list에서 파생(동일 source).
    for names in s.by_pillar.values():
        assert set(names) <= full_names
    for names in s.by_category.values():
        assert set(names) <= full_names
    # 각 full_list 항목은 위치/근거/궁성을 갖춘다(이름만 나열 금지).
    for it in s.full_list:
        assert it.basis and it.position and it.palace


def test_known_sinsal_anchor() -> None:
    # 일간 己 → 천을귀인 子/申; 원국 申(년지) → 천을귀인 @year.
    _r, s = _sinsal()
    cheoneul = [it for it in s.full_list if it.name == "천을귀인"]
    assert any(it.position == "year" for it in cheoneul)
    # 역마살은 사생지(寅申巳亥) 글자 기준 — 申·亥 위치에 표시.
    yeokma = [it for it in s.full_list if it.name == "역마살"]
    assert {it.position for it in yeokma} >= {"month", "day"}
    # 위치별 12신살(겁살·망신·지살 등)은 펼치지 않는다.
    assert not any(it.name in ("망신살", "지살", "겁살") for it in s.full_list)


def test_repeated_sinsal_intensity_increases() -> None:
    # 亥亥 → 역마살(글자살) 반복 → repeated=True, 강도 상승.
    _r, s = _sinsal()
    yeokma = [it for it in s.full_list if it.name == "역마살"]
    assert all(it.repeated for it in yeokma)
    assert any(it.intensity in ("high", "very_high") for it in yeokma)
    assert "역마살" in s.summary.repeated


def test_hour_unknown_suppresses_hour_sinsal() -> None:
    _r, s = _sinsal(birth_time=None, birth_time_unknown=True)
    assert s.hour_unknown is True
    assert s.by_pillar.get("hour", []) == []
    assert all(it.position != "hour" for it in s.full_list)


def test_added_standard_sinsal() -> None:
    # 1980(진태양시 戊辰, 己亥일·년지 申·월지 亥): 신규 표준 신살 감지.
    _r, s = _sinsal()
    names = {it.name for it in s.full_list}
    assert "관귀학관" in names  # 일간 己 → 亥 (관성 장생)
    assert "고신살" in names    # 년지 申(申酉戌) → 亥
    assert "천문성" in names    # 일지 亥


def test_yeokma_is_branch_glyph_based() -> None:
    # 09:40(申亥亥巳: 모두 사생지) → 역마살이 네 자리 모두에, 위치별 12신살은 없음.
    _r, s = _sinsal(birth_time="09:40")
    yeokma = {it.position for it in s.full_list if it.name == "역마살"}
    assert yeokma >= {"year", "month", "day", "hour"}
    assert not any(it.name in ("망신살", "지살", "겁살") for it in s.full_list)


def test_added_sinsal_tables_lookup() -> None:
    # 표준표 직접 검증(핵심 표가 의도대로 들어갔는지).
    from saju_manse_analysis.sinsal import sinsal_catalog as cat

    from saju_shared_types.enums import Branch as B
    from saju_shared_types.enums import Stem as S

    assert cat.CHEONROK[S.GAP] == B.IN  # 천록귀인=건록(甲→寅)
    assert cat.MUNGOK[S.GAP] == B.HAE   # 문곡=문창(甲巳)의 충 亥
    assert cat.BIIN[S.GYEONG] == B.MYO  # 비인=양인(庚酉)의 충 卯
    assert cat.GOSHIN[B.SIN] == B.HAE and cat.GWASUK[B.SIN] == B.MI  # 申酉戌→고신亥·과숙未
    assert (S.GAP, B.IN) in cat.ILDEOK and (S.JEONG, B.YU) in cat.ILGWI


def test_sinsal_does_not_affect_strength_or_yongsin() -> None:
    # 신살이 신강약/용신/격국 점수를 바꾸지 않는다(정책).
    r, s = _sinsal()
    assert all(it.use_for_yongsin_decision is False for it in s.full_list)
    assert r.force_analysis.strength.band == "신약"
    assert r.force_analysis.strength.score == 35.51  # 통합형 강약(진태양시 戊辰) 스냅샷
    assert r.yongsin_analysis.final["yongsin"] == "土"
    assert r.geokguk.main_structure == "정재격"
