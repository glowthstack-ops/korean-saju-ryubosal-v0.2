"""지장간 잠복 십성 발현 층(2026-11-10, 데굴님 "제안대로 진행해 · 시작할 때 모두") — 서술 전용.

원국 천간(일간 제외)·지지 본기에 없고 중기·여기에만 있는 십성이 후보 기간 운에서 드러나는지
(투출 = 운 천간 같은 글자 / 자극 = 대운·세운 지지의 충·육합·삼합)를 엔진이 판정한다.
docs/05 `interpretations/hidden_latent_text.json` 절.
"""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

from saju_api.services import chat_service, report_service
from saju_api.services.manse_service import calculate
from saju_engines import context_reducer
from saju_engines.dictionaries import (
    HIDDEN_LATENT_TEXT_IDS,
    HiddenLatentTextFile,
    _lint_hidden_latent_text,
    lint_dictionaries,
)
from saju_engines.hidden_latent_activation import (
    BLOCK_HEADER,
    NATAL_LATENT_PERIOD_RULE,
    HiddenLatent,
    LuckUnit,
    domain_groups,
    hidden_latent_block,
    judge,
    luck_units,
    natal_hidden_latents,
    sewoon_year_of,
)
from saju_shared_types.birth_input import BirthInput

_DICT = Path(__file__).resolve().parents[2] / "dictionaries"
# 甲寅·丁丑·丁卯·甲辰 — 丁 일간, 재성(金)이 천간·본기에 없고 丑 중기 辛(편재)만(강의 예시형).
# 관성(水)도 丑 여기·辰 중기 癸(편관)만 있다.
_CASE_LATENT = BirthInput(
    birth_date=date(1975, 1, 21), birth_time="09:30:00", birth_place_name="서울", gender="male",
)
# 庚申·丁亥·己亥·戊辰 — 己 일간, 재성(水)은 亥 본기로 드러나 있다(잠복 아님). 관성(木)만 잠복.
_CASE_VISIBLE_WEALTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:08:00", birth_place_name="서울", gender="male",
)
_XIN = HiddenLatent(group="재성", stem="辛", ten_god="편재", hosts=(("month", "丑", "middle"),))


# ── 사전 ──────────────────────────────────────────────────────────────────────


def test_hidden_latent_dictionary_lint_clean() -> None:
    assert not [e for e in lint_dictionaries(_DICT) if "hidden_latent" in e]
    path = _DICT / "interpretations" / "hidden_latent_text.json"
    parsed = HiddenLatentTextFile.model_validate(json.loads(path.read_text("utf-8")))
    assert _lint_hidden_latent_text(parsed) == []
    assert sorted(it.id for it in parsed.items) == sorted(HIDDEN_LATENT_TEXT_IDS)


def test_hidden_latent_lint_rejects_assertive_text_and_missing_id() -> None:
    path = _DICT / "interpretations" / "hidden_latent_text.json"
    raw = json.loads(path.read_text("utf-8"))
    raw["items"][0]["text"] = "숨어 있던 재성이 드러나면 반드시 큰돈이 들어와 대박이 난다고 본다."
    errs = _lint_hidden_latent_text(HiddenLatentTextFile.model_validate(raw))
    assert any("반드시" in e for e in errs) and any("대박" in e for e in errs)
    raw["items"][1]["id"] = "group_unknown"
    errs = _lint_hidden_latent_text(HiddenLatentTextFile.model_validate(raw))
    assert any("id 집합" in e for e in errs)


# ── 원국 잠복 글자 ─────────────────────────────────────────────────────────────


def test_natal_latents_only_groups_absent_from_stems_and_main_qi() -> None:
    r = calculate(_CASE_LATENT)
    assert [p.ganji for p in (r.pillars.year, r.pillars.month, r.pillars.day, r.pillars.hour)] == [
        "甲寅", "丁丑", "丁卯", "甲辰",
    ]
    got = {(lt.group, lt.stem): lt for lt in natal_hidden_latents(r)}
    assert set(got) == {("재성", "辛"), ("관성", "癸")}
    assert got[("재성", "辛")].ten_god == "편재"
    assert got[("재성", "辛")].hosts == (("month", "丑", "middle"),)
    # 같은 글자가 두 지지에 있으면 한 항목으로 묶는다.
    assert got[("관성", "癸")].hosts == (("month", "丑", "residual"), ("hour", "辰", "middle"))


def test_visible_group_is_not_latent() -> None:
    """반례: 본기에 드러난 재성(亥 본기 壬)은 잠복이 아니다 — 재물 질문에 블록이 나오지 않는다."""
    r = calculate(_CASE_VISIBLE_WEALTH)
    assert "재성" not in {lt.group for lt in natal_hidden_latents(r)}
    assert hidden_latent_block(r, [("2027", "丁未"), ("2031", "辛亥")], "wealth") == []


