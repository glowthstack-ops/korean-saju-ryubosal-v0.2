"""창고(입고·개고) 판정 층 — 무엇의 창고인가·상태·운의 개고/입고·득실 표기(2026-11-13).

SSOT: doc/v2_2/STORAGE_GATES.md. 반례가 있는 단언만 둔다.
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate, pattern_timeline
from saju_engines.dictionaries import STORAGE_GATE_TEXT_IDS
from saju_engines.storage_gates import (
    MONTH_OVERLAP_MARK,
    _Chart,
    _period_events,
    load_storage_gate_text,
    natal_storage_lines,
    storage_gate_block,
    storage_gate_lines,
)
from saju_shared_types.birth_input import BirthInput

# 庚申 丁亥 己亥 己巳 — 원국에 辰戌丑未 없음, 현재 대운 壬辰(水 창고 = 재고).
_NO_STORE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울", gender="male",
)
# 己未 丁丑 壬辰 乙巳 — 원국에 창고 셋(未·丑 충, 辰은 일간 壬 투출).
_THREE_STORES = BirthInput(
    birth_date=date(1980, 1, 20), birth_time=time(10, 0), birth_place_name="서울", gender="male",
)


def _lines(birth: BirthInput, years: list[int]) -> list[str]:
    result = calculate(birth)
    timelines = [pattern_timeline(birth, y, include_months=False) for y in years]
    return storage_gate_lines(result, timelines, [str(y) for y in years])


def test_text_dictionary_covers_every_id() -> None:
    assert set(load_storage_gate_text()) == set(STORAGE_GATE_TEXT_IDS)


def test_natal_lines_name_the_store_and_its_state() -> None:
    lines = natal_storage_lines(calculate(_THREE_STORES))
    by_branch = {ln.split(" ")[2][0]: ln for ln in lines}
    # 壬 일간: 未 = 木 창고(식상고), 丑 = 金 창고(인고), 辰 = 水 창고(비겁고).
    assert "= 木 창고·식상고" in by_branch["未"] and "= 金 창고·인고" in by_branch["丑"]
    assert "= 水 창고·비겁고" in by_branch["辰"]
    # 丑未충으로 이미 열려 있고, 未의 木은 시간 乙로 투출(이미 쓰는 중).
    assert "원국 丑과 충 — 이미 열려 있음" in by_branch["未"]
    assert "木 천간 투출(시간 乙) — 이미 쓰는 중" in by_branch["未"]
    assert "水 천간 투출(일간 壬) — 이미 쓰는 중" in by_branch["辰"]
    # 반례: 창고 지지가 없는 원국은 그 사실 한 줄만.
    none = natal_storage_lines(calculate(_NO_STORE))
    assert none == ["원국 창고: 辰戌丑未 없음 — 창고 작용은 운에서 창고 지지가 올 때만 생긴다"]


def test_entering_meaning_follows_strength_and_role() -> None:
    chart = _Chart(calculate(_NO_STORE))
    # 水 32.7%(강)·木 8.8%(결핍)·金 17%(보통) — 엔진 세력 값을 그대로 읽는다.
    assert chart.strength_class("水") == "strong" and chart.strength_class("木") == "weak"
    assert chart.strength_class("金") == "mid"
    text = load_storage_gate_text()
    lines = _lines(_NO_STORE, [2026])
    # 대운 辰 = 水 창고(재고). 원국에 드러난 水(월지·일지 亥)가 들어가는데, 세력이 강한 구신이라
    # '갇혀 잦아든다'가 아니라 '쌓여 부담이 두터워진다'로 읽는다(旺者入庫).
    dw = next(ln for ln in lines if ln.startswith("대운 壬辰: "))
    assert "辰(水 창고·재고)" in dw and "水(재성·구신)[월지 亥·일지 亥]이 입고" in dw
    assert dw.endswith(text["enter_strong_bad"])
    assert text["enter_weak_bad"] not in dw


def test_luck_opens_binds_and_reveals() -> None:
    lines = _lines(_NO_STORE, [2027, 2029, 2030])
    # 2030 庚戌: 세운 戌이 대운 辰을 충 → 개고. 戌(火·土 창고)도 열린 채 들어온다.
    y2030 = [ln for ln in lines if ln.startswith("세운 庚戌 2030년: ")]
    assert any("대운 辰(水 창고·재고)을 충 → 개고" in ln for ln in y2030)
    assert any("운 창고 戌(火 창고·인고 / 土 창고·비겁고)이 대운 辰과 충" in ln for ln in y2030)
    # 2029 己酉: 辰酉 육합 — 대운 창고가 묶인다(열리지 않음).
    assert any(ln.startswith("세운 己酉 2029년: ") and "육합으로 묶여" in ln for ln in lines)
    # 반례: 2027 丁未 — 未(木 창고)가 오지만 원국에 드러난 木이 없어 작용이 없다(줄 없음).
    assert not any(ln.startswith("세운 丁未 2027년: ") for ln in lines)
    # 개고는 저장 오행의 역할대로 표기한다 — 용신 金 창고(丑)를 未 세운이 충.
    opened = next(ln for ln in _lines(_THREE_STORES, [2027]) if "원국 丑" in ln and "개고" in ln)
    assert "金(인성·용신) " + load_storage_gate_text()["open_good"] in opened


def _month_lines(birth: BirthInput, year: int, labels: list[str]) -> list[str]:
    result = calculate(birth)
    return storage_gate_lines(result, [pattern_timeline(birth, year, include_months=True)], labels)


def test_both_directions_are_tagged() -> None:
    """원국 창고가 운에 움직인 것([원국 발동])과 운에서 온 것([운 도래])을 모두 낸다."""
    lines = _month_lines(_THREE_STORES, 2026, ["2026-12", "2027-01"])
    # [원국 발동] 투출 — 운 천간의 오행이 원국 창고의 저장 오행(《子平真詮》 壬透: 양간도 투출).
    for label, stem in (("2026-12 庚子", "庚"), ("2027-01 辛丑", "辛")):
        head = f"월운 {label}: [원국 발동] 운 천간 {stem}이 원국 丑의 金"
        assert any(ln.startswith(head) and "드러냄" in ln for ln in lines)
    # 반례: 운에서 온 글자의 '입묘'는 판정하지 않는다 — 천간(庚→丑)도, 지지(子→辰)도 줄이 없다.
    assert not any("으로 입고" in ln or "운 지지" in ln for ln in lines)
    # [운 도래] 운 창고가 원국 충을 맞아 열린 채 옴. 2027-01 丑 ↔ 원국 未.
    assert any("[운 도래] 운 창고 丑(金 창고·인고)이 원국 未과 충" in ln for ln in lines)
    # 모든 기간 줄은 두 표지 가운데 하나를 가진다.
    assert all("[원국 발동]" in ln or "[운 도래]" in ln for ln in lines)


def test_half_combination_peak_does_not_enter() -> None:
    """왕지와 그 창고(子辰)는 반합이라 입고로 세지 않는다 — 論合不論墓."""
    # 甲子 丙寅 己巳 庚午 — 원국에 드러난 水는 연지 子뿐.
    peak_only = BirthInput(
        birth_date=date(1984, 2, 5), birth_time=time(12, 0), birth_place_name="서울", gender="male",
    )
    chart = _Chart(calculate(peak_only))
    assert chart.visible("水") == ["연지 子"]
    assert _period_events(chart, "甲", "辰", []) == []
    # 반례: 생지 亥는 왕지가 아니므로 운 창고 辰이 오면 입고 줄이 선다(_NO_STORE 대운 壬辰).
    dw = next(ln for ln in _lines(_NO_STORE, [2026]) if ln.startswith("대운 壬辰: "))
    assert "[월지 亥·일지 亥]이 입고" in dw


def test_month_line_marks_overlap_with_upper_layers() -> None:
    """월운 줄의 겹침 표지 — 같은 창고가 대운·세운 줄에도 있을 때만."""
    lines = _month_lines(_THREE_STORES, 2026, ["2026-12", "2027-01"])
    # 세운 丙午가 원국 未를 묶고(午未 육합), 2027-01 丑월이 같은 未를 충 → 표지.
    hit = next(
        ln for ln in lines
        if ln.startswith("월운 2027-01") and "원국 未(木 창고·식상고)을 충" in ln
    )
    assert hit.endswith(MONTH_OVERLAP_MARK)
    # 반례: 丑은 대운·세운이 건드리지 않았다 → 丑에 대한 월운 줄에는 표지가 없다.
    for ln in lines:
        if ln.startswith("월운") and "원국 丑" in ln:
            assert not ln.endswith(MONTH_OVERLAP_MARK)
    # 대운·세운 줄에는 표지를 붙이지 않는다.
    assert not any(ln.endswith(MONTH_OVERLAP_MARK) for ln in lines if not ln.startswith("월운"))


def test_block_carries_reading_guide_only_for_present_layers() -> None:
    """층·분류 읽는 법은 실린 줄에 해당하는 것만 싣는다."""
    text = load_storage_gate_text()
    result = calculate(_NO_STORE)
    years = [pattern_timeline(_NO_STORE, y, include_months=False) for y in (2029, 2030)]
    block = storage_gate_block(result, years, ["2029", "2030"])
    assert text["layer_daewoon"] in block and text["layer_year"] in block
    assert text["class_luck"] in block
    # 반례: 월운 줄이 없으면 월운 읽는 법이 없고, 원국 창고가 없으면 [원국 발동] 읽는 법도 없다.
    assert text["layer_month"] not in block and text["class_natal"] not in block
    assert block[-1] == text["rule"]


def test_block_is_omitted_when_nothing_to_say() -> None:
    result = calculate(_NO_STORE)
    # 辛卯 대운·乙未년(2015): 원국에 창고가 없고, 未가 와도 드러난 木이 없다 → 블록 없음.
    tl = [pattern_timeline(_NO_STORE, 2015, include_months=False)]
    assert storage_gate_block(result, tl, ["2015"]) == []
    # 반례: 원국에 창고가 있으면 기간에 작용이 없어도 원국 상태 줄과 '작용 없음'을 싣는다.
    three = calculate(_THREE_STORES)
    quiet = storage_gate_block(three, [], [])
    assert quiet[0].startswith("[창고(입고·개고)") and quiet[-2] == load_storage_gate_text()["none"]
    # 시주 미상은 판정하지 않는다(용희신·십성 배치 미확정).
    unknown = BirthInput(
        birth_date=date(1980, 1, 20), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="male",
    )
    assert storage_gate_block(calculate(unknown), [], []) == []


def test_chat_block_carries_storage_lines_for_window_and_single_period() -> None:
    rows = [SimpleNamespace(period=lb) for lb in ("2026-11", "2026-12", "2027-01")]
    block = chat_service._window_structure_block(_NO_STORE, rows, "취업운 정리해줘")
    assert block is not None and "[창고(입고·개고)" in block
    assert "월운 2027-01 辛丑: [운 도래] 운 창고 丑(金 창고·식상고)이 옴" in block
    # 단일 기간·시점 없는 질문에도 창고 블록은 실린다(구조 블록은 기간 질문에만).
    single = chat_service._window_structure_block(
        _NO_STORE, [], "2030년 재물운", SimpleNamespace(start="2030", end="2030")
    )
    assert single is not None and "개고" in single and "[운에서 서는 구조" not in single
    timeless = chat_service._window_structure_block(
        _NO_STORE, [], "내 사주에 재물 창고 있어?", None, date(2026, 11, 13)
    )
    assert timeless is not None and "대운 壬辰: [운 도래] 운 창고 辰(水 창고·재고)이 옴" in timeless
