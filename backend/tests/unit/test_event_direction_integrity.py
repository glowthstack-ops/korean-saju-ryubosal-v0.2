"""이벤트 방향·근거 무결성 회귀 (2026-07-22 데굴님 확정 P0~P4).

실사례(금전·횡재운 리포트): ①'運 子↔원국 丁 천간합' — 천간 관계에 지지가 렌더링되는
차단급 참조 오류 ②두 글자 결집이 '삼합/방합'으로 표기돼 완성 국 오해 ③'횡재+손실·지출'
모순 라벨 ④점수순 Top-N이 부정 후보 일색으로 표를 채움(긍정 후보 존재에도 컷).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.ganji_calendar import relation_hits
from saju_engines.report_event_input import (
    _relation_lines,
    select_table_candidates,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import (
    event_display_ko,
    result_direction,
)
from saju_shared_types.ganji_calendar import GanjiLevel, RelationType

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male",
)


def _chart():
    return calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 7, 22)}))


# ── P0 — 관계 endpoint 불변식 ─────────────────────────────────

def test_stem_combination_endpoints_are_stems() -> None:
    """천간합 hit의 양쪽 노드는 천간만 — '運 子↔원국 丁 천간합' 차단."""
    r = _chart()
    assert r.pillars is not None and r.luck_cycles is not None
    checked = 0
    for p in [*r.luck_cycles.yearly_luck, *r.luck_cycles.monthly_luck]:
        hits = relation_hits(
            GanjiLevel.MONTH, p.stem, p.branch,
            p.relations_to_chart, p.gongmang_activation, r.pillars,
        )
        for h in hits:
            if h.type is RelationType.STEM_COMBINATION:
                assert h.luck_ref.stem and not h.luck_ref.branch
                assert all(ref.stem and not ref.branch for ref in h.natal_refs)
                checked += 1
            else:
                assert h.luck_ref.branch and not h.luck_ref.stem
    assert checked >= 1  # 이 차트에서 천간합이 최소 1건은 검증됨


def test_relation_lines_never_mix_stem_branch() -> None:
    """렌더 문자열에 '子…천간합' 류 혼합 표기가 없다(운 천간이 표기됨)."""
    r = _chart()
    assert r.pillars is not None and r.luck_cycles is not None
    for p in r.luck_cycles.yearly_luck:
        for line in _relation_lines(p, GanjiLevel.YEAR, r):
            if "천간합" in line:
                # 運 뒤 글자는 그 운의 천간이어야 한다.
                luck_char = line.split("運 ")[1][0]
                assert luck_char == p.stem, line


def test_partial_harmony_label_marks_incomplete() -> None:
    """두 글자 결집은 '일부 결집(미완성)'으로 표기 — 완성 삼합/방합 오해 차단."""
    r = _chart()
    assert r.luck_cycles is not None
    joined = "\n".join(
        line
        for p in [*r.luck_cycles.yearly_luck, *r.luck_cycles.monthly_luck]
        for line in _relation_lines(p, GanjiLevel.MONTH, r)
    )
    if "삼합" in joined or "방합" in joined:
        assert "일부 결집(미완성" in joined
        assert "삼합(세력 보조)" not in joined  # 구 라벨 잔존 금지


# ── P1 파생축 + P2 방향 인지 라벨 ─────────────────────────────

def test_result_direction_axes() -> None:
    assert result_direction("opportunity") == "positive"
    assert result_direction("loss") == "negative"
    assert result_direction("pressure") == "activation"  # 부담=경험 품질, 실패 아님
    assert result_direction("opportunity", "delay") == "delay"  # 지연이 우선
    assert result_direction(None) == "unknown"


def test_windfall_label_never_contradicts() -> None:
    assert event_display_ko("windfall", "loss") == "예상 밖 지출·손실 위험"
    assert event_display_ko("windfall", "opportunity") == "뜻밖의 수입·수익 기회"
    assert event_display_ko("windfall", None) == "돌발 금전 변동"
    assert "횡재" not in event_display_ko("windfall", "loss")


def test_pressure_keeps_activation_label() -> None:
    # '합격+부담'을 실패로 격하하지 않는다 — 국면 라벨 + 방향 열이 부담을 병기.
    assert event_display_ko("job_gain", "pressure") == "구직·채용 국면"
    assert event_display_ko("education_admission", "pressure") == "시험·학업 관련 변동"
    assert event_display_ko("marriage_signal", "pressure") == "혼인 논의 국면"


def test_unlisted_key_falls_back() -> None:
    assert event_display_ko("relocation", "opportunity") == "이사·이동"


# ── P3 표 계층 선별 ───────────────────────────────────────────

def _cand(key: str, period: str, score: int, quality: str | None):
    from saju_shared_types.events import EventCandidate

    return EventCandidate(
        event_key=key, event_type="instant", period=period, score=score,
        confidence="medium", polarity="positive", quality=quality,
    )


def test_selection_dedups_adjacent_and_keeps_directions() -> None:
    pool = [
        _cand("windfall", "2028-11", 87, "loss"),
        _cand("windfall", "2028-12", 72, "loss"),   # 인접 달 동일 사건 — 제거 대상
        _cand("wealth_change", "2029-03", 55, "opportunity"),  # 저점수 긍정 — 대표로 생존
        _cand("windfall", "2030-07", 69, "loss"),
    ]
    sel = select_table_candidates(pool, cap=3)
    periods = {str(c.period) for c in sel}
    assert "2028-12" not in periods  # 인접 중복 제거
    assert any(c.quality == "opportunity" for c in sel)  # 존재하는 긍정 대표 포함


def test_selection_no_positive_quota_when_absent() -> None:
    # 긍정 후보가 없으면 억지로 만들지 않는다 — 부정 일색 그대로(사실 보존).
    pool = [
        _cand("windfall", "2028-11", 87, "loss"),
        _cand("windfall", "2030-07", 69, "loss"),
    ]
    sel = select_table_candidates(pool, cap=3)
    assert all(c.quality == "loss" for c in sel)