def test_hour_unknown_chart_is_not_judged() -> None:
    """반례: 시주 미상이면 '표면에 없음'을 확정할 수 없다(미상 ≠ 없음) — 판정하지 않는다."""
    birth = _CASE_LATENT.model_copy(update={"birth_time": None, "birth_time_unknown": True})
    r = calculate(birth)
    assert r.pillars.hour is None
    assert natal_hidden_latents(r) == []
    assert hidden_latent_block(r, [("2031", "辛亥")], "wealth") == []


# ── 판정 ──────────────────────────────────────────────────────────────────────


def test_judge_grades() -> None:
    emerge = judge(_XIN, LuckUnit("sewoon", "2031", "辛亥"))
    assert emerge is not None and emerge.grade == "emerge" and emerge.stir is None
    stir = judge(_XIN, LuckUnit("sewoon", "2027", "丁未"))  # 丑未충
    assert stir is not None and stir.grade == "stir" and not stir.emerge
    assert stir.stir == "세운 지지 未–원국 丑 충"
    assert judge(_XIN, LuckUnit("sewoon", "2032", "壬子")).stir == "세운 지지 子–원국 丑 육합"
    assert judge(_XIN, LuckUnit("sewoon", "2029", "己酉")).stir == "세운 지지 酉–원국 丑 삼합"
    clear = judge(_XIN, LuckUnit("sewoon", "2041", "辛酉"))  # 투출 + 酉丑 삼합
    assert clear is not None and clear.grade == "clear"
    assert judge(_XIN, LuckUnit("daewoon", "2031~2040", "辛未")).grade == "clear"  # 대운도 둘 다
    # 반례: 미성립(다른 글자·건드리지 않는 지지), 같은 지지(복음)는 자극이 아니다.
    assert judge(_XIN, LuckUnit("sewoon", "2028", "戊申")) is None
    assert judge(_XIN, LuckUnit("sewoon", "2033", "癸丑")) is None
    # 반례: 같은 오행 다른 글자(庚)는 투출이 아니다.
    assert judge(_XIN, LuckUnit("sewoon", "2030", "庚戌")) is None


def test_monthly_branch_never_counts_as_stir() -> None:
    """월운은 투출만 본다 — 열두 지지가 해마다 지나가 자극이 항상 성립하기 때문(데굴님 승인)."""
    assert judge(_XIN, LuckUnit("wolwoon", "2026-07", "乙未")) is None  # 丑未충이지만 월운
    hit = judge(_XIN, LuckUnit("wolwoon", "2027-01", "辛丑"))
    assert hit is not None and hit.grade == "emerge" and hit.stir is None


def test_sewoon_year_of_january_belongs_to_previous_year() -> None:
    assert sewoon_year_of("2027") == 2027
    assert sewoon_year_of("2027-02") == 2027 and sewoon_year_of("2027-12") == 2027
    assert sewoon_year_of("2027-01") == 2026  # 丑월은 전년도 세운
    assert sewoon_year_of("") is None


def test_luck_units_add_year_pillar_for_month_candidates_once() -> None:
    r = calculate(_CASE_LATENT)
    units = luck_units(r, [("2027-01", "辛丑"), ("2027-03", "癸卯"), ("2027-04", "甲辰")])
    by_layer = {layer: [u for u in units if u.layer == layer] for layer in ("sewoon", "wolwoon")}
    assert [(u.label, u.ganji) for u in by_layer["sewoon"]] == [("2026", "丙午"), ("2027", "丁未")]
    assert [u.label for u in by_layer["wolwoon"]] == ["2027-01", "2027-03", "2027-04"]
    assert len([u for u in units if u.layer == "daewoon"]) >= 1


# ── 블록 ──────────────────────────────────────────────────────────────────────


def test_block_states_established_and_unestablished_periods() -> None:
    r = calculate(_CASE_LATENT)
    periods = [("2027", "丁未"), ("2028", "戊申"), ("2031", "辛亥")]
    block = hidden_latent_block(r, periods, "wealth")
    assert block[0] == BLOCK_HEADER
    line = next(ln for ln in block if ln.startswith("- 재성"))
    assert "丑(월지) 중기 辛(편재)" in line
    assert "2031 辛亥 = 세운 천간 辛 투출 → 성립" in line
    assert "2027 丁未 = 세운 지지 未–원국 丑 충 → 약함(참고)" in line
    assert "그 밖의 후보 기간 = 미성립" in line and "2028" not in line
    assert "수입·거래·실리" in line
    assert not any(ln.startswith("- 관성") for ln in block)  # 재물 질문 — 재성·비겁만
    assert block[-1].startswith("사용 규칙:") and "용신·기신" in block[-1]
    legend = next(ln for ln in block if ln.startswith("읽는 법:"))
    assert "성립 =" in legend and "약함(참고) =" in legend


