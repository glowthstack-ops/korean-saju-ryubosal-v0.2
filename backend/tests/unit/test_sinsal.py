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
    # 대상 지지는 원국 성립 여부와 무관하게 항상 응답에 포함(프론트 표 중복 제거용).
    assert s.cheoneul_targets == ["子", "申"]
    # 寅申巳亥 보유는 '이동지' 표지 — 申(년)·亥(월·일) 위치에 표시(역마 성립과 별개).
    marker = [it for it in s.full_list if it.name == "이동지"]
    assert {it.position for it in marker} >= {"year", "month", "day"}
    # 역마살은 연지·일지 삼합국 기준 상대 12신살 — 연지 申(申子辰국)·일지 亥(亥卯未국)의 역마는
    # 각각 寅·巳라 이 명식(申亥亥…)에는 성립하지 않는다(글자살이면 세 자리에 떴을 것).
    assert not any(it.name == "역마살" for it in s.full_list)
    # 위치별 12신살(겁살·망신·지살 등)은 펼치지 않는다.
    assert not any(it.name in ("망신살", "지살", "겁살") for it in s.full_list)


def test_repeated_sinsal_intensity_increases() -> None:
    # 申·亥·亥 → '이동지' 표지 반복 → repeated=True, 강도 상승(표지도 집계 규칙은 공유).
    _r, s = _sinsal()
    marker = [it for it in s.full_list if it.name == "이동지"]
    assert all(it.repeated for it in marker)
    assert any(it.intensity in ("high", "very_high") for it in marker)
    assert "이동지" in s.summary.repeated


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


def test_yeokma_is_relative_not_glyph_based() -> None:
    # 09:40(申亥亥巳: 모두 사생지) → '이동지' 표지는 네 자리 모두, 역마살은 상대 기준으로만.
    # 일지 亥(亥卯未국)의 역마 = 巳 → 시지 巳에 역마살 1건(근거에 기준 지지 명시).
    _r, s = _sinsal(birth_time="09:40")
    marker = {it.position for it in s.full_list if it.name == "이동지"}
    assert marker >= {"year", "month", "day", "hour"}
    yeokma = [it for it in s.full_list if it.name == "역마살"]
    assert [it.position for it in yeokma] == ["hour"]
    assert "일지 亥 기준 역마" in yeokma[0].basis and "亥卯未" in yeokma[0].basis
    assert not any(it.name in ("망신살", "지살", "겁살") for it in s.full_list)


def test_luck_yeokma_is_relative() -> None:
    # 운 지지도 같은 원칙: 寅 운은 연지 申(申子辰국) 기준 역마 → 역마살+이동지, 巳 운은 일지 亥
    # 기준 역마, 卯 운은 사생지가 아니라 둘 다 아님.
    from saju_manse_analysis.sinsal.sinsal_aggregator import sinsal_for_luck

    from saju_shared_types.enums import Branch as B
    from saju_shared_types.enums import Stem as S

    r, _s = _sinsal()
    assert r.pillars is not None
    names_in = {x.name for x in sinsal_for_luck(r.pillars, S.GAP, B.IN)}
    names_myo = {x.name for x in sinsal_for_luck(r.pillars, S.EUL, B.MYO)}
    assert {"역마살", "이동지"} <= names_in
    assert not {"역마살", "이동지"} & names_myo


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
