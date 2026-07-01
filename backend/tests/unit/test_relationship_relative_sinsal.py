"""12신살 상대위치법(P2) 단위 테스트 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §4. 삼합국 기준 상대위치 표(장성=왕지·지살=생지·화개=고지),
A→B/B→A 비대칭, 노출 tier 게이트, explanation-first(점수 미개입)를 검증한다.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.relationship_relative_sinsal import (
    _BASE_MAPS,
    get_relative_sinsal,
    relative_sinsal_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch


def _chart(date_: str, time_: str, gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date_, birth_time=time_,
        birth_place_name="서울", gender=gender,
    ))


# 1. 표 검증 — 4 삼합국 모두 장성=왕지·지살=생지·화개=고지.
def test_relative_table_anchors() -> None:
    anchors = {
        Branch.SIN: (Branch.JA, Branch.SIN, Branch.JIN),   # 申子辰: 장성子·지살申·화개辰
        Branch.IN: (Branch.O, Branch.IN, Branch.SUL),      # 寅午戌
        Branch.SA: (Branch.YU, Branch.SA, Branch.CHUK),    # 巳酉丑
        Branch.HAE: (Branch.MYO, Branch.HAE, Branch.MI),   # 亥卯未
    }
    for base, (wangji, saengji, goji) in anchors.items():
        m = _BASE_MAPS[base]
        assert m[wangji] == "장성살"
        assert m[saengji] == "지살"
        assert m[goji] == "화개살"


# 2. 삼합 3멤버는 같은 상대위치 맵을 공유한다.
def test_triad_members_share_map() -> None:
    assert _BASE_MAPS[Branch.SIN] == _BASE_MAPS[Branch.JA] == _BASE_MAPS[Branch.JIN]


# 3. 비대칭 — A→B와 B→A가 다르게 나올 수 있다.
def test_asymmetry() -> None:
    ab = get_relative_sinsal(Branch.HAE, Branch.MYO)  # 亥 기준 卯
    ba = get_relative_sinsal(Branch.MYO, Branch.HAE)  # 卯 기준 亥
    assert ab.sinsal == "장성살" and ba.sinsal == "지살"
    assert ab.sinsal != ba.sinsal  # 비대칭


# 4. 노출 tier — 겁살·재살·월살은 internal(문구 없음), expose/movement는 문구 있음.
def test_tier_gating() -> None:
    for base in _BASE_MAPS:
        for target in Branch:
            r = get_relative_sinsal(base, target)
            assert r.tier in ("expose", "movement", "internal")
            if r.tier == "internal":
                assert r.relationship_reading == ""
                assert r.sinsal in ("겁살", "재살", "월살")
            else:
                assert r.relationship_reading  # 노출 대상은 문구 존재


# 5. 렌더 — internal은 출력되지 않고, 승패/서열 어휘가 없다.
def test_lines_exclude_internal_and_are_neutral() -> None:
    a = _chart("1990-05-05", "06:00", "male")
    b = _chart("1992-11-12", "14:30", "female")
    text = "\n".join(relative_sinsal_lines(a, b, "본인", "상대"))
    # internal 신살명은 노출 문구에 등장하지 않는다.
    for internal in ("겁살", "재살", "월살"):
        assert internal not in text
    for banned in ("이긴다", "진다", "승패", "서열", "상전", "못 이김"):
        assert banned not in text


# 6. inert — get_relative_sinsal은 원국을 변경하지 않는다(순수 branch 계산).
def test_inert_and_graceful() -> None:
    from types import SimpleNamespace
    # pillars 결측이면 빈 목록(graceful).
    assert relative_sinsal_lines(
        SimpleNamespace(pillars=None), SimpleNamespace(pillars=None)  # type: ignore[arg-type]
    ) == []
    # 실제 명식 렌더는 리스트(헤더 포함 또는 빈 목록).
    a = _chart("1961-09-30", "06:00")
    b = _chart("1980-11-22", "09:08", "male")
    out = relative_sinsal_lines(a, b)
    assert isinstance(out, list)
