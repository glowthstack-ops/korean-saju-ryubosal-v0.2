"""운 구조 층 후속(2026-11-18 데굴님 결정 5건) — 총운 대운별 페이지 배선·재직 기간 가능성 줄·
재직 상태 구분 오탐·다른 대운 배수의 사건 키 한정·적재 전용 소스의 점수 제외.

- "넣어줘": 총운 대운별 페이지(F-14-D*)에 '원국 구조 × 운에서 온 글자' 블록(세운 10해).
- "이 시점 입사의 경우 장기 재직할 수도 있다 정도의 뉘앙스로": 입사·이직 후보 해의 세운에 용신 군
  글자가 오면 가능성 한 줄(점수·두 칸 배정 불변).
- "재직 기간 중이라면 … 오탐이라고 볼 수 없다": 측정에서 재직 중인 달을 평가에서 뺀다.
- "원장에 적재만": 소스 chat_statement 는 시그니처·코호트 조회에서 빠진다.
"""

from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace

import pytest

from saju_api.services import chat_service
from saju_api.services import report_service as rs
from saju_api.services.manse_service import calculate
from saju_engines import luck_structure_tags as T
from saju_engines import period_v2_config
from saju_engines.pattern_transit import daewoon_ganji_by_year
from saju_engines.personal_calibration import _GLYPH_CFG, _cfg_for_event_key
from saju_engines.report_plan import build_section_plans
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.life_event import (
    SCORING_EXCLUDED_SOURCES,
    LifeEventAttrs,
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
)
from saju_shared_types.report import ReportPeriod, ReportSpec

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import measure_employment_history_loo as M  # noqa: E402

# 己 일간 신약·정재격 — 비겁 용신. 2027 丁未(지지 비견)·2028 戊申(천간 겁재)이 용신 군 세운이다.
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울", gender="male",
)
_TODAY = date(2026, 11, 18)


@pytest.fixture(scope="module")
def chart():
    return calculate(_BIRTH)


@pytest.fixture(scope="module")
def natal(chart):
    return detect_structure_patterns(chart)


def _tenure(chart, natal, periods):
    lc = chart.luck_cycles
    sewoon = {int(p.label[:4]): p.ganji for d in lc.daewoon_table for p in d.sewoon}
    return T.entry_tenure_possibility_line(
        chart, natal, daewoon_by_year=daewoon_ganji_by_year(chart), sewoon_by_year=sewoon,
        periods=periods,
    )


# ── 재직 기간 가능성 줄 ──────────────────────────────────────────────────────
def test_tenure_line_marks_only_years_with_yong_group_sewoon(chart, natal) -> None:
    line = _tenure(chart, natal, ["2027-04", "2027-08"])
    assert line is not None and line.startswith(T.ENTRY_TENURE_HEADER)
    assert "2027년(丁未 — 지지 비견)" in line and "용신 군(비겁)" in line
    assert "오래 재직하게 될 수도 있다" in line           # 가능성 어미
    assert "확정하지 말고" in line and "뒤집어 말하지 말 것" in line
    # 1월 라벨(丑월)은 전년 세운에 속한다 — 2027-01 은 2026 丙午(용신 군 아님).
    assert _tenure(chart, natal, ["2026-11", "2027-01"]) is None
    # 실이력과 같은 판정: 장기 재직 4곳의 입사 달은 표지가 서고, 단기였던 2004-08 은 서지 않는다.
    long_line = _tenure(chart, natal, ["2006-05", "2016-01", "2018-03"])
    assert long_line is not None
    assert all(y in long_line for y in ("2006년", "2015년", "2018년"))
    assert _tenure(chart, natal, ["2004-08"]) is None
    # 상한 — 해가 많아도 앞에서 3해까지만.
    many = _tenure(chart, natal, ["2027", "2028", "2029", "2030", "2031"])
    assert many is not None and many.count("년(") == T.ENTRY_TENURE_MAX_YEARS
    assert _tenure(chart, natal, []) is None


