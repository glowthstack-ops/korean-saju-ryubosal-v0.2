"""원국 구조 × 운에서 온 글자 — 구조 태그·층 읽기·서술 블록 검증 (2026-11-18).

데굴님 "같은 십성이라도 개인별로 역할이 다를 수 있어 … 원국의 구조는 이러한데 운에서 이런 십성들이
옴으로 인해서 이런식의 결과가 나타난다 같은 식". 운 글자를 십성 이름이 아니라 그 명식에서의 역할·
원국 대비 위치·운에서 서는 구조로 옮기는 층(`luck_structure_tags`)과, 그 층을 채팅 말미에 싣는
블록을 지킨다. 서술·측정 전용이라 점수·판정은 바꾸지 않는다.
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

import pytest

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines import luck_structure_tags as T
from saju_engines import period_v2_config
from saju_engines.pattern_transit import LuckGlyph, daewoon_ganji_by_year
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput

# 己 일간 신약·정재격 — 재성 과다(재다신약·득비이재), 관성은 드러난 글자 없음, 비겁 용신.
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울", gender="male",
)
_UNKNOWN_HOUR = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=None, birth_time_unknown=True,
    birth_place_name="서울", gender="male",
)


@pytest.fixture(scope="module")
def chart():
    return calculate(_BIRTH)


@pytest.fixture(scope="module")
def natal(chart):
    return detect_structure_patterns(chart)


@pytest.fixture(scope="module")
def profile(chart, natal):
    p = T.natal_structure_profile(chart, natal)
    assert p is not None
    return p


def _rows(labels):
    return [SimpleNamespace(period=lb) for lb in labels]


def test_profile_reads_natal_structure_from_engine(profile) -> None:
    assert profile.day_master == "己" and profile.band == "신약"
    assert profile.excess_groups == frozenset({"wealth"})      # 재성 과다
    assert profile.absent_groups == frozenset({"officer"})     # 관성은 드러난 글자 없음
    assert profile.group_role == {
        "peer": "용신", "resource": "희신", "officer": "기신", "wealth": "구신", "output": "한신",
    }
    assert {"재다신약", "득비이재"} <= set(profile.core_pattern_names)
    assert abs(sum(profile.group_share.values()) - 100.0) < 1.0


def test_same_ten_god_reads_differently_by_chart(chart, natal, profile) -> None:
    """같은 겁재 세운(戊戌)이라도 역할은 명식이 정한다 — 이 명식에서는 용신이고 부담 구조를 푼다."""
    dw = LuckGlyph("daewoon", "辛", "卯")
    peer_year = T.read_luck_layer(chart, profile, natal, [dw, LuckGlyph("year", "戊", "戌")])
    assert peer_year is not None
    assert (peer_year.stem_god, peer_year.stem_role) == ("겁재", "용신")
    assert {T.TAG_YONG_GROUP, T.TAG_FAV_ALL, T.TAG_BURDEN_DOWN} <= set(peer_year.tags)
    assert ("재다신약", "burden", "weakened") in peer_year.changes
    # 반례: 재성·관성 세운(壬寅)은 과다 군을 더하고 없는 군을 채우며 두 글자 모두 기·구신이다.
    wealth_year = T.read_luck_layer(chart, profile, natal, [dw, LuckGlyph("year", "壬", "寅")])
    assert wealth_year is not None
    assert {T.TAG_EXCESS_ADD, T.TAG_ABSENT_SUPPLY, T.TAG_UNFAV_ALL} <= set(wealth_year.tags)
    assert T.TAG_YONG_GROUP not in wealth_year.tags
    # 다른 명식(비겁 과다 신강)에서는 같은 겁재 글자가 용신 군이 아니다.
    strong = calculate(BirthInput(
        birth_date=date(1984, 2, 10), birth_time=time(6, 0), birth_place_name="서울", gender="male",
    ))
    sp = T.natal_structure_profile(strong, detect_structure_patterns(strong))
    assert sp is not None
    assert sp.day_master != profile.day_master or sp.group_role != profile.group_role


def test_month_layer_reads_on_top_of_year_and_daewoon(chart, natal, profile) -> None:
    stack = [LuckGlyph("daewoon", "辛", "卯"), LuckGlyph("year", "壬", "寅"),
             LuckGlyph("month", "辛", "亥")]
    month = T.read_luck_layer(chart, profile, natal, stack)
    assert month is not None
    assert T.TAG_MB_ECHO in month.tags and T.TAG_EXCESS_ADD in month.tags  # 亥 = 원국 월지·재성
    assert T.luck_structure_tags(chart, profile, natal, stack) == list(month.tags)
    assert T.read_luck_layer(chart, profile, natal, []) is None


def _lines(chart, natal, labels, month_ganji=None):
    lc = chart.luck_cycles
    sewoon = {int(p.label[:4]): p.ganji for d in lc.daewoon_table for p in d.sewoon}
    return T.natal_luck_role_lines(
        chart, natal, daewoon_by_year=daewoon_ganji_by_year(chart), sewoon_by_year=sewoon,
        month_ganji=month_ganji or {}, labels=labels,
    )


def test_block_orders_layers_and_states_what_the_glyph_did(chart, natal) -> None:
    lines = _lines(chart, natal, ["2026-11"], {"2026-11": "己亥"})
    assert lines[0].startswith("[원국 구조 × 운에서 온 글자 — 2026-11, 엔진 판정] ")
    assert T.NATAL_LUCK_ROLE_DIRECTIVE in lines[0]
    assert lines[1].startswith("원국: 신약 · 세력 — ")
    assert "재성 33%(과다)" in lines[1] and "관성 9%(드러난 글자 없음)" in lines[1]
    assert "비겁=용신" in lines[1] and "재다신약" in lines[1]
    assert [ln.split(" ")[0] for ln in lines[2:]] == ["대운", "세운", "월운"]  # 위 층부터
    assert lines[2].startswith("대운 壬辰: 천간 정재(구신)·지지 겁재(용신) — ")
    assert "원국에 이미 많은 재성이 더해짐" in lines[2]
    assert lines[3].startswith("세운 丙午 2026년: 천간 정인(희신)·지지 편인(희신) — ")
    assert lines[4].startswith("월운 2026-11 己亥: 천간 비견(용신)·지지 정재(구신) — ")
    assert "원국 월지와 같은 글자" in lines[4]
    # 지어낸 십성·한자 밖 표기 없음 — 줄의 간지는 넘겨준 운 글자뿐이다.
    assert all("을(를)" not in ln for ln in lines)


def test_block_caps_drop_whole_layer_not_part(chart, natal) -> None:
    months = ["2026-11", "2026-12", "2027-01", "2027-02"]
    ganji = {"2026-11": "己亥", "2026-12": "庚子", "2027-01": "辛丑", "2027-02": "壬寅"}
    lines = _lines(chart, natal, months, ganji)
    assert not any(ln.startswith("월운 ") for ln in lines)  # 4달 > 상한 3 → 달 줄 전부 생략
    assert sum(ln.startswith("세운 ") for ln in lines) == 2  # 2026·2027(2027-02 는 2027년 절기)
    many_years = [str(y) for y in range(2026, 2034)]
    lines = _lines(chart, natal, many_years)
    assert not any(ln.startswith("세운 ") for ln in lines)  # 8해 > 상한 6 → 세운 줄 전부 생략
    assert sum(ln.startswith("대운 ") for ln in lines) == 1  # 판(대운)은 남는다
    six = _lines(chart, natal, [str(y) for y in range(2026, 2032)])
    assert sum(ln.startswith("세운 ") for ln in six) == 6
    assert _lines(chart, natal, []) == []


def test_block_is_empty_without_hour_pillar() -> None:
    """시주 미상이면 역할을 말하지 않는다(불완전 정보 비확정 정책)."""
    unknown = calculate(_UNKNOWN_HOUR)
    assert _lines(unknown, detect_structure_patterns(unknown), ["2026"]) == []


def test_chat_block_carries_role_lines_for_timed_questions_only(monkeypatch) -> None:
    window = chat_service._window_structure_block(
        _BIRTH, _rows(["2026-11", "2026-12", "2027-01"]), "취업운 정리해줘",
    )
    assert window is not None and "[원국 구조 × 운에서 온 글자 — 2026-11–2027-01" in window
    assert "월운 2026-11 己亥: 천간 비견(용신)" in window
    assert window.startswith("[운에서 서는 구조")  # 기존 블록 뒤에 붙는다
    single = chat_service._window_structure_block(
        _BIRTH, [], "2030년 재물운", SimpleNamespace(start="2030", end="2030"),
    )
    assert single is not None and "세운 庚戌 2030년: " in single
    # 반례: 시점 없는 질문에는 올해를 끌어와 싣지 않는다.
    timeless = chat_service._window_structure_block(
        _BIRTH, [], "내 성격은 어때?", None, date(2026, 11, 18),
    )
    assert timeless is None or "[원국 구조 × 운에서 온 글자" not in timeless
    # 끄면 실리지 않는다.
    monkeypatch.setattr(period_v2_config, "NATAL_LUCK_ROLE_BLOCK_ENABLED", False)
    off = chat_service._window_structure_block(
        _BIRTH, _rows(["2026-11", "2026-12", "2027-01"]), "취업운 정리해줘",
    )
    assert off is not None and "[원국 구조 × 운에서 온 글자" not in off
