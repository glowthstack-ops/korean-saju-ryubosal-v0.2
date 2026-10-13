"""도화 정비(2026-10-13 데굴님 확정) — 판정 조건·시주 미상·중복 가산·세 소비처 회귀 고정.

정비 기준: 글자 보유(사정지=가도화)와 도화 성립(진도화)을 구분하고 성립한 판정만 '도화'로 쓴다.
월담도화=시지 진도화(하위 유형, 별도 가산 없음), 나체도화=판정 보류, 십성 조합=성립 지지 본기
십성(일간 기준) 5군. 해석 문구는 기본으로 싣는다 — 검수는 실제 사용 결과(풀이)로 판단하므로
reviewed 는 기록용일 뿐 노출 조건이 아니며, 노출 로그(dohwa_text_exposed)로 실답을 찾는다.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.compatibility_engine import _ATTRACTION_WEIGHT, analyze_compatibility
from saju_engines.context_reducer import build_birth_summary
from saju_engines.dictionaries import DohwaTextFile, _lint_dohwa_text
from saju_engines.dohwa import _DOHWA_TEXT_PATH, analyze_dohwa, load_dohwa_texts
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.structural_context import dohwa_structure_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatSignalKind
from saju_shared_types.dohwa import DohwaTenGodGroup
from saju_shared_types.intent import Domain, IntentJson, QueryType


def _chart(d: date, t: str | None, gender: str = "female"):
    return calculate(BirthInput(
        birth_date=d, birth_time=t, birth_time_unknown=t is None,
        birth_place_name="서울", gender=gender,
    ))


# 표본(실측): 甲寅·丙子·丁未·庚子 — 월지 子·시지 子 진도화(일지 未 기준 亥卯未국), 둘 다 편관.
_TWO_POS = (date(1975, 1, 1), "01:30:00")
# 甲寅·丙子·丁未·癸卯 — 월지 子(일지 未 기준, 편관=관성도화) + 시지 卯(연지 寅 기준, 편인=인성도화).
_WOLLDAM = (date(1975, 1, 1), "07:30:00")
# 甲寅·丙子·壬子·庚子 — 子 셋(사정지)만 있고 진도화 없음.
_SAJEONG_ONLY = (date(1975, 1, 6), "01:30:00")
# 甲寅·丁丑·壬戌·癸卯 — 시지 卯가 연지 寅·일지 戌 두 기준(寅午戌국)에서 겹쳐 성립.
_DUAL_BASE = (date(1975, 1, 16), "07:30:00")


def _intent(domain: Domain = Domain.RELATIONSHIP, qt: QueryType = QueryType.DOMAIN_ANALYSIS):
    return IntentJson(intent_id="t", query_type=qt, domain=domain)


# ── 판정 조건 ──────────────────────────────────────────────────────────────────


def test_establishment_records_base_and_position_per_slot():
    """진도화는 자리마다 기준 지지·삼합국·본기 십성·십성군을 기록한다(여러 자리면 각각)."""
    prof = analyze_dohwa(_chart(*_WOLLDAM))
    assert prof is not None
    got = {(e.position, e.branch): e for e in prof.established}
    assert set(got) == {("month", "子"), ("hour", "卯")}
    month, hour = got[("month", "子")], got[("hour", "卯")]
    assert [(b.slot, b.branch, b.trine) for b in month.bases] == [("day", "未", "亥卯未")]
    assert [(b.slot, b.branch, b.trine) for b in hour.bases] == [("year", "寅", "寅午戌")]
    officer, resource = DohwaTenGodGroup.OFFICER, DohwaTenGodGroup.RESOURCE
    assert (month.ten_god, month.group, month.group_label) == ("편관", officer, "관성도화")
    assert (hour.ten_god, hour.group, hour.group_label) == ("편인", resource, "인성도화")


def test_two_bases_on_same_slot_are_one_establishment():
    """같은 자리가 연지·일지 두 기준에서 겹치면 1건에 기준 둘을 함께 기록한다(중복 건 금지)."""
    prof = analyze_dohwa(_chart(*_DUAL_BASE))
    assert prof is not None
    hour = [e for e in prof.established if e.position == "hour"]
    assert len(hour) == 1
    assert {(b.slot, b.branch) for b in hour[0].bases} == {("year", "寅"), ("day", "戌")}


def test_sajeong_only_is_not_dohwa():
    """子午卯酉 보유(사정지)만으로는 진도화가 아니다 — 표지로만 남는다."""
    prof = analyze_dohwa(_chart(*_SAJEONG_ONLY))
    assert prof is not None
    assert prof.established == []
    assert [(m.position, m.branch) for m in prof.sajeong_markers] == [
        ("month", "子"), ("day", "子"), ("hour", "子"),
    ]


def test_wolldam_is_hour_establishment_subtype():
    """월담도화 = 시지 진도화. 별도 건이 아니라 시지 성립 건의 표시다."""
    prof = analyze_dohwa(_chart(*_WOLLDAM))
    assert prof is not None
    assert prof.wolldam_status == "established"
    assert [e.position for e in prof.established if e.wolldam] == ["hour"]
    assert len(prof.established) == 2  # 월담으로 건수가 늘지 않는다


def test_hour_unknown_wolldam_undetermined():
    """시주 미상이면 월담도화는 미확정 — 없음으로 단정하지 않고, 다른 자리 판정은 유지한다."""
    prof = analyze_dohwa(_chart(_WOLLDAM[0], None))
    assert prof is not None
    assert prof.hour_known is False
    assert prof.wolldam_status == "undetermined"
    assert all(e.position != "hour" for e in prof.established)
    assert any(e.position == "month" for e in prof.established)


def test_wolldam_not_established_when_hour_known():
    prof = analyze_dohwa(_chart(*_SAJEONG_ONLY))
    assert prof is not None and prof.wolldam_status == "not_established"


# ── 해석 사전 ──────────────────────────────────────────────────────────────────


def test_texts_cover_types_and_groups_and_stay_unreviewed():
    """유형 3종·십성군 5종을 모두 싣고, 검수 전(reviewed:false)이어도 로더가 돌려준다."""
    texts = load_dohwa_texts()
    type_keys = {k for k in texts if k.startswith("type:")}
    assert type_keys == {"type:sajeong", "type:jin", "type:wolldam", "type:naked"}
    assert texts["type:naked"]["feature"] == "가식 없는 솔직함·꾸미지 않은 매력"
    assert {k for k in texts if k.startswith("combo:")} == {
        f"combo:{g.value}" for g in DohwaTenGodGroup
    }
    assert all(v["reviewed"] is False for v in texts.values())
    assert texts["combo:관성"]["label"] == "관성도화"
    assert texts["combo:인성"]["label"] == "인성도화"


def test_lint_catches_wrong_label_and_ten_gods():
    data = json.loads(_DOHWA_TEXT_PATH.read_text(encoding="utf-8"))
    data["combos"][3]["label"] = "편관도화"
    data["combos"][4]["tenGods"] = ["편인", "식신"]
    errors = _lint_dohwa_text(DohwaTextFile.model_validate(data))
    assert any("라벨" in e for e in errors)
    assert any("소속 십성" in e for e in errors)


# ── 풀이 블록 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("intent", "question", "shown"),
    [
        (_intent(Domain.RELATIONSHIP), "", True),
        (_intent(Domain.GENERAL, QueryType.CHART_ANALYSIS), "", True),
        (_intent(Domain.CAREER), "내 도화가 궁금해", True),  # 직접 질문 예외
        (_intent(Domain.CAREER), "이직해도 될까?", False),
        (_intent(Domain.GENERAL, QueryType.FORTUNE_OVERVIEW), "오늘 운세", False),
    ],
)
def test_block_gating(intent, question, shown):
    lines, _keys = dohwa_structure_lines(analyze_dohwa(_chart(*_WOLLDAM)), intent, question)
    assert bool(lines) is shown


def test_block_carries_texts_by_default():
    """해석 문구는 기본으로 싣는다(reviewed:false 여도) — 성립 사실·문구·노출 키, 월담 가산 없음."""
    lines, keys = dohwa_structure_lines(analyze_dohwa(_chart(*_WOLLDAM)), _intent())
    text = "\n".join(lines)
    assert "진도화 성립: 월지 子 [일지 未 기준(亥卯未국)] — 관성도화(본기 편관)" in text
    assert "진도화 성립: 시지 卯 [연지 寅 기준(寅午戌국)] — 인성도화(본기 편인)" in text
    assert "품격·신뢰·카리스마" in text and "신비로움·내면의 깊이·보호본능 자극" in text
    assert "월담도화: 성립(시지 진도화) — 외부로 확산되는 매력·폭넓은 관심과 유혹" in text
    assert text.count("월담도화: 성립") == 1
    assert "별도의 추가 매력으로 세지 않는다" in text
    assert "뚜렷한 개성·자기주장·눈에 띄는 왕지 성향" in text
    assert keys == ["combo:관성", "combo:인성", "type:wolldam", "type:sajeong"]


def test_reviewed_flag_does_not_gate_exposure(monkeypatch):
    """reviewed 는 검토 상태 기록용 — 값이 무엇이든 노출은 같다(2026-10-13 데굴님 정정)."""
    import saju_engines.dohwa as dohwa_mod

    base_lines, base_keys = dohwa_structure_lines(analyze_dohwa(_chart(*_WOLLDAM)), _intent())
    texts = {k: dict(v) for k, v in load_dohwa_texts().items()}
    for v in texts.values():
        v["reviewed"] = True
    monkeypatch.setattr(dohwa_mod, "load_dohwa_texts", lambda: texts)
    lines, keys = dohwa_structure_lines(analyze_dohwa(_chart(*_WOLLDAM)), _intent())
    assert (lines, keys) == (base_lines, base_keys)


def test_block_sajeong_only_limits_negation_to_natal():
    """진도화가 없으면 '현재 원국에서 확인되지 않음'으로만 한정한다.

    운에서 들어오는 도화나 아직 판정하지 않는 유형까지 부정하지 않는다.
    """
    lines, _keys = dohwa_structure_lines(analyze_dohwa(_chart(*_SAJEONG_ONLY)), _intent())
    text = "\n".join(lines)
    assert "현재 분석 대상 원국에서 진도화가 확인되지 않음" in text
    assert "운에서 들어오는 도화나 이 블록이 판정하지 않는 다른 도화 유형까지" in text
    assert "'도화가 있다'고 말하지 말 것" not in text  # 전면 부정 지시 금지(운 도화·미구현 유형)
    assert "도화 성립이나 이성적 매력의 직접 근거로 쓰지 않는다" in text


def test_block_hour_unknown_line():
    lines, _ = dohwa_structure_lines(analyze_dohwa(_chart(_WOLLDAM[0], None)), _intent())
    assert any(ln.startswith("월담도화: 미확정(시주 미상)") for ln in lines)


def test_chat_logs_exposed_text_keys():
    """채팅 구조 블록은 노출된 도화 문구 키를 스레드·턴과 함께 로그로 남긴다(실답 검수 경로).

    앱 로거는 propagate=False 라 caplog 로는 거짓 통과한다 — 로거에 직접 핸들러를 붙인다.
    """
    from saju_api.services import chat_service

    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _H()
    prev_level = chat_service._logger.level
    chat_service._logger.setLevel(logging.INFO)  # 테스트 환경 유효 레벨은 WARNING
    chat_service._logger.addHandler(handler)
    try:
        chat_service._structural_context(
            _chart(*_WOLLDAM), _intent(), date(2026, 10, 13), "",
            thread_id="t-dohwa", turn_no=3,
        )
    finally:
        chat_service._logger.removeHandler(handler)
        chat_service._logger.setLevel(prev_level)
    msgs = [r.getMessage() for r in records if "dohwa_text_exposed" in r.getMessage()]
    assert msgs and "thread=t-dohwa" in msgs[0] and "turn=3" in msgs[0]
    assert "combo:관성" in msgs[0]


# ── 소비처: 결혼 자원·궁합 ────────────────────────────────────────────────────


def test_marriage_resource_uses_established_dohwa_only():
    """결혼 자원 — 글자 보유(사정지)로 도화를 부여하지 않는다. 도화·홍염은 각자의 조건."""
    sajeong = analyze_marriage_resource(_chart(*_SAJEONG_ONLY))
    assert sajeong.dohwa_established is False
    assert not any("도화(진도화 성립)" in f for f in sajeong.flags)
    est = analyze_marriage_resource(_chart(*_WOLLDAM))
    assert est.dohwa_established is True and est.charm_present is True
    assert any(f.startswith("도화(진도화 성립)") for f in est.flags)
    assert est.day_branch_tendency == "" or "도화형" not in est.day_branch_tendency


def test_marriage_day_branch_label_has_no_dohwa_type():
    """일지 왕지 기질 — 도화형·이성 인연·끌림 서술 없이 개성·자기주장 성향으로만."""
    mr = analyze_marriage_resource(_chart(*_SAJEONG_ONLY))  # 일지 子
    assert mr.day_branch_group == "wangji"
    tendency = mr.day_branch_tendency
    assert "도화형" not in tendency
    assert "이성" not in tendency and "인연" not in tendency and "끌림" not in tendency
    assert "개성·자기주장" in tendency


def test_compat_one_sided_dohwa_is_personal_and_not_attraction():
    """한쪽 도화는 그 사람의 보조 신호일 뿐 두 사람의 끌림 점수에 들어가지 않는다."""
    a, b = _chart(*_WOLLDAM), _chart(*_SAJEONG_ONLY, gender="male")
    sa, sb = build_birth_summary(a), build_birth_summary(b)
    rep = analyze_compatibility(a, b, sa.useful_gods, sb.useful_gods)
    assert rep is not None
    dohwa = [s for s in rep.signals if s.kind is CompatSignalKind.SINSAL_DOHWA]
    assert [s.label for s in dohwa] == ["본인 도화 성립(개인·보조)"]
    assert all(s.auxiliary for s in dohwa)
    assert "상호 끌림 판정이 아니다" in dohwa[0].detail
    assert CompatSignalKind.SINSAL_DOHWA not in _ATTRACTION_WEIGHT
    assert rep.attraction_score == sum(_ATTRACTION_WEIGHT.get(s.kind, 0) for s in rep.signals)


# ── 운 도화 × 십성군(2026-10-13) — 기존 운 진도화 판정 재사용, 원국과 구분, 중복 가산 없음 ──


def _luck_day(birth: tuple, label: str):
    from saju_api.services.manse_service import luck_days

    b = BirthInput(birth_date=birth[0], birth_time=birth[1], birth_place_name="서울",
                   gender="female")
    y, m = int(label[:4]), int(label[5:7])
    return next(p for p in luck_days(b, y, m) if p.label == label)


def test_luck_dohwa_uses_existing_judgment_and_luck_branch_ten_god():
    """운 진도화(sinsal_for_luck '도화')를 그대로 쓰고 운 지지 본기 십성으로 군을 붙인다.

    십성은 원국 일간 기준(LuckPillar.branch_ten_god)이다.
    """
    from saju_engines.dohwa import analyze_luck_dohwa

    pillar = _luck_day(_WOLLDAM, "2026-10-05")  # 壬子 — 일지 未(亥卯未) 기준 子
    assert "도화" in [s.name for s in pillar.luck_sinsal]
    ld = analyze_luck_dohwa(_chart(*_WOLLDAM), pillar, "일운")
    assert ld is not None
    assert (ld.level, ld.period_label, ld.ganji, ld.branch) == ("일운", "2026-10-05", "壬子", "子")
    assert [(b.slot, b.branch) for b in ld.bases] == [("day", "未")]
    assert (ld.ten_god, ld.group_label) == ("편관", "관성도화")


def test_luck_dohwa_none_when_not_judged():
    from saju_engines.dohwa import analyze_luck_dohwa

    pillar = _luck_day(_WOLLDAM, "2026-10-01")  # 戊申 — 운 도화 아님
    assert analyze_luck_dohwa(_chart(*_WOLLDAM), pillar, "일운") is None


def test_luck_dohwa_two_bases_one_line_no_double_count():
    """연지 寅·일지 戌 두 기준이 같은 卯를 가리켜도 1건·1줄(가산 없음)."""
    from saju_engines.chart_interpretation import build_luck_grounding
    from saju_engines.dohwa import analyze_luck_dohwa

    chart = _chart(*_DUAL_BASE)  # 壬 일간
    pillar = _luck_day(_DUAL_BASE, "2026-10-08")  # 乙卯
    ld = analyze_luck_dohwa(chart, pillar, "일운")
    assert ld is not None
    assert {(b.slot, b.branch) for b in ld.bases} == {("year", "寅"), ("day", "戌")}
    assert (ld.ten_god, ld.group_label) == ("상관", "식상도화")
    g = build_luck_grounding(chart, pillar)
    dohwa_lines = [ln for ln in g["sinsal_lines"] if "도화(운 진도화)" in ln]
    assert len(dohwa_lines) == 1
    assert g["dohwa_text_keys"] == ["luck_combo:식상"]


def test_luck_dohwa_line_marks_luck_scope_and_carries_text():
    """운 도화 줄 — 기간·기준·십성군·'운에 적용된 설명' 문구·평생 매력 금지 규칙."""
    from saju_engines.chart_interpretation import build_luck_grounding

    g = build_luck_grounding(_chart(*_WOLLDAM), _luck_day(_WOLLDAM, "2026-10-05"))
    line = next(ln for ln in g["sinsal_lines"] if "도화(운 진도화)" in ln)
    assert "2026-10-05 壬子의 지지 子 [일지 未 기준(亥卯未국)] — 관성도화(운 지지 본기 편관" in line
    assert "운에 적용된 설명 — 매력의 핵심: 품격·신뢰·카리스마" in line
    assert "타고난 성향이나 평생의 매력으로 설명하지 말고 원국 도화와 구분" in line
    assert g["dohwa_text_keys"] == ["luck_combo:관성"]


def test_natal_block_and_luck_lines_are_separate_layers():
    """원국 도화 블록은 원국 판정만, 운 도화는 기간 블록 줄에만 — 서로 섞지 않는다."""
    lines, _ = dohwa_structure_lines(analyze_dohwa(_chart(*_WOLLDAM)), _intent())
    natal = "\n".join(lines)
    assert "운 진도화" not in natal and "원국 기준(운 미반영)" in natal


def test_period_fortune_carries_luck_dohwa_keys():
    """일 총운(PeriodFortune) — 운 도화 문구 키가 실려 노출 로그 재료가 된다."""
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity, TimeRange

    b = BirthInput(birth_date=_WOLLDAM[0], birth_time=_WOLLDAM[1], birth_place_name="서울",
                   gender="female")
    intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-10-05", end="2026-10-05"),
    )
    pf = chat_service._build_period_fortune(b, intent, date(2026, 10, 5), "daily")
    assert pf is not None
    assert pf.dohwa_text_keys == ["luck_combo:관성"]
    assert any("도화(운 진도화)" in ln for ln in pf.sinsal_lines)


# ── 주제별 기간 질문(연애·매력)에 운 도화 연결(2026-10-13) — 총운과 같은 판정·문구, 중복 없음 ──


def _range_intent(gran, start, end=None, domain=Domain.RELATIONSHIP, dates=None):
    from saju_shared_types.intent import TimeRange

    return IntentJson(
        intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS, domain=domain,
        time_range=TimeRange(type="absolute", granularity=gran, start=start,
                             end=end or start, dates=dates or []),
    )


def _birth(spec: tuple) -> BirthInput:
    return BirthInput(birth_date=spec[0], birth_time=spec[1], birth_place_name="서울",
                      gender="female")


def test_relationship_day_question_gets_same_line_as_period_fortune():
    """'10월 5일 연애운'과 '10월 5일 운세'의 운 도화 줄이 같다.

    판정·십성군·기간 규칙을 공용 빌더로 공유한다.
    """
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    b = _birth(_WOLLDAM)
    ctx = chat_service._luck_dohwa_context(
        b, _chart(*_WOLLDAM), _range_intent(Granularity.DAY, "2026-10-05"), "연애운", set(),
    )
    assert ctx and ctx[0].startswith("[질문 기간 운 도화 — 원국 도화와 별개 층")
    overview = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=_range_intent(Granularity.DAY, "2026-10-05").time_range,
    )
    pf = chat_service._build_period_fortune(b, overview, date(2026, 10, 5), "daily")
    assert pf is not None
    pf_line = next(ln for ln in pf.sinsal_lines if "도화(운 진도화)" in ln)
    assert ctx[1:] == [pf_line]
    assert "타고난 성향이나 평생의 매력으로 설명하지 말고" in ctx[1]


@pytest.mark.parametrize(
    ("domain", "question", "shown"),
    [
        (Domain.RELATIONSHIP, "연애운", True),
        (Domain.CAREER, "이직운 어때", False),
        (Domain.CAREER, "이 날 내 매력이 잘 보일까", True),  # 매력 직접 질문 예외
    ],
)
def test_luck_dohwa_context_gating(domain, question, shown):
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    ctx = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM),
        _range_intent(Granularity.DAY, "2026-10-05", domain=domain), question, set(),
    )
    assert bool(ctx) is shown


def test_luck_dohwa_context_skips_period_already_covered():
    """기간 총운에 이미 실린 날짜는 건너뛴다 — 같은 운 도화 중복 삽입 금지."""
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    ctx = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM), _range_intent(Granularity.DAY, "2026-10-05"),
        "연애운", {"2026-10-05"},
    )
    assert ctx == []


def test_luck_dohwa_context_only_asked_days():
    """질문한 날만 — 범위 안 운 도화 날(5일)만 싣고 범위 밖 날(8일 乙卯)은 싣지 않는다."""
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    ctx = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM),
        _range_intent(Granularity.DAY, "2026-10-04", "2026-10-06"), "연애운", set(),
    )
    body = "\n".join(ctx[1:])
    assert "2026-10-05 壬子" in body and "2026-10-08" not in body
    assert len(ctx) == 2


def test_luck_dohwa_context_month_and_year():
    """월(2026-12 庚子)·연(2032 壬子) 단위 질문 — 월운·세운 운 도화를 같은 규칙으로 싣는다."""
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    month = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM), _range_intent(Granularity.MONTH, "2026-12"),
        "12월 연애운", set(),
    )
    assert len(month) == 2 and "월운" in month[1] and "2026-12 庚子의 지지 子" in month[1]
    year = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM), _range_intent(Granularity.YEAR, "2032"),
        "2032년 연애운", set(),
    )
    assert len(year) == 2 and "세운" in year[1] and "2032 壬子의 지지 子" in year[1]


def test_luck_dohwa_context_empty_without_dohwa_or_range():
    from saju_api.services import chat_service
    from saju_shared_types.intent import Granularity

    none_day = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM), _range_intent(Granularity.DAY, "2026-10-01"),
        "연애운", set(),
    )
    assert none_day == []
    too_long = chat_service._luck_dohwa_context(
        _birth(_WOLLDAM), _chart(*_WOLLDAM),
        _range_intent(Granularity.DAY, "2026-10-01", "2026-11-30"), "연애운", set(),
    )
    assert too_long == []



# ── 나체도화(2026-10-13 데굴님 지시) — 일지 목욕 정의 + 포스텔러 소개 견해(천충지충) 결합 ──
_NAKED_PRESENT = (date(1980, 2, 21), "12:40:00")  # 庚申·戊寅·甲子·庚午 — 시주 庚午 천충지충
_NAKED_ABSENT = (date(1980, 2, 21), "05:30:00")   # 庚申·戊寅·甲子·丙寅 — 천충지충 없음
_NAKED_UNKNOWN_HOUR = (date(1980, 2, 21), None)   # 시주 미상


def test_naked_days_are_exactly_bathing_day_pillars():
    """일지가 일간의 12운성 목욕인 일주는 60갑자 중 甲子·乙巳·庚午·辛亥뿐이다(엔진값 기준)."""
    from saju_engines.dictionaries import _expected_twelve_stage
    from saju_shared_types.enums import Branch, Stem

    stems, branches = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
    days = {
        stems[i % 10] + branches[i % 12] for i in range(60)
        if _expected_twelve_stage(Stem(stems[i % 10]), Branch(branches[i % 12])) == "목욕"
    }
    assert days == {"甲子", "乙巳", "庚午", "辛亥"}


@pytest.mark.parametrize(
    ("spec", "status", "positions"),
    [
        (_NAKED_PRESENT, "present", ["hour"]),
        (_NAKED_ABSENT, "absent", []),
        (_NAKED_UNKNOWN_HOUR, "undetermined", []),
    ],
)
def test_naked_dohwa_clash_status(spec, status, positions):
    prof = analyze_dohwa(_chart(*spec))
    assert prof is not None and prof.naked is not None
    assert prof.naked.day_ganji == "甲子"
    assert (prof.naked.clash_status, prof.naked.clash_positions) == (status, positions)


def test_non_bathing_day_has_no_naked():
    prof = analyze_dohwa(_chart(*_WOLLDAM))  # 丁未 일주
    assert prof is not None and prof.naked is None


@pytest.mark.parametrize(
    ("spec", "phrase"),
    [
        (_NAKED_PRESENT, "천충지충 동반(시주) — 일지 목욕만으로 성립한다는 견해와 천충지충을 추가"),
        (_NAKED_ABSENT, "천충지충 미동반 — 일지 목욕만으로 성립한다는 견해에 해당"),
        (_NAKED_UNKNOWN_HOUR, "천충지충 동반 여부 미확정(시주 미상"),
    ],
)
def test_naked_block_line(spec, phrase):
    """블록 — 성립·견해 구분·성향 문구·별도 유형(가산 금지) 규칙, 노출 키."""
    lines, keys = dohwa_structure_lines(analyze_dohwa(_chart(*spec)), _intent())
    line = next(ln for ln in lines if ln.startswith("나체도화:"))
    assert "성립(일지 목욕 — 甲子 일주)" in line and phrase in line
    assert "가식 없는 솔직함·꾸미지 않은 매력" in line
    assert "진도화와 별도 유형이다" in line
    assert "type:naked" in keys


def test_naked_not_added_to_impression_score():
    """나체도화는 매력 점수에 더하지 않는다 — 외적 인상 도화계 신호는 진도화·홍염뿐."""
    from saju_engines.external_impression import analyze_external_impression

    prof = analyze_external_impression(_chart(*_NAKED_PRESENT))
    codes = {s.code for s in prof.signals if s.category == "peach"}
    assert codes <= {"DAY_BRANCH_PEACH", "ACTUAL_DOHWA_OR_HONGYEOM"}
    assert not any("나체" in s.legacy_ko or "나체" in s.modern_ko for s in prof.signals)
