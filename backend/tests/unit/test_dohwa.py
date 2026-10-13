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
    assert type_keys == {"type:sajeong", "type:jin", "type:wolldam"}
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