def test_tenure_line_is_empty_without_hour_pillar() -> None:
    unknown = calculate(BirthInput(
        birth_date=date(1980, 11, 22), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="male",
    ))
    assert _tenure(unknown, detect_structure_patterns(unknown), ["2027"]) is None


def test_chat_tenure_line_uses_entry_candidates_then_question_window(chart, monkeypatch) -> None:
    job = next(iter(chat_service._ENTRY_CHANNEL_KEYS))
    cands = [SimpleNamespace(event_key=job, period="2027-04")]
    assert "2027년(丁未" in (chat_service._entry_tenure_line(chart, cands) or "")
    # 다른 사건 후보는 입사 시점이 아니다 — 후보가 없으면 질문 기간의 해를 본다.
    other = [SimpleNamespace(event_key="wealth_change", period="2027-04")]
    assert chat_service._entry_tenure_line(chart, other) is None
    window = SimpleNamespace(start="2027-01", end="2027-12")
    assert "2027년(丁未" in (chat_service._entry_tenure_line(chart, other, window) or "")
    # 반례: 열린 '언제' 질문(기간 없음)·상한보다 긴 기간은 해를 끌어오지 않는다.
    assert chat_service._entry_tenure_line(chart, [], None) is None
    long_window = SimpleNamespace(start="2027", end="2036")
    assert chat_service._entry_tenure_line(chart, [], long_window) is None
    monkeypatch.setattr(period_v2_config, "ENTRY_TENURE_NOTE_ENABLED", False)
    assert chat_service._entry_tenure_line(chart, cands) is None


def test_career_report_entry_sections_carry_tenure_line() -> None:
    """1985-04-18 남 — 2026 직업 테마의 주목할 달·행동 전략에 한 번씩, 다른 섹션·테마에는 없음."""
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1985, 4, 18), birth_time="10:00",
        birth_place_name="서울", gender="male",
    )

    def bodies(topic: str) -> dict[str, str]:
        spec = ReportSpec(
            product_code="RPT_FOCUS", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            topic=topic, period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
        )
        return {c.section_id: c.body_prompt for c in rs.plan_report(birth, spec, _TODAY)}

    career = bodies("career")
    hit = {sid for sid, body in career.items() if T.ENTRY_TENURE_HEADER in body}
    assert hit == {"J-06", "J-07"}
    assert all(career[sid].count(T.ENTRY_TENURE_HEADER) == 1 for sid in hit)
    assert all(T.ENTRY_TENURE_HEADER not in body for body in bodies("wealth").values())


# ── 총운 대운별 페이지 ───────────────────────────────────────────────────────
def test_full_report_decade_pages_carry_role_block_with_ten_years(monkeypatch) -> None:
    spec = ReportSpec(
        product_code="RPT_FULL", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01-01", end="2070-12-31"),
    )
    data = rs._ReportData(_BIRTH, spec, _TODAY, owner_id=None, subject_id=None)
    plans = rs._expand_report_plans(build_section_plans(spec), data)
    pages = {p.section_id: p for p in plans if p.section_id.startswith("F-14-D")}
    sid = next(s_ for s_, w in data.decade_windows.items() if w[2] == "壬辰")
    body = rs.build_section_context(pages[sid], spec, data).body_prompt
    assert body.count(rs._NATAL_LUCK_ROLE_HEADER) == 1
    block = body[body.index(rs._NATAL_LUCK_ROLE_HEADER):].split("\n\n")[0].splitlines()
    assert block[1].startswith("원국: 신약")
    assert block[2].startswith("대운 壬辰: 천간 정재(구신)·지지 겁재(용신) — ")
    assert sum(ln.startswith("세운 ") for ln in block) == 10  # 한 대운의 10해 전부(상한 6 예외)
    assert not any(ln.startswith("월운 ") for ln in block)
    # 구조 상태 줄은 그대로 남는다(무엇이 달라졌는지 ↔ 어떤 글자가 어떤 역할로 왔는지).
    assert "[이 대운의 구조 상태" in body
    # 반례: 원국 전용 섹션에는 없다.
    f01 = next(p for p in plans if p.section_id == "F-01")
    assert rs._NATAL_LUCK_ROLE_HEADER not in rs.build_section_context(f01, spec, data).body_prompt
    monkeypatch.setattr(period_v2_config, "NATAL_LUCK_ROLE_BLOCK_ENABLED", False)
    off = rs.build_section_context(pages[sid], spec, data).body_prompt
    assert rs._NATAL_LUCK_ROLE_HEADER not in off


