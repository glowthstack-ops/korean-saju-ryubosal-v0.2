"""출입구 제2기준(간지론 — 연지 삼합 '앞 그룹' 왕지 방위, 2026-10-16 데굴님 승인) 회귀.

사업자 전용 별도 층: 목적 'sales'(출입구)에만 붙고, 12신살 picks·cautions 와 합산하지 않으며
학파별로 병기한다. 쥐띠(申子辰)에 교재는 동(亥卯未 왕지 卯), 우리 12신살 기준은 서(지살 申)를
권하므로 두 기준이 다른 방위를 내는 것이 정상이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.dictionaries import _lint_sinsal_direction
from saju_engines.sinsal_direction import (
    build_direction_profile,
    load_sinsal_direction_dict,
    recommend_for_purpose,
)
from saju_shared_types.enums import Branch
from saju_shared_types.sinsal_direction import DirectionPurpose, SinsalDirectionDict

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def test_dictionary_section_valid_and_linted():
    data = json.loads((_DICTS / "sinsal_direction.json").read_text("utf-8"))
    parsed = SinsalDirectionDict.model_validate(data)
    assert _lint_sinsal_direction(parsed) == []
    ecg = parsed.entrance_customer_group
    assert ecg is not None and ecg.school_label == "간지론"
    assert ecg.applies_to_purposes == [DirectionPurpose("sales")]
    assert set(ecg.table) == {"申子辰", "寅午戌", "巳酉丑", "亥卯未"}


@pytest.mark.parametrize(
    ("year_branch", "group", "king", "direction"),
    [
        (Branch("子"), "亥卯未", "卯", "동"),   # 쥐띠 — 교재 예시
        (Branch("午"), "巳酉丑", "酉", "서"),
        (Branch("酉"), "申子辰", "子", "북"),
        (Branch("卯"), "寅午戌", "午", "남"),
    ],
)
def test_second_basis_table_by_trine_group(year_branch, group, king, direction):
    dic = load_sinsal_direction_dict()
    profile = build_direction_profile(year_branch, dic)
    rec = recommend_for_purpose(profile, DirectionPurpose("sales"), dic)
    sb = rec.second_basis
    assert sb is not None
    assert sb.customer_group == group and sb.king_branch == king and sb.direction == direction
    assert sb.text.startswith("간지론에서는") and "단정하지 말 것" in sb.text


def test_second_basis_is_separate_from_twelve_sinsal_picks():
    """쥐띠: 12신살 1순위(지살 申=서)는 불변이고 제2기준(동)은 별도 필드에만 있다."""
    dic = load_sinsal_direction_dict()
    profile = build_direction_profile(Branch("子"), dic)
    rec = recommend_for_purpose(profile, DirectionPurpose("sales"), dic)
    assert rec.picks[0].sinsal == "지살" and rec.picks[0].absolute_direction == "서"
    assert rec.second_basis is not None and rec.second_basis.direction == "동"
    assert all(p.absolute_direction != "동" or p.sinsal != "제2기준" for p in rec.picks)


def test_second_basis_only_for_sales_purpose():
    dic = load_sinsal_direction_dict()
    profile = build_direction_profile(Branch("子"), dic)
    for purpose in DirectionPurpose:
        if purpose == DirectionPurpose("sales"):
            continue
        rec = recommend_for_purpose(profile, purpose, dic)
        assert rec.second_basis is None, purpose


def test_format_lines_include_second_basis_once():
    from saju_engines.sinsal_direction import format_sinsal_direction_lines
    from saju_shared_types.sinsal_direction import SinsalDirectionBlock

    dic = load_sinsal_direction_dict()
    profile = build_direction_profile(Branch("子"), dic)
    rec = recommend_for_purpose(profile, DirectionPurpose("sales"), dic)
    block = SinsalDirectionBlock(profile=profile, recommendations=[rec], proactive=False)
    lines = format_sinsal_direction_lines(block)
    hits = [x for x in lines if x.startswith("  · [제2기준·간지론] 동쪽 卯")]
    assert len(hits) == 1 and "앞 그룹 亥卯未" in hits[0]
