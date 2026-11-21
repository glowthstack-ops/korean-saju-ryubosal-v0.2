"""세운 12신살 결 층 · 12신살 기준 자리 병용 · 궁위 표 · 오늘의 운세 12신살 문장 (2026-11-21).

데굴님 결정: ① 12신살 12종 전체를 띠(연지) 기준으로도 인정(측정 뒤 공용 상수 반영) ② 궁위 표를
한곳으로 모으고 인연 범위 열을 보조 서술로 추가 ③ 오늘의 운세는 일주만으로 되는 것만 적용.
새 층은 전부 서술 전용이다 — 점수·후보·판정은 바뀌지 않는다.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_api.services.manse_service import calculate
from saju_engines import daily_ilju_fortune as M
from saju_engines import simple_reading as SR
from saju_engines.chart_interpretation import _PALACE_ROLE, _SINSAL_PALACE_LABEL
from saju_engines.context_reducer import _year_sinsal_years
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_engines.dictionaries import lint_dictionaries, validate_dictionaries
from saju_engines.palace_relationship_network import _PALACE_ROLES
from saju_engines.repetition_structure import _PALACE_KO
from saju_engines.year_sinsal_flow import (
    MAX_YEARS,
    YEAR_SINSAL_HEADER,
    YEAR_SINSAL_INSTRUCTION,
    build_year_sinsal,
    format_year_sinsal_lines,
    load_year_sinsal_text,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    DICT_VERSION_BEFORE_LUCK_SINSAL,
    LUCK_SINSAL_EFFECTIVE_FROM,
    active_dict_version,
)
from saju_shared_types.enums import Branch as B
from saju_shared_types.intent import Domain, Granularity, IntentJson, QueryType, TimeRange
from saju_shared_types.llm_input import PeriodFortune
from saju_shared_types.palace_scope import (
    PALACE_KEYS,
    PALACE_SCOPE_RULE,
    PALACE_TABLE,
    palace_column,
    palace_scope_legend,
)
from saju_shared_types.twelve_sinsal import (
    DOHWA_BASE_SLOTS,
    SELF_SINSAL_BASE_SLOTS,
    TWELVE_SINSAL_ORDER,
    self_sinsal_bases,
)

_HANJA_OR_DIGIT = re.compile(r"[一-鿿0-9]")
_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_LECTURE_NAMES = {"화개살", "월살", "천살", "반안살"}


def _chart(day: str, time: str = "10:00"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=day, birth_time=time, birth_place_name="서울",
        gender="male",
    ))


# ── 1. 12신살 기준 자리 — 연지·일지 병용 ───────────────────────────────────────


def test_self_sinsal_bases_use_year_and_day() -> None:
    assert SELF_SINSAL_BASE_SLOTS == ("year", "day") == DOHWA_BASE_SLOTS
    assert self_sinsal_bases("午", "酉") == [("year", "연지", B.O), ("day", "일지", B.YU)]
    assert self_sinsal_bases("午", "酉", "화개살") == self_sinsal_bases("午", "酉", "년살")
    # 없는 자리는 건너뛴다.
    assert self_sinsal_bases(None, "酉") == [("day", "일지", B.YU)]


def test_natal_positional_sinsal_carries_both_bases() -> None:
    """원국 자리별 12신살이 연지 기준·일지 기준 근거를 각각 남긴다(같은 자리·같은 이름은 병기)."""
    r = _chart("1983-05-05")  # 연지 亥(亥卯未국) · 일지 巳(巳酉丑국)
    assert (r.pillars.year.branch, r.pillars.day.branch) == ("亥", "巳")
    basis = [
        s.basis for s in r.traditional_extras.sinsal.full_list
        if s.category == "twelve_sinsal" or s.name in ("역마살", "화개살", "도화")
    ]
    assert any(b.startswith("연지 亥 기준") for b in basis)
    assert any(b.startswith("일지 巳 기준") for b in basis)


# ── 2. 세운 12신살 사실 ────────────────────────────────────────────────────────


def test_year_sinsal_facts_differ_by_base() -> None:
    r = _chart("1983-05-05")
    row = build_year_sinsal(r, 2027)  # 丁未
    assert row is not None
    assert (row.stem.value, row.branch.value) == ("丁", "未")
    assert (row.by_year, row.by_day, row.same) == ("화개살", "월살", False)
    assert row.samjae_label == "날삼재"  # 띠 기준 화개 = 날삼재
    assert [(y, name) for y, _b, name in row.flow] == [
        (2026, "육해살"), (2027, "화개살"), (2028, "겁살"),
    ]
    # 반례: 삼재가 아닌 띠 기준 이름에는 삼재 라벨이 없다.
    other = build_year_sinsal(_chart("1988-03-03"), 2027)  # 연지 辰 → 천살
    assert other is not None and other.by_year == "천살" and other.samjae_label is None


def test_year_sinsal_same_trine_merges_into_one_item() -> None:
    r = _chart("1995-07-07")  # 연지 亥 · 일지 亥
    row = build_year_sinsal(r, 2027)
    assert row is not None and row.same and row.by_year == "화개살"
    lines = format_year_sinsal_lines(r, [2027])
    assert sum("▸ 화개살" in ln for ln in lines) == 1
    assert any("띠·일지 두 기준 모두 화개살(= 날삼재)" in ln for ln in lines)


def test_year_sinsal_every_year_maps_to_table() -> None:
    """12년 전부 두 기준 이름이 12신살 표 안에 있고, 띠 기준은 12년에 12종이 한 번씩 돈다."""
    r = _chart("1983-05-05")
    rows = [build_year_sinsal(r, y) for y in range(2020, 2032)]
    assert all(row is not None for row in rows)
    assert {row.by_year for row in rows if row} == set(TWELVE_SINSAL_ORDER)
    assert {row.by_day for row in rows if row} == set(TWELVE_SINSAL_ORDER)


# ── 3. 블록 렌더 ───────────────────────────────────────────────────────────────


def test_block_renders_scope_labels_scenes_and_cycle() -> None:
    r = _chart("1983-05-05")
    lines = format_year_sinsal_lines(r, [2027], current_year=2027)
    text = "\n".join(lines)
    assert lines[0] == "" and lines[1] == YEAR_SINSAL_HEADER
    assert "기준: 띠(연지) 亥(亥卯未국) · 일지 巳(巳酉丑국)" in text
    assert "- 2027년 丁未 ◀ 올해: 띠 기준 화개살(= 날삼재) · 일지 기준 월살" in text
    assert "▸ 화개살 [띠(연지) 기준 — 바깥·사회 쪽]" in text
    assert "▸ 월살 [일지 기준 — 가까운 관계·생활 쪽]" in text
    assert "장면:" in text and "태도:" in text and "대비:" in text
    # 화개 해의 삼합 주기 — 시작 해(지살)는 8년 전, 한창 해(장성살)는 4년 전.
    assert "시작 해 2019년(지살) · 한창 해 2023년(장성살)" in text
    assert build_year_sinsal(r, 2019).by_year == "지살"  # type: ignore[union-attr]
    assert build_year_sinsal(r, 2023).by_year == "장성살"  # type: ignore[union-attr]


def test_block_compact_drops_scenes_and_contrast() -> None:
    r = _chart("1983-05-05")
    text = "\n".join(format_year_sinsal_lines(r, [2027], compact=True))
    assert "태도:" in text and "주기:" in text
    assert "장면:" not in text and "대비:" not in text


def test_block_cheonsal_names_the_outside_agent_by_ten_god() -> None:
    r = _chart("1988-03-03")  # 연지 辰 → 2027 未 = 천살
    row = build_year_sinsal(r, 2027)
    assert row is not None
    text = "\n".join(format_year_sinsal_lines(r, [2027]))
    agent = f"천간 丁 {row.stem_god} · 지지 未 {row.branch_god}"
    assert f"바깥의 주체: 이 해 운의 십성 — {agent}" in text
    # 반례: 천살이 아닌 이름(월살)에는 '바깥의 주체' 줄이 한 번뿐이다(천살 항목 것).
    assert text.count("바깥의 주체:") == 1
    # 천을귀인 동반 표기는 세운 지지가 일간의 귀인 글자일 때만.
    assert ("천을귀인 동반" in text) is row.cheoneul


def test_block_falls_back_to_meaning_for_names_without_lecture_text() -> None:
    """문구가 있는 것은 4종뿐 — 午년(왕지 4종)은 뜻 한 문장만 싣고 장면·태도를 만들지 않는다."""
    r = _chart("1983-05-05")
    text = "\n".join(format_year_sinsal_lines(r, [2026]))
    assert "▸ 육해살 [띠(연지) 기준 — 바깥·사회 쪽]: (뜻) " in text
    assert "▸ 년살 [일지 기준 — 가까운 관계·생활 쪽]: (뜻) " in text
    assert "장면:" not in text and "태도:" not in text


def test_block_limits_years_and_handles_missing_chart() -> None:
    r = _chart("1983-05-05")
    lines = format_year_sinsal_lines(r, [2025, 2026, 2027, 2028, 2029])
    assert sum(ln.startswith("- 20") for ln in lines) == MAX_YEARS
    assert format_year_sinsal_lines(r, []) == []
    assert format_year_sinsal_lines(r.model_copy(update={"pillars": None}), [2027]) == []


def test_dictionary_covers_four_names_without_assertive_words() -> None:
    text = load_year_sinsal_text()
    assert {it["name"] for it in text["items"]} == _LECTURE_NAMES
    assert {sc["id"] for sc in text["scopes"]} == {"year", "day", "both"}
    for it in text["items"]:
        for sentence in (it["core"], it["stance"], *it["scenes"]):
            assert not any(w in sentence for w in ("반드시", "틀림없이", "무조건", "큰일"))
        # 장면은 가능성 어미로만 쓴다.
        assert all(scene.endswith("수 있다") for scene in it["scenes"]), it["name"]
    assert "출처·강의 언급 금지" in YEAR_SINSAL_INSTRUCTION
    assert validate_dictionaries(_DICTS) == [] and lint_dictionaries(_DICTS) == []


# ── 4. 채팅 입력의 대상 연도 ───────────────────────────────────────────────────


def _intent(granularity: Granularity, start: str | None, end: str | None) -> IntentJson:
    return IntentJson(
        intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.CAREER,
        time_range=TimeRange(type="absolute", granularity=granularity, start=start, end=end),
    )


def _fortune(kind: str, label: str) -> PeriodFortune:
    return PeriodFortune(fortune_type=kind, period_label=label, ganji="丁未", pillar_line="-")


def test_year_sinsal_years_follow_question_horizon() -> None:
    year_q = _intent(Granularity.YEAR, "2027-01-01", "2027-12-31")
    assert _year_sinsal_years(year_q, None) == [2027]
    assert _year_sinsal_years(_intent(Granularity.YEAR, "2027-01-01", "2028-12-31"), None) == [
        2027, 2028,
    ]
    # 반례: 3년 이상 창·월 단위 질문·시점 없는 질문에는 싣지 않는다.
    assert _year_sinsal_years(_intent(Granularity.YEAR, "2027-01-01", "2029-12-31"), None) == []
    assert _year_sinsal_years(_intent(Granularity.MONTH, "2027-03-01", "2027-03-31"), None) == []
    assert _year_sinsal_years(year_q.model_copy(update={"time_range": None}), None) == []
    # 기간 총운: 연 총운만, 월·일 총운은 질문 창이 연 단위여도 싣지 않는다.
    assert _year_sinsal_years(year_q, _fortune("yearly", "2027")) == [2027]
    assert _year_sinsal_years(year_q, _fortune("monthly", "2027-03")) == []
    assert _year_sinsal_years(year_q, _fortune("daily", "2027-03-01 (월)")) == []


# ── 5. 궁위 표 — 한 표의 열 ────────────────────────────────────────────────────


def test_palace_table_feeds_every_consumer() -> None:
    assert PALACE_KEYS == ("year", "month", "day", "hour") == tuple(PALACE_TABLE)
    assert _PALACE_ROLE == palace_column("kin_role")
    assert _SINSAL_PALACE_LABEL == palace_column("sinsal_label")
    assert _PALACE_ROLES == palace_column("network_label")
    assert _PALACE_KO == palace_column("repetition_label")
    # 기존 문구는 그대로다(프롬프트 불변).
    assert _SINSAL_PALACE_LABEL["month"] == "월주(부모·직장·사회·청년 — 작용력 최대)"
    assert _PALACE_ROLES["day"] == "일지(배우자·친밀관계)"
    assert _PALACE_KO["hour"] == "시지(자녀·지향·투자)"


def test_palace_relation_scope_is_auxiliary() -> None:
    scope = palace_column("relation_scope")
    assert "윗사람" in scope["year"] and "해외" in scope["year"]
    assert "직장 동료" in scope["month"] and "상사" in scope["month"]
    assert "배우자" in scope["day"] and "연인" in scope["day"]
    assert "부하" in scope["hour"] and "후배" in scope["hour"] and "제자" in scope["hour"]
    legend = palace_scope_legend()
    assert legend.startswith("연주=") and legend.count(" / ") == 3
    assert "고정 등식" in PALACE_SCOPE_RULE and "보조 단서" in PALACE_SCOPE_RULE


def test_palace_scope_reaches_structure_block() -> None:
    from saju_engines.chart_interpretation import build_chart_interpretation  # noqa: PLC0415

    block = build_chart_interpretation(_chart("1985-10-29", "22:20"))
    assert {d.palace: d.palace_scope for d in block.pillar_details} == palace_column(
        "relation_scope"
    )
    # 기존 육친 자리역할 칸은 그대로다.
    assert {d.palace: d.palace_role for d in block.pillar_details} == _PALACE_ROLE


# ── 6. 오늘의 운세 — 일지 기준 12신살 문장 · 띠별 조건 줄 (dict.v1.24) ─────────


def _simple(d: dt.date) -> dict:
    return M.load_daily_dicts_for(d).templates["simple_layer"]


def test_daily_version_boundary() -> None:
    assert DICT_VERSION == "dict.v1.24" and DICT_VERSION_BEFORE_LUCK_SINSAL == "dict.v1.23"
    assert LUCK_SINSAL_EFFECTIVE_FROM == dt.date(2026, 11, 23)
    assert active_dict_version(LUCK_SINSAL_EFFECTIVE_FROM) == "dict.v1.24"
    before = LUCK_SINSAL_EFFECTIVE_FROM - dt.timedelta(days=1)
    assert active_dict_version(before) == "dict.v1.23"
    assert "luck_sinsal" not in _simple(before) and "luck_sinsal" in _simple(
        LUCK_SINSAL_EFFECTIVE_FROM
    )


def test_daily_sentences_follow_text_policy() -> None:
    pool = _simple(LUCK_SINSAL_EFFECTIVE_FROM)["luck_sinsal"]
    assert set(pool["body"]) == _LECTURE_NAMES
    for text in (*pool["body"].values(), pool["lead"]["year"], pool["lead"]["month"]):
        assert not _HANJA_OR_DIGIT.search(text), text
        assert not any(w in text for w in polish._FORBIDDEN), text
        # 노출 문장에는 살 이름을 쓰지 않는다(단식 층 용어 정책).
        assert not any(
            name in text or (len(name) == 3 and name[:2] in text) for name in TWELVE_SINSAL_ORDER
        ), text
    assert all(text.endswith("요.") for text in pool["body"].values())


@pytest.mark.parametrize(
    ("ilju", "luck", "name"),
    [
        (B.SA, B.CHUK, "화개살"), (B.MYO, B.CHUK, "월살"),
        (B.JA, B.MI, "천살"), (B.O, B.MI, "반안살"),
    ],
)
def test_daily_note_uses_ilju_trine(ilju: B, luck: B, name: str) -> None:
    simple = _simple(LUCK_SINSAL_EFFECTIVE_FROM)
    body = simple["luck_sinsal"]["body"][name]
    assert SR.luck_sinsal_note(ilju, luck, simple, "month") == (
        f"이번 달 가까운 관계와 생활에서는 {body}"
    )
    assert SR.luck_sinsal_note(ilju, luck, simple, "year") == (
        f"올해 가까운 관계와 생활에서는 {body}"
    )


def test_daily_note_absent_outside_storage_branches_and_old_contract() -> None:
    simple = _simple(LUCK_SINSAL_EFFECTIVE_FROM)
    # 반례: 문장이 없는 12신살(왕지·생지 해와 달)에는 붙지 않는다.
    for luck in (B.JA, B.O, B.MYO, B.YU, B.IN, B.SIN, B.SA, B.HAE):
        assert all(SR.luck_sinsal_note(ilju, luck, simple, "year") is None for ilju in B)
    # 과거 계약(키 없음)은 None·빈 목록.
    old = _simple(LUCK_SINSAL_EFFECTIVE_FROM - dt.timedelta(days=1))
    assert SR.luck_sinsal_note(B.SA, B.CHUK, old, "month") is None
    assert SR.year_zodiac_lines(B.MI, old) == []


def test_daily_zodiac_lines_cover_four_trines_in_storage_years() -> None:
    simple = _simple(LUCK_SINSAL_EFFECTIVE_FROM)
    lines = SR.year_zodiac_lines(B.MI, simple)
    assert len(lines) == 4
    body = simple["luck_sinsal"]["body"]
    joined = "\n".join(lines)
    assert f"돼지띠·토끼띠·양띠라면 올해 바깥 일과 사회생활에서 {body['화개살']}" in joined
    assert f"뱀띠·닭띠·소띠라면 올해 바깥 일과 사회생활에서 {body['월살']}" in joined
    assert f"원숭이띠·쥐띠·용띠라면 올해 바깥 일과 사회생활에서 {body['천살']}" in joined
    assert f"호랑이띠·말띠·개띠라면 올해 바깥 일과 사회생활에서 {body['반안살']}" in joined
    # 반례: 午년(2026)에는 문장이 있는 이름이 없어 한 줄도 없다.
    assert SR.year_zodiac_lines(B.O, simple) == []


def test_daily_board_lines_appear_only_when_branch_is_storage() -> None:
    """丑월(2027-01-10) 일주별 이번 달 줄·未년(2027-03-01) 일주별 올해 줄과 조건 줄에만 붙는다."""
    lead_m, lead_y = "이번 달 가까운 관계와 생활에서는", "올해 가까운 관계와 생활에서는"

    def board(d: dt.date):
        return compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))

    nov, jan, mar = board(dt.date(2026, 11, 23)), board(dt.date(2027, 1, 10)), board(
        dt.date(2027, 3, 1)
    )
    def month_notes(b) -> list[str]:
        return [n.note for f in b.month_flow for n in f.ilju_notes]

    def year_notes(b) -> list[str]:
        return [n.note for f in b.year_flow for n in f.ilju_notes]

    # 亥월·午년(2026-11-23): 어느 줄에도 없다.
    assert not any(lead_m in n for n in month_notes(nov))
    assert not any(lead_y in n for n in year_notes(nov))
    assert all(len(f.conditions) == 4 for f in nov.year_flow)
    # 丑월(세운은 아직 午): 이번 달 줄 60일주 전부, 올해 줄에는 없다.
    assert len(month_notes(jan)) == 60 and all(lead_m in n for n in month_notes(jan))
    assert not any(lead_y in n for n in year_notes(jan))
    # 未년 寅월: 올해 줄 60일주 전부 + 조건 줄 4개 추가, 이번 달 줄에는 없다.
    assert len(year_notes(mar)) == 60 and all(lead_y in n for n in year_notes(mar))
    assert all(len(f.conditions) == 8 for f in mar.year_flow)
    assert not any(lead_m in n for n in month_notes(mar))


def test_daily_decision_unchanged_by_luck_sinsal_layer() -> None:
    """문체 전용 — 같은 날짜를 이전 사전으로 계산한 보드와 사건·점수가 같다."""
    d = dt.date(2027, 1, 10)
    ctx = M.build_day_context(d)
    new = compute_board_v2(ctx, M.load_daily_dicts_for(d))
    old = compute_board_v2(
        ctx, M.load_daily_dicts_for(LUCK_SINSAL_EFFECTIVE_FROM - dt.timedelta(days=1)),
    )
    skip = {"month_flow", "year_flow", "content_version"}
    assert new.model_dump(exclude=skip) == old.model_dump(exclude=skip)
    assert new.content_version.split("|")[1] == "dict.v1.24"
    # 반례: 문장이 붙는 줄은 실제로 달라졌다(비교가 빈 비교가 아님).
    assert new.month_flow != old.month_flow


# ── 7. 채팅 입력 직렬화 — 블록·지침·인연 범위가 실제로 실린다 ──────────────────


def _payload(granularity: Granularity, start: str, end: str):
    from pathlib import Path as _Path  # noqa: PLC0415

    from saju_engines import EventEngineV2  # noqa: PLC0415
    from saju_engines.context_reducer import build_llm_input  # noqa: PLC0415
    from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: PLC0415

    chart = calculate(BirthInput(
        calendar_type="solar", birth_date="1983-05-05", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date=dt.date(2026, 11, 21),
    ))
    scorer = EventEngineV2(_Path(__file__).resolve().parents[2] / "dictionaries")
    candidates = scorer.score_legacy(chart, levels={GanjiLevel.YEAR})
    return build_llm_input(
        "내년 이직운 어때?", _intent(granularity, start, end), chart, candidates, [], scorer,
        today=dt.date(2026, 11, 21),
    )


def test_chat_payload_carries_year_sinsal_block_and_palace_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from saju_engines import period_v2_config  # noqa: PLC0415
    from saju_engines.context_reducer import serialize_with_guard  # noqa: PLC0415

    payload = _payload(Granularity.YEAR, "2027-01-01", "2027-12-31")
    assert payload.year_sinsal_context[1] == YEAR_SINSAL_HEADER
    text, _tokens = serialize_with_guard(payload, "chat_single")
    assert YEAR_SINSAL_HEADER in text and YEAR_SINSAL_INSTRUCTION in text
    assert "- 2027년 丁未: 띠 기준 화개살(= 날삼재) · 일지 기준 월살" in text
    # 연 단위 사건 질문은 결·태도만(compact).
    assert "    태도: " in text and "    장면: " not in text
    # 명식 구조 블록 기둥 줄의 인연 범위와 사용 규칙.
    assert "인연 범위(보조): 사적으로 깊은 관계 — 배우자·연인·가장 가까운 친구" in text
    assert PALACE_SCOPE_RULE in text
    # 반례: 월 단위 질문에는 블록이 없다.
    month = _payload(Granularity.MONTH, "2027-03-01", "2027-03-31")
    assert month.year_sinsal_context == []
    assert YEAR_SINSAL_HEADER not in serialize_with_guard(month, "chat_single")[0]
    # 반례: 플래그를 끄면 연 단위 질문에도 싣지 않는다.
    monkeypatch.setattr(period_v2_config, "YEAR_SINSAL_FLOW_ENABLED", False)
    assert _payload(Granularity.YEAR, "2027-01-01", "2027-12-31").year_sinsal_context == []