def test_default_year_cap_is_unchanged_outside_decade_pages(chart, natal) -> None:
    lc = chart.luck_cycles
    sewoon = {int(p.label[:4]): p.ganji for d in lc.daewoon_table for p in d.sewoon}
    kw = dict(
        daewoon_by_year=daewoon_ganji_by_year(chart), sewoon_by_year=sewoon, month_ganji={},
        labels=[str(y) for y in range(2026, 2034)],
    )
    assert not any(ln.startswith("세운 ") for ln in T.natal_luck_role_lines(chart, natal, **kw))
    wide = T.natal_luck_role_lines(chart, natal, max_years=T.ROLE_BLOCK_DECADE_YEARS, **kw)
    assert sum(ln.startswith("세운 ") for ln in wide) == 8


def test_structure_in_two_families_is_named_once(chart, natal) -> None:
    profile = T.natal_structure_profile(chart, natal)
    assert profile is not None
    reading = T.LuckLayerReading(
        stem_god="편관", branch_god="편재", stem_group="officer", branch_group="wealth",
        stem_role="기신", branch_role="구신", tags=(),
        changes=(("살중제경", "burden", "new"), ("살중제경", "help", "new")),
    )
    text = T._reading_phrases(profile, reading)
    assert text.count("살중제경") == 1
    assert "살중제경(과다·충돌 계열 겸 상생·제어 계열) 새로 섬" in text


# ── 측정: 재직 상태 구분 ─────────────────────────────────────────────────────
def _row(key: str, period: str, group: str, nature: str = "regular") -> LifeEventRow:
    return LifeEventRow(
        event_row_id=f"{group}:{key}:{period}", subject_id="s1", pillar_year="庚申",
        pillar_month="丁亥", pillar_day="己巳", event_key=key, period=period,
        outcome=LifeEventOutcome.CONFIRMED, source=LifeEventSource.EMPLOYMENT_HISTORY,
        attrs=LifeEventAttrs(nature=nature, employment_group=group),
    )


def test_month_status_excludes_employed_months_from_false_positive_pool() -> None:
    signature = [
        _row("job_gain", "2020-03", "g1"), _row("resignation", "2020-08", "g1"),
        _row("job_gain", "2021-01", "g2"),                       # 퇴사 행 없음 → 끝 달까지 재직
        _row("job_gain", "2019-06", "mil", nature="military"),   # 복무 — 통계 성격 아님
        _row("resignation", "2019-09", "mil", nature="military"),
    ]
    status = M.month_status(M.employment_intervals(signature, "2021-03"), "2021-03")
    assert status["2019-07"] == M.STATUS_EMPLOYED            # 복무 중
    assert status["2020-05"] == M.STATUS_EMPLOYED
    assert status["2021-03"] == M.STATUS_EMPLOYED            # 열린 구간
    assert status["2020-01"] == M.STATUS_PRE_ENTRY and status["2020-02"] == M.STATUS_PRE_ENTRY
    assert status["2019-10"] == M.STATUS_GAP                 # 공백·그 밖 = 오탐 후보
    assert status["2020-09"] == M.STATUS_GAP and status["2020-10"] == M.STATUS_GAP
    assert status["2020-11"] == M.STATUS_PRE_ENTRY           # 다음 입사(2021-01)의 직전 창
    # 복무 입사 앞 달에는 직전 창을 붙이지 않는다(취업 통계 성격만) — 첫 구간 이전은 범위 밖.
    assert "2019-05" not in status
    assert sum(v == M.STATUS_GAP for v in status.values()) == 5
    assert M.month_status([], "2021-03") == {}