def test_block_omitted_when_nothing_matches_and_lists_unmatched_glyph_otherwise() -> None:
    r = calculate(_CASE_LATENT)
    dw = [u.ganji for u in luck_units(r, [("2028", "戊申")]) if u.layer == "daewoon"]
    # 2028 戊申: 辛 투출 아님·申–丑 무관. 대운 배경도 걸리지 않으면 블록 자체가 없다.
    if all(judge(_XIN, LuckUnit("daewoon", "-", g)) is None for g in dw):
        assert hidden_latent_block(r, [("2028", "戊申")], "wealth") == []
    # 한 글자(재성 辛)만 걸리는 기간(2031 辛亥: 亥–丑·亥–辰 무관)에서는 걸리지 않은 글자(관성 癸)도
    # '전부 미성립'으로 함께 적는다 — 대운 배경이 관성에 걸리는 경우는 제외.
    block = hidden_latent_block(r, [("2031", "辛亥")], None)
    officer = next(ln for ln in block if ln.startswith("- 관성"))
    if "대운" not in officer:
        assert "후보 기간 전부 미성립" in officer


def test_domain_selects_groups() -> None:
    r = calculate(_CASE_LATENT)
    periods = [("2027", "丁未"), ("2031", "辛亥")]
    assert domain_groups(r, None) == ("재성", "관성", "인성", "식상", "비겁")
    assert domain_groups(r, "general") == domain_groups(r, None)
    assert domain_groups(r, "wealth") == ("재성", "비겁")
    assert domain_groups(r, "career") == ("관성", "식상")
    assert domain_groups(r, "education") == ("인성", "식상")
    assert domain_groups(r, "relationship") == ("재성", "비겁")  # 남성 — 배우자성 재성이 앞
    assert domain_groups(r, "relocation") is None and domain_groups(r, "health") is None
    # 총운형: 두 군 모두, 재성이 앞.
    general = [ln for ln in hidden_latent_block(r, periods, None) if ln.startswith("- ")]
    assert [ln.split(" — ")[0] for ln in general] == ["- 재성", "- 관성"]
    career = [ln for ln in hidden_latent_block(r, periods, "career") if ln.startswith("- ")]
    assert [ln.split(" — ")[0] for ln in career] == ["- 관성"]
    # 관계 질문(남성): 재성 줄이 배우자성 문구로 바뀐다.
    rel_block = hidden_latent_block(r, periods, "relationship")
    rel = next(ln for ln in rel_block if ln.startswith("- 재성"))
    assert "배우자성" in rel and "수입·거래" not in rel
    # 반례: 이사·건강 질문, 후보 기간 없음 → 블록 없음.
    assert hidden_latent_block(r, periods, "relocation") == []
    assert hidden_latent_block(r, periods, "health") == []
    assert hidden_latent_block(r, [], "wealth") == []


def test_female_partner_star_is_officer() -> None:
    r = calculate(_CASE_LATENT.model_copy(update={"gender": "female"}))
    assert domain_groups(r, "relationship") == ("관성", "비겁")
    rel = next(
        ln for ln in hidden_latent_block(r, [("2033", "癸丑")], "relationship")
        if ln.startswith("- 관성")
    )
    assert "배우자성" in rel and "2033 癸丑 = 세운 천간 癸 투출" in rel


# ── 배선 ──────────────────────────────────────────────────────────────────────


def test_natal_latent_line_forbids_inventing_periods() -> None:
    """원국 잠재 신호 줄에 '기간은 엔진 블록만' 꼬리가 붙는다(일반 조건문의 시기 합성 방지)."""
    assert "블록에 적힌 기간만" in NATAL_LATENT_PERIOD_RULE
    src = inspect.getsource(context_reducer)
    assert src.count("NATAL_LATENT_PERIOD_RULE") >= 2  # import + 잠재 신호 줄


def test_block_is_wired_to_chat_trailing_and_report_lecture_block() -> None:
    """채팅 말미와 테마 리포트 강의 블록 두 곳에 같이 배선한다(한 곳만 배선한 전례 방지)."""
    assert "hidden_latent_block(" in inspect.getsource(chat_service)
    assert "hidden_latent_block(" in inspect.getsource(report_service._ReportData.lecture_block)
