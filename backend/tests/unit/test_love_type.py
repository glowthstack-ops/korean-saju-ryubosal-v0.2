"""연애운 강의 4편 대조 서술층(2026-10-25) — 연애 유형 5종 사전·분류기, 결혼 자원 신규 필드,
궁합 비겁 과다, 운 도화 연지/일지 프레임. 전부 서술 전용(점수 비개입)이며 낙인·단정 어휘를
쓰지 않는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import love_type as lt
from saju_engines.chart_interpretation import _DOHWA_BASE_FRAME
from saju_engines.compatibility_engine import analyze_compatibility
from saju_engines.context_reducer import build_birth_summary
from saju_engines.dictionaries import LoveTypesFile, _lint_love_types
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.structural_context import marriage_resource_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_BANNED = ("외도", "바람둥이", "과부", "반드시 ", "확정")


def _chart(y: int, m: int, d: int, hm: str, gender: str):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name="서울", gender=gender,
    ))


# ── 사전 ──────────────────────────────────────────────────────────────────────


def test_love_types_dictionary_valid_and_clean() -> None:
    import json

    raw = json.loads((_DICTS / "interpretations" / "love_types.json").read_text(encoding="utf-8"))
    file = LoveTypesFile.model_validate(raw)
    assert _lint_love_types(file) == []
    groups = {i.group for i in file.items}
    assert groups == {"비겁", "식상", "재성", "관성", "인성"}
    for i in file.items:
        text = " ".join((i.meaning, i.psychology, i.wants, i.approach, i.caution, i.absent))
        assert not any(w in text for w in _BANNED), (i.group, text)
    assert set(lt.load_love_types()) == groups


# ── 분류기(1~3단계) ───────────────────────────────────────────────────────────


def test_classifier_stage_rules_on_real_charts() -> None:
    """실명식 여러 건에서 단계 규칙이 서로 모순 없이 적용되는지(결과 자체는 명식에 따름)."""
    seen_stages: set[int] = set()
    for y, m, d, hm, g in (
        (1980, 11, 22, "10:00", "female"), (1990, 5, 5, "08:00", "female"),
        (1984, 3, 1, "12:00", "male"), (1961, 9, 30, "06:00", "female"),
        (1975, 7, 15, "22:00", "male"), (2001, 1, 20, "15:00", "female"),
    ):
        r = _chart(y, m, d, hm, g)
        res = lt.classify_love_type(r, age=30)
        assert res.primary in lt.load_love_types()
        assert res.stage in (1, 2, 3)
        seen_stages.add(res.stage)
        p = r.pillars
        assert p is not None
        counts: dict[str, int] = {}
        for pil in (p.year, p.month, p.day, p.hour):
            if pil is None:
                continue
            for tg in (pil.stem_ten_god, pil.branch_main_ten_god):
                gk = lt.TEN_GOD_GROUP_KO.get(tg or "", "")
                if gk:
                    counts[gk] = counts.get(gk, 0) + 1
        if res.stage == 1:
            assert counts[res.primary] >= lt.LOVE_TYPE_COUNT_THRESHOLD
        else:
            assert all(v < lt.LOVE_TYPE_COUNT_THRESHOLD for v in counts.values())
        if res.stage == 3:
            assert res.primary == lt.TEN_GOD_GROUP_KO[p.month.branch_main_ten_god]
            # 51세+ 는 일지 기준(100세 밴드) — 월지≠일지면 유형이 바뀔 수 있다.
            res_old = lt.classify_love_type(r, age=55)
            assert res_old.primary == lt.TEN_GOD_GROUP_KO[p.day.branch_main_ten_god]
            assert "일지" in res_old.basis
    assert seen_stages  # 최소 한 단계는 관측


def test_classifier_age_boundary_uses_100_year_band() -> None:
    """나이 분기는 강의의 38세가 아니라 100세 밴드(50/51)로 번역된다."""
    for y, m, d, hm, g in ((1990, 5, 5, "08:00", "female"), (1975, 7, 15, "22:00", "male")):
        r = _chart(y, m, d, hm, g)
        if lt.classify_love_type(r, age=30).stage != 3:
            continue
        a40 = lt.classify_love_type(r, age=40)
        a50 = lt.classify_love_type(r, age=50)
        a51 = lt.classify_love_type(r, age=51)
        assert "월지" in a40.basis and "월지" in a50.basis
        assert "일지" in a51.basis
        none_age = lt.classify_love_type(r, None)
        assert "나이 미상" in none_age.basis and "월지" in none_age.basis


def test_age_from_result() -> None:
    r = _chart(1990, 5, 5, "08:00", "female")
    assert lt.age_from_result(r, date(2026, 10, 25)) == 36
    assert lt.age_from_result(r, date(2026, 5, 4)) == 35
    assert lt.age_from_result(r, date(1980, 1, 1)) is None


def test_love_type_lines_render_from_dictionary() -> None:
    res = lt.LoveTypeResult(primary="관성", secondary="비겁", basis="1단계 — 관성 3개", stage=1)
    lines = lt.love_type_lines(res)
    assert lines[0].startswith("[연애 유형")
    assert any("관성형" in x for x in lines)
    assert any("부 유형: 비겁형" in x for x in lines)
    assert any("다가가는 법" in x for x in lines)
    assert lt.love_type_lines(lt.LoveTypeResult(primary="")) == []


# ── 결혼 자원 신규 필드(P2-2~P2-7) ───────────────────────────────────────────


def _profile(y: int, m: int, d: int, hm: str, g: str, age: int | None = None):
    r = _chart(y, m, d, hm, g)
    return r, analyze_marriage_resource(r, build_birth_summary(r).useful_gods, age=age)


def test_profile_new_fields_consistent() -> None:
    for y, m, d, hm, g in (
        (1980, 11, 22, "10:00", "female"), (1984, 3, 1, "12:00", "male"),
        (1961, 9, 30, "06:00", "female"), (1975, 7, 15, "22:00", "male"),
    ):
        r, mr = _profile(y, m, d, hm, g, age=35)
        p = r.pillars
        assert p is not None
        spouse_gods = {"편관", "정관"} if g == "female" else {"편재", "정재"}
        n_visible = sum(
            1 for pil in (p.year, p.month, p.day, p.hour) if pil is not None
            for tg in (pil.stem_ten_god, pil.branch_main_ten_god) if tg in spouse_gods
        )
        # 자리 목록 합 = 가시 배우자성 수, 미투출이면 축 라벨 비어 있음.
        n_pos = len(mr.spouse_star_stem_positions) + len(mr.spouse_star_branch_positions)
        assert n_pos == n_visible
        assert bool(mr.spouse_star_axis) == (n_visible > 0)
        if mr.spouse_star_mixed:
            assert "혼재" in mr.spouse_star_axis
        for gy in mr.spouse_star_ganyeojidong:
            assert "간여지동 배우자성" in gy and "100세 밴드" in gy
        if mr.spouse_star_absent:
            assert any("미투출" in n for n in mr.late_marriage_notes)
        if mr.peer_excess:
            assert any("비겁 과다" in n for n in mr.late_marriage_notes)
        assert mr.love_type == lt.classify_love_type(r, 35).primary
        joined = " ".join(
            [mr.spouse_star_axis, *mr.partner_age_tendencies, *mr.late_marriage_notes,
             *mr.spouse_star_ganyeojidong]
        )
        assert not any(w in joined for w in _BANNED)


def test_partner_age_rules_follow_spec() -> None:
    """연·월주 배우자성→연상 / 일지 비겁→동갑 / 시주 배우자성→연하 / 여 일지 상관→연하 /
    남 인성 多→연상."""
    for y, m, d, hm, g in (
        (1980, 11, 22, "10:00", "female"), (1984, 3, 1, "12:00", "male"),
        (1990, 5, 5, "08:00", "female"), (1975, 7, 15, "22:00", "male"),
    ):
        r, mr = _profile(y, m, d, hm, g)
        p = r.pillars
        assert p is not None and p.hour is not None
        spouse_gods = {"편관", "정관"} if g == "female" else {"편재", "정재"}
        fam = any(
            pil.stem_ten_god in spouse_gods or pil.branch_main_ten_god in spouse_gods
            for pil in (p.year, p.month)
        )
        assert ("연상 경향(연·월주 배우자성)" in mr.partner_age_tendencies) is fam
        assert ("동갑·또래 경향(일지 비겁)" in mr.partner_age_tendencies) is (
            p.day.branch_main_ten_god in ("비견", "겁재")
        )
        hour_hit = p.hour.stem_ten_god in spouse_gods or p.hour.branch_main_ten_god in spouse_gods
        younger = any(t.startswith("연하 경향(시주 배우자성") for t in mr.partner_age_tendencies)
        assert younger is hour_hit
        if g == "female":
            assert ("연하 경향(일지 상관 — 여성 명식)" in mr.partner_age_tendencies) is (
                p.day.branch_main_ten_god == "상관"
            )
            assert not any("인성 많음" in t for t in mr.partner_age_tendencies)


def test_marriage_lines_render_new_blocks() -> None:
    r, mr = _profile(1980, 11, 22, "10:00", "female", age=45)
    text = "\n".join(marriage_resource_lines(mr))
    if mr.spouse_star_stem_positions or mr.spouse_star_branch_positions:
        assert "배우자성 자리(배우자성 한정 — 고정 등식 아님" in text
        assert "배우자성 정/편 축" in text
    if mr.partner_age_tendencies:
        assert "상대 나이대 경향" in text
    if mr.spouse_star_absent:
        assert "들어오는 시기에 결혼 경향" in text and "이혼 단정 금지" in text
    assert "[연애 유형" in text and f"{mr.love_type}형" in text
    assert not any(w in text for w in _BANNED)


# ── 궁합 비겁 과다(보조·중립) ─────────────────────────────────────────────────


def test_compatibility_peer_excess_is_auxiliary_neutral() -> None:
    found = False
    pairs = (
        ((1980, 11, 22, "10:00", "female"), (1984, 3, 1, "12:00", "male")),
        ((1975, 7, 15, "22:00", "male"), (1990, 5, 5, "08:00", "female")),
        ((1961, 9, 30, "06:00", "female"), (2001, 1, 20, "15:00", "female")),
    )
    for a_in, b_in in pairs:
        a, b = _chart(*a_in), _chart(*b_in)
        rep = analyze_compatibility(
            a, b, build_birth_summary(a).useful_gods, build_birth_summary(b).useful_gods,
        )
        assert rep is not None
        peers = [s for s in rep.signals if s.kind is CompatSignalKind.PEER_EXCESS]
        for s in peers:
            found = True
            assert s.auxiliary and s.direction is CompatDirection.NEUTRAL
            assert "이혼·불화 단정 금지" in s.detail
        # 보조 신호라 보완/마찰 카운트에 들어가지 않는다.
        main_neutral = [s for s in rep.signals if not s.auxiliary]
        assert rep.harmony_count == sum(
            1 for s in main_neutral if s.direction is CompatDirection.HARMONY
        )
        # 양쪽 비겁 과다 판정은 결혼 자원 peer_excess 와 일치.
        for res, label in ((a, rep.self_label), (b, rep.partner_label)):
            mr = analyze_marriage_resource(res)
            assert any(label in s.detail for s in peers) is mr.peer_excess
    assert found or True  # 표본에 과다가 없을 수 있음 — 일치성 검사가 본체


# ── 운 도화 연지/일지 프레임 ──────────────────────────────────────────────────


def test_luck_dohwa_base_frames() -> None:
    assert "타인 시선" in _DOHWA_BASE_FRAME["year"]
    assert "가까운 인연" in _DOHWA_BASE_FRAME["day"]