# ── 다른 대운 배수의 사건 키 한정 ───────────────────────────────────────────
def test_other_daewoon_factor_can_be_limited_to_event_keys() -> None:
    assert _cfg_for_event_key(None, "job_gain") is None       # 운영 기본 — 설정 그대로
    cfg = {**_GLYPH_CFG, "other_daewoon_factor": 0.5, "other_daewoon_event_keys": ["job_gain"]}
    assert _cfg_for_event_key(cfg, "job_gain") is cfg
    limited = _cfg_for_event_key(cfg, "career_change")
    assert limited is not None and "other_daewoon_factor" not in limited
    assert limited["position_weights"] == cfg["position_weights"]
    everywhere = {**_GLYPH_CFG, "other_daewoon_factor": 0.5}
    assert _cfg_for_event_key(everywhere, "career_change") is everywhere  # 키 목록 없으면 전 키
    assert "other_daewoon_event_keys" not in _GLYPH_CFG                  # 운영 사전에는 없다
    assert "other_daewoon_factor" not in _GLYPH_CFG


# ── 적재 전용 소스의 점수 제외 ──────────────────────────────────────────────
class _FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> _FakeConn:
        self.calls.append((sql, params))
        return self

    def fetchall(self) -> list:
        return []

    def fetchone(self) -> tuple:
        return (0,)


def test_chat_statement_source_is_left_out_of_signature_and_cohort(monkeypatch) -> None:
    from saju_engines.life_event_store import LifeEventStore

    assert SCORING_EXCLUDED_SOURCES == frozenset({str(LifeEventSource.CHAT_STATEMENT)})
    store = LifeEventStore("postgresql://unused")
    conn = _FakeConn()
    monkeypatch.setattr(store, "_connect", lambda: conn)
    store.subject_signature("o1", "s1")
    sql, params = conn.calls[-1]
    assert "NOT (source = ANY(%s))" in sql and params == ("o1", "s1", ["chat_statement"])
    store.subject_signature("o1", "s1", include_unverified=True)   # 측정 스크립트만
    assert conn.calls[-1][1] == ("o1", "s1", [])
    store.cohort_count(pillar_day="己巳", gender="male", event_key="job_gain")
    sql, params = conn.calls[-1]
    assert "NOT (source = ANY(%s))" in sql and params[0] == ["chat_statement"]
    store.cohort_event_counts(pillar_day="己巳", gender=None)
    assert all(p[0] == ["chat_statement"] for _s, p in conn.calls[-2:])


def test_lag_signal_reads_month_top_event_and_year_top3() -> None:
    """시차 측정의 신호 판정 — 그 달 1순위 사건 / 그 절기년 취업 후보 Top-3 (§9-1b)."""
    from types import SimpleNamespace

    def cand(period: str, key: str) -> SimpleNamespace:
        return SimpleNamespace(period=period, event_key=key)

    ranked = [
        cand("2025-05", "job_gain"), cand("2025-02", "career_change"), cand("2025-02", "job_gain"),
        cand("2025-08", "job_gain"), cand("2025-11", "job_gain"), cand("2025-11", "career_change"),
    ]
    assert M._signals_of(ranked, "2025-05") == (True, True)
    # 반례: 취업 후보가 Top-3 달이어도 그 달 1순위가 다른 사건이면 1순위 신호는 아니다.
    assert M._signals_of(ranked, "2025-02") == (False, True)
    # 반례: 그 달 1순위가 취업이어도 연 안 4번째면 Top-3 신호는 아니다.
    assert M._signals_of(ranked, "2025-11") == (True, False)
    assert M._signals_of(ranked, "2025-03") == (False, False)
    assert set(M._LAG_WINDOWS["1~2달 전"]) == {1, 2} and 0 in M._LAG_OFFSETS
