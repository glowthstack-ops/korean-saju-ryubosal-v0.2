"""반복 구조 판정(2026-10-27) — 설계안 11절 통과 기준 + 원국 세력 불변 + 배선.

판정은 같은 글자 여부만, 구조 강도는 설명용 가설값, 운 유입은 기간 활성화(새 사건 아님).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.repetition_structure import (
    activation_line,
    detect_repetition_groups,
    group_line,
    repetition_activations,
)
from saju_shared_types.birth_input import BirthInput

_FIXTURE = Path(__file__).parent / "fixtures" / "entry_slots_birth_19801122.json"


def _pil(stem: str, branch: str) -> SimpleNamespace:
    return SimpleNamespace(stem=stem, branch=branch)


def _result(ganjis: list[str], dm_index: int = 2, daewoon=None, yearly=None) -> SimpleNamespace:
    """원국 4기둥(연·월·일·시)만 가진 최소 결과 — 판정기는 pillars·luck_cycles 만 읽는다."""
    pils = [_pil(g[0], g[1]) for g in ganjis]
    pillars = SimpleNamespace(
        year=pils[0], month=pils[1], day=pils[2], hour=pils[3] if len(pils) > 3 else None,
        day_master=ganjis[dm_index][0],
    )
    lc = None
    if daewoon is not None or yearly is not None:
        lc = SimpleNamespace(daewoon_table=daewoon or [], yearly_luck=yearly or [])
    return SimpleNamespace(pillars=pillars, luck_cycles=lc)


@pytest.mark.parametrize("ch", ["子", "丑", "寅", "巳"])
def test_branch_repetition_without_self_punishment(ch: str) -> None:
    g = detect_repetition_groups(_result(["甲" + ch, "丙" + ch, "戊辰", "庚申"]))
    br = [x for x in g if x.kind == "branch"]
    assert [(x.char, x.is_self_punishment) for x in br] == [(ch, False)]


@pytest.mark.parametrize("ch", ["辰", "午", "酉", "亥"])
def test_self_punishment_four_kinds(ch: str) -> None:
    g = detect_repetition_groups(_result(["甲子", "丙" + ch, "戊" + ch, "庚寅"]))
    br = next(x for x in g if x.kind == "branch")
    assert br.char == ch and br.is_self_punishment and br.adjacent


def test_stem_repetition_is_not_punishment() -> None:
    g = detect_repetition_groups(_result(["甲子", "己丑", "己卯", "辛巳"]))
    assert [(x.kind, x.char, x.is_self_punishment) for x in g] == [("stem", "己", False)]


def test_hidden_stems_are_not_counted() -> None:
    # 亥 지장간 壬·甲, 寅 지장간 甲 — 천간 壬·甲 과 같은 글자 반복으로 보지 않는다.
    g = detect_repetition_groups(_result(["壬亥", "甲寅", "丙午", "庚申"]))
    assert g == []


def test_three_and_four_same_branch_one_group() -> None:
    g3 = next(x for x in detect_repetition_groups(_result(["甲亥", "乙亥", "丙亥", "丁卯"]))
              if x.kind == "branch")
    assert g3.count == 3 and len(g3.pairs) == 3 and g3.structural_strength == pytest.approx(1.10)
    g4 = next(x for x in detect_repetition_groups(_result(["甲亥", "乙亥", "丙亥", "丁亥"]))
              if x.kind == "branch")
    assert g4.count == 4 and len(g4.pairs) == 6 and g4.structural_strength == pytest.approx(1.20)


def test_distance_weights_non_adjacent() -> None:
    g = next(x for x in detect_repetition_groups(_result(["甲午", "乙卯", "丙辰", "丁午"]))
             if x.kind == "branch")
    assert not g.adjacent and g.pairs[0].distance == 3 and g.pairs[0].weight == 0.5
    assert g.structural_strength == 0.5
    g2 = next(x for x in detect_repetition_groups(_result(["甲午", "乙卯", "丙午", "丁辰"]))
              if x.kind == "branch")
    assert g2.structural_strength == 0.7


def test_same_pillar_recorded_separately() -> None:
    g = detect_repetition_groups(_result(["甲子", "己巳", "戊辰", "己巳"]))
    kinds = {(x.kind, x.char) for x in g}
    assert ("pillar", "己巳") in kinds and ("stem", "己") in kinds and ("branch", "巳") in kinds


def test_luck_same_char_activates_existing_group() -> None:
    r = _result(["庚申", "丁亥", "己亥", "己巳"])
    acts = repetition_activations(r, "year", "2031", "辛亥")
    assert [a.kind for a in acts] == ["natal_group_active"]
    assert acts[0].natal_positions == ["month", "day"] and acts[0].is_self_punishment


def test_luck_clash_on_group_is_one_activation() -> None:
    r = _result(["庚申", "丁亥", "己亥", "己巳"])
    acts = repetition_activations(r, "year", "2025", "乙巳")
    clash = [a for a in acts if a.kind == "clash_group"]
    assert len(clash) == 1 and clash[0].natal_positions == ["month", "day"]
    assert "충 활성화 그룹 1건" in activation_line(clash[0])


def test_period_new_self_punishment_only_for_self_chars() -> None:
    r = _result(["甲子", "丙亥", "戊辰", "庚寅"])
    assert [a.kind for a in repetition_activations(r, "year", "2031", "辛亥")] == ["period_new"]
    # 反例: 자형 글자가 아닌 지지(子) 1개 + 운 子 는 기록하지 않는다(노이즈 억제).
    assert repetition_activations(r, "year", "2032", "壬子") == []


def test_luck_luck_repetition_without_natal_char() -> None:
    dw = [SimpleNamespace(
        stem="癸", branch="亥", approx_start_date=date(2030, 1, 1),
        approx_end_date=date(2039, 12, 31),
    )]
    r = _result(["甲子", "丙寅", "戊辰", "庚申"], daewoon=dw)
    acts = repetition_activations(r, "year", "2031", "辛亥")
    assert [(a.kind, a.luck_layers, a.is_self_punishment) for a in acts] == [
        ("luck_luck", ["daewoon"], True),
    ]


def test_no_fortune_word_in_group_line() -> None:
    r = _result(["庚申", "丁亥", "己亥", "己巳"])
    for g in detect_repetition_groups(r, {"水": "희신"}):
        line = group_line(g)
        assert "흉" not in line and "사건" not in line


def test_natal_force_unchanged_and_excerpts_wired() -> None:
    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    r = calculate(birth.model_copy(update={"reference_date": date(2026, 10, 27)}))
    before = r.force_analysis.model_dump()
    ci = build_chart_interpretation(r)
    assert r.force_analysis.model_dump() == before  # 반복 판정이 세력 계산을 건드리지 않는다
    assert ci is not None
    reps = [e for e in ci.excerpts if e.kind == "repetition"]
    assert [e.key for e in reps] == ["반복 구조 己", "반복 구조 亥"]
    assert "자형(亥亥)" in reps[1].text and "정재 반복" in reps[1].text
    assert "사건(이직·이별·손실 등)을 말하지 말 것" in reps[0].text  # 원칙은 첫 줄에 1회


def test_candidate_repetition_note_once_per_period() -> None:
    from saju_api.services import chat_service

    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    res = chat_service.chat(birth, "2027년 5월 이직운 어때?", date(2026, 10, 27), True)
    assert res.prompt_preview is not None
    p = res.prompt_preview
    # 같은 달 후보가 여럿이어도 반복 구조 줄은 한 번만(기간 하나의 사실).
    assert p.count("반복 구조(새 사건 아님): 월운 巳 유입") == 1
    assert "충 활성화 그룹 1건(관계 쌍 2개" in p


@pytest.mark.parametrize(("flag", "n_hits", "n_refs"), [(True, 1, 2), (False, 2, 4)])
def test_relation_hit_dedup_flag(
    monkeypatch: pytest.MonkeyPatch, flag: bool, n_hits: int, n_refs: int,
) -> None:
    # 원국 亥 2개 + 운 巳 — 만세력 엔진은 '충:巳-亥' 를 자리마다 한 번씩(×2) 낸다.
    from saju_engines import ganji_calendar, period_v2_config

    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    r = calculate(birth.model_copy(update={"reference_date": date(2026, 10, 27)}))
    monkeypatch.setattr(period_v2_config, "RELATION_HIT_DEDUP_ENABLED", flag)
    hits = ganji_calendar.relation_hits(
        "year", "乙", "巳", ["충:巳-亥", "충:巳-亥"], [], r.pillars,
    )
    assert len(hits) == n_hits
    assert sum(len(h.natal_refs) for h in hits) == n_refs  # 켜면 월지·일지 2자리, 끄면 4(중복)
