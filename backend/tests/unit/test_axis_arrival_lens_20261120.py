"""축 글자 도래 층 — 렌즈 선택·원국×운 판정·문구 사전·채팅/리포트 배선 검증 (2026-11-20).

데굴님이 제공한 영상 스크립트(합격은 관성=자리·인성=자격 두 축, 원국에 없던 글자가 운에서 들어옴·
누르는데 받칠 글자가 들어옴·대운의 10년 바닥·이미 줄 선 구조)를 대조해 만든 서술층
(`saju_engines.axis_arrival_lens`)을 지킨다. 판정은 기존 엔진 값(세력·부재·과다·구조 패턴·교운 가중)
이고 이 층은 주제의 말로 옮기기만 한다 — 점수·판정 불변, 당락·시기 확정 금지, 부재 선언 금지.
대조 문서: doc/v2_2/EXTERNAL_TEXT_GAP_POSITION_SEAL_VIDEO.md.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import json
from datetime import date, time
from pathlib import Path

import pytest

from saju_api.services import chat_service, report_service
from saju_api.services.manse_service import calculate
from saju_engines import axis_arrival_lens as A
from saju_engines import period_v2_config
from saju_engines.dictionaries import (
    AxisArrivalLensFile,
    _lint_axis_arrival_lens,
    _structure_pattern_ids,
    lint_dictionaries,
    validate_dictionaries,
)
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_T = date(2026, 11, 20)

# 己 일간 신약 — 관성은 드러난 글자 없음, 인성 있음(희신), 재성 과다.
_ABSENT_OFFICER = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울", gender="male",
)
_UNKNOWN_HOUR = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=None, birth_time_unknown=True,
    birth_place_name="서울", gender="male",
)
# 스크립트 코너 명식 — 己酉 丙子 壬戌 辛丑(관성·인성이 이어진 구조, 2020년대 庚 대운).
_CHAIN = BirthInput(
    birth_date=date(1969, 12, 13), birth_time=time(2, 30), birth_place_name="서울", gender="male",
)
# 스크립트 코너 명식 — 癸酉 己未 甲寅 辛未(2020년대 중반부터 癸亥 대운 = 인성이 겹으로 놓임).
_DECADE_SEAL = BirthInput(
    birth_date=date(1993, 8, 1), birth_time=time(14, 30), birth_place_name="서울", gender="female",
)
# 스크립트 코너 명식 — 辛酉 庚寅 辛酉 辛卯(관성·인성 모두 드러난 글자 없음).
_BOTH_ABSENT = BirthInput(
    birth_date=date(1981, 2, 12), birth_time=time(6, 30), birth_place_name="서울", gender="male",
)


@pytest.fixture(scope="module")
def absent_chart():
    return calculate(_ABSENT_OFFICER)


def _text(lines: list[str]) -> str:
    return "\n".join(lines)


# ── 렌즈 선택 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "event_key, domain, selection, expected",
    [
        ("education_admission", "education", False, A.LENS_POSITION),
        ("job_gain", "career", False, A.LENS_POSITION),
        ("promotion", "career", False, A.LENS_POSITION),
        ("business_start", "career", False, A.LENS_BUSINESS),
        ("business_expansion", "wealth", False, A.LENS_BUSINESS),
        ("wealth_change", "wealth", False, A.LENS_WEALTH),
        (None, "education", False, A.LENS_POSITION),
        (None, "wealth", False, A.LENS_WEALTH),
        ("contract_document", "career", True, A.LENS_POSITION),  # 공모·지원사업
        # 반례 — 다른 층이 맡는 사건·도메인에는 렌즈가 없다.
        ("career_change", "career", False, None),   # 직장 운 결 층
        ("windfall", "wealth", False, None),        # 횡재 신호 층
        ("marriage_signal", "relationship", False, None),
        (None, "career", False, None),
        (None, "health", False, None),
        # 사건이 정해지면 도메인으로 넓히지 않는다.
        ("education_completion", "education", False, None),
    ],
)
def test_lens_for_follows_event_then_domain(event_key, domain, selection, expected) -> None:
    assert A.lens_for(event_key, domain, selection=selection) == expected


@pytest.mark.parametrize(
    "gender, expected",
    [
        ("female", A.LENS_CHILDREN_FEMALE),  # 여성 자녀성 = 식상
        ("male", A.LENS_CHILDREN_MALE),      # 남성 자녀성 = 관성
        ("unknown", None),                   # 반례 — 성별 미상이면 자녀성을 정하지 않는다
        (None, None),
    ],
)
def test_childbirth_lens_follows_gender(gender, expected) -> None:
    assert A.lens_for("childbirth", "relationship", gender=gender) == expected
    # 반례 — 출산 사건이 아니면 성별이 있어도 자녀 렌즈로 가지 않는다.
    assert A.lens_for("marriage_signal", "relationship", gender=gender) is None


@pytest.mark.parametrize(
    "domain, question, expected",
    [
        ("public_program", "정부 지원사업에 선정될 수 있을까?", True),
        ("generic", "이번 공모에 뽑힐 수 있을까?", True),
        # 반례 — 추첨·배정형은 관성·인성으로 풀 일이 아니다.
        ("generic", "이번 추첨에 당첨될까?", False),
        ("military_service", "카투사 선발될까?", False),
        ("housing_subscription", "청약 당첨될까?", False),
        (None, "공모에 뽑힐까?", False),
    ],
)
def test_judged_selection_excludes_lottery_like_domains(domain, question, expected) -> None:
    assert A.is_judged_selection(domain, question) is expected


# ── 원국 × 운 판정 ───────────────────────────────────────────────────────────


def test_absent_axis_arriving_in_monthly_luck_is_named_with_place(absent_chart) -> None:
    """원국에 드러난 관성이 없고 월운 지지로 관성이 오면 '없던 것이 들어옴' + 지지 양상 + 조언."""
    lines = A.axis_arrival_block(absent_chart, [("2027-02", "壬寅")], A.LENS_POSITION)
    body = _text(lines)
    assert lines[0].startswith("[자리·자격 구조 — 원국 × 운에서 온 글자")
    assert "원국: 관성(자리·직책·평가) — 드러난 글자 없음" in lines[1]
    assert "월운 2027-02 壬寅: 지지 寅 = 정관(관성 · 기신)" in body
    assert "세운 2027 丁未: 천간 丁 = 편인(인성 · 희신)" in body  # 달 라벨의 해 세운도 본다
    assert "[월운 2027-02 지지] 원국에 드러난 관성이 없다가 운에서 들어오는 때" in body
    assert "지지로 오는 관성 — 실제로 발을 딛는 자리 쪽" in body
    assert "천간으로 오는 인성 — 머리로 쌓는 쪽" in body
    assert "관성이 드는 때는 지켜보는 눈도 함께 늘어" in body
    assert lines[-1] == A.AXIS_LENS_RULE
    # 반례 — 인성은 원국에 있으므로 '없던 인성이 들어옴'은 싣지 않는다.
    assert "원국에 드러난 인성이 없다가" not in body
    # 반례 — 천간으로 온 관성은 없으므로 천간 관성 양상 줄은 없다.
    assert "천간으로 오는 관성" not in body


def test_next_arrival_years_replace_absence_declaration(absent_chart) -> None:
    """질문 기간 세운에 관성이 들지 않으면 '없다'가 아니라 다음에 드는 해를 싣는다."""
    lines = A.axis_arrival_block(absent_chart, [("2027", "")], A.LENS_POSITION)
    nxt = [ln for ln in lines if ln.startswith("- 세운으로 드는 다음 해")]
    assert len(nxt) == 1
    assert "관성 2034 甲寅(천간·지지)·2035 乙卯(천간·지지)" in nxt[0]
    assert "인성 " not in nxt[0]  # 인성은 2027 세운 천간에 들었으므로 다음 해를 싣지 않는다
    assert "시기의 근거로 쓰지 말 것" in nxt[0]
    profile_years = A.next_arrival_years(
        A.natal_structure_profile(absent_chart, []), "officer", 2027,
    )
    assert profile_years == ["2034 甲寅(천간·지지)", "2035 乙卯(천간·지지)"]
    # 어느 줄도 부재를 선언하지 않는다(규칙 문장 제외).
    for ln in lines[:-1]:
        assert "글자가 없" not in ln and "기회가 없" not in ln


def test_natal_chain_moves_when_lead_axis_arrives() -> None:
    """원국에 관성·인성이 이어진 구조가 있고 세운으로 관성이 오면 '줄이 함께 움직임'을 싣는다."""
    chart = calculate(_CHAIN)
    lines = A.axis_arrival_block(chart, [("2027", "")], A.LENS_POSITION)
    body = _text(lines)
    assert "이어지는 구조 — " in lines[1] and "관인상생" in lines[1]
    assert "세운 2027 丁未: 지지 未 = 정관(관성" in body
    assert "[세운 2027 지지] 원국에 관성과 인성이 이어지는 구조가 이미 서 있어" in body
    assert "대운에 인성이 놓인 10년" in body  # 庚 대운 = 인성
    # 반례 — 과다 군이 없으면 '줄이 길어 무겁다'는 덧붙지 않는다.
    assert "거쳐야 할 단계가 늘어" not in body
    # 반례 — 관성이 들지 않는 달만 보면 줄 움직임을 말하지 않는다(세운 줄이 상한을 넘겨 빠진 경우).
    many = [(str(y), "") for y in range(2027, 2027 + A.MAX_YEARS + 1)]
    capped = _text(A.axis_arrival_block(chart, many, A.LENS_POSITION))
    assert "세운 2027" not in capped and "이미 서 있어" not in capped


def test_decade_seal_is_backdrop_not_event_shape() -> None:
    """대운에 놓인 인성은 10년 배경으로만 말하고 천간·지지 양상(사건 모양)은 붙이지 않는다."""
    chart = calculate(_DECADE_SEAL)
    lines = A.axis_arrival_block(chart, [("2027", "")], A.LENS_POSITION)
    body = _text(lines)
    assert "癸亥: 천간 癸 = 정인(인성" in body and "지지 亥 = 편인(인성" in body
    assert "대운에 인성이 놓인 10년" in body
    assert "천간으로 오는 인성" not in body and "지지로 오는 인성" not in body
    # 2027 丁未 세운에는 관성·인성이 없다 — 두 군 모두 다음에 드는 해를 싣는다.
    nxt = next(ln for ln in lines if ln.startswith("- 세운으로 드는 다음 해"))
    assert "관성 2028 戊申(지지)·2029 己酉(지지)" in nxt
    assert "인성 2031 辛亥(지지)·2032 壬子(천간·지지)" in nxt


def test_bridge_replaces_plain_arrival_when_other_axis_is_excess(monkeypatch) -> None:
    """관성 과다 + 인성 없음 + 운 인성 = 다리 문구. 과다가 아니면 평범한 '없던 것이 들어옴'."""
    chart = calculate(_BOTH_ABSENT)
    plain = _text(A.axis_arrival_block(chart, [("2027", "")], A.LENS_POSITION))
    assert "원국에 드러난 인성이 없다가 운에서 들어오는 때" in plain
    assert "살인상생의 결" not in plain
    real = A.natal_structure_profile

    def _pressed(result, patterns=()):
        p = real(result, patterns)
        return dataclasses.replace(
            p, excess_groups=frozenset({"officer"}), absent_groups=frozenset({"resource"}),
        )

    monkeypatch.setattr(A, "natal_structure_profile", _pressed)
    bridged = _text(A.axis_arrival_block(chart, [("2027", "")], A.LENS_POSITION))
    assert "살인상생의 결" in bridged
    assert "원국에 드러난 인성이 없다가 운에서 들어오는 때" not in bridged


def test_daewoon_turn_care_only_near_turn(absent_chart) -> None:
    table = absent_chart.luck_cycles.daewoon_table
    turn_year = next(d.approx_start_date.year for d in table if d.approx_start_date.year >= 2026)
    near = A.daewoon_turn_near(absent_chart, [str(turn_year)])
    assert near and "대운 교체(" in near[0]
    assert A.daewoon_turn_near(absent_chart, [str(turn_year + 4)]) == []  # 반례 — 교체에서 먼 해
    lines = _text(A.axis_arrival_block(absent_chart, [(str(turn_year), "")], A.LENS_POSITION))
    assert "두 번의 기회를 두고 일정을 짜는 편이 맞다" in lines


def test_layer_lines_are_in_time_order_regardless_of_candidate_order(absent_chart) -> None:
    """후보는 점수 순으로 넘어온다 — 층 줄은 시점 순으로 정렬해 싣는다."""
    periods = [("2027-05", "乙巳"), ("2027-02", "壬寅"), ("2027-04", "甲辰"), ("2027-03", "癸卯")]
    lines = A.axis_arrival_block(absent_chart, periods, A.LENS_POSITION)
    months = [ln[3:10] for ln in lines if ln.startswith("월운 ")]
    assert months == ["2027-02", "2027-03", "2027-04", "2027-05"]
    where = next(ln for ln in lines if "원국에 드러난 관성이 없다가" in ln)
    assert where.startswith(
        "- [월운 2027-02 지지·월운 2027-03 지지·월운 2027-04 천간·월운 2027-05 천간]"
    )


def test_block_is_empty_without_hour_or_lens_or_periods(absent_chart) -> None:
    assert A.axis_arrival_block(calculate(_UNKNOWN_HOUR), [("2027", "")], A.LENS_POSITION) == []
    assert A.axis_arrival_block(absent_chart, [("2027", "")], None) == []
    assert A.axis_arrival_block(absent_chart, [("2027", "")], "no_such_lens") == []
    assert A.axis_arrival_block(absent_chart, [], A.LENS_POSITION) == []


def test_business_and_wealth_lenses_use_their_own_axes(absent_chart) -> None:
    """사업 렌즈는 재성·식상, 재물 렌즈는 재성의 천간/지지 양상만(원국 줄 없음)."""
    # 2028 戊申: 戊=겁재, 申=상관(식상) / 2030 庚戌: 庚=상관(식상), 戌=겁재.
    biz = A.axis_arrival_block(absent_chart, [("2028", "")], A.LENS_BUSINESS)
    body = _text(biz)
    assert biz[0].startswith("[사업 구조 — ")
    assert "원국: 재성(시장·거래·매출) — 많음" in biz[1]
    assert "세운 2028 戊申: 지지 申 = 상관(식상" in body
    assert "지지로 오는 식상 — 생산·기술·서비스" in body
    assert "관성" not in body  # 반례 — 사업 렌즈에 자리·자격 축이 섞이지 않는다
    # 재물 렌즈 — 2032 壬子: 壬=정재, 子=편재.
    wealth = A.axis_arrival_block(absent_chart, [("2032", "")], A.LENS_WEALTH)
    wbody = _text(wealth)
    assert wealth[0].startswith("[재물이 오는 자리 — ")
    assert not any(ln.startswith("원국:") for ln in wealth)
    assert "천간으로 오는 재성 — 제안·소식" in wbody and "지지로 오는 재성 — 급여·매출" in wbody
    # 반례 — 재성이 들지 않는 해에는 재물 렌즈 블록이 없다(다음 해 안내도 없음).
    assert A.axis_arrival_block(absent_chart, [("2028", "")], A.LENS_WEALTH) == []


def test_children_lens_reads_child_star_by_gender(absent_chart) -> None:
    """남성 명식 — 관성이 자녀성. 원국에 드러난 관성이 없다가 월운 지지로 들어오는 달."""
    male = A.axis_arrival_block(absent_chart, [("2027-02", "壬寅")], A.LENS_CHILDREN_MALE)
    body = _text(male)
    assert male[0].startswith("[자녀 인연 구조 — ")
    assert "원국: 관성(자녀 — 책임과 규율) — 드러난 글자 없음" in male[1]
    assert "[월운 2027-02 지지] 원국에 드러난 관성이 없다가 운에서 들어오는 때" in body
    assert "자녀와 가장으로서의 책임 얘기" in body
    assert "세운으로 드는 다음 해" not in body  # 자녀 렌즈는 다음 해 안내를 싣지 않는다
    assert "임신·출산이나 그 시기를 확정하지 말 것" in male[-1]
    # 여성 명식 — 식상이 자녀성(癸酉 己未 甲寅 辛未: 甲 일간의 식상 = 火, 2027 丁未 천간 丁 = 상관).
    female_chart = calculate(_DECADE_SEAL)
    female = _text(A.axis_arrival_block(female_chart, [("2027", "")], A.LENS_CHILDREN_FEMALE))
    assert "세운 2027 丁未: 천간 丁 = 상관(식상" in female
    assert "천간으로 오는 식상 — 자녀 계획·임신 소식처럼" in female
    # 반례 — 같은 해를 남성 렌즈(관성)로 보면 축 글자가 없어 블록이 없다.
    assert A.axis_arrival_block(female_chart, [("2027", "")], A.LENS_CHILDREN_MALE) == []


# ── 문구 사전 ────────────────────────────────────────────────────────────────


def test_dictionary_passes_schema_and_lint() -> None:
    assert not [e for e in validate_dictionaries(_DICTS) if "axis_arrival_lens" in e]
    assert not [e for e in lint_dictionaries(_DICTS) if "axis_arrival_lens" in e]
    lenses = A.load_axis_lenses()
    assert set(lenses) == {
        A.LENS_POSITION, A.LENS_BUSINESS, A.LENS_WEALTH,
        A.LENS_CHILDREN_FEMALE, A.LENS_CHILDREN_MALE,
    }
    assert lenses[A.LENS_POSITION].next_arrival and not lenses[A.LENS_BUSINESS].next_arrival


def test_dictionary_lint_catches_counterexamples() -> None:
    raw = json.loads((_DICTS / "interpretations" / "axis_arrival_lens.json").read_text("utf-8"))
    ids = _structure_pattern_ids(_DICTS)
    assert ids and _lint_axis_arrival_lens(AxisArrivalLensFile.model_validate(raw), ids) == []

    def _errors(mutate) -> list[str]:
        doc = copy.deepcopy(raw)
        mutate(doc)
        return _lint_axis_arrival_lens(AxisArrivalLensFile.model_validate(doc), ids)

    def _state_pass(doc) -> None:
        doc["lenses"][0]["items"][0]["text"] += " 이 해에는 합격한다."

    def _declare_absence(doc) -> None:
        doc["lenses"][0]["items"][0]["text"] += " 그 밖의 해에는 기회가 없다."

    def _foreign_group(doc) -> None:
        doc["lenses"][0]["items"][0]["id"] = "absent_arrive.wealth"  # 축 밖의 군

    def _bridge_without_config(doc) -> None:
        doc["lenses"][0]["bridgeExcess"] = None

    def _unknown_pattern(doc) -> None:
        doc["lenses"][0]["chainPatterns"].append("NO_SUCH_PATTERN")

    def _rename_lens(doc) -> None:
        doc["lenses"][2]["key"] = "money"

    def _state_birth(doc) -> None:
        doc["lenses"][3]["items"][0]["text"] += " 이 해에 임신한다."

    for mutate in (
        _state_pass, _declare_absence, _foreign_group, _bridge_without_config,
        _unknown_pattern, _rename_lens, _state_birth,
    ):
        assert _errors(mutate), mutate.__name__


# ── 배선 ─────────────────────────────────────────────────────────────────────


def test_chat_carries_block_for_matching_intents_only(monkeypatch) -> None:
    exam_q = "내년에 자격증 시험 합격할 수 있을까?"
    exam = chat_service.chat(_ABSENT_OFFICER, exam_q, _T, dry_run=True)
    assert "[자리·자격 구조 — 원국 × 운에서 온 글자" in (exam.prompt_preview or "")
    grant = chat_service.chat(
        _ABSENT_OFFICER, "내년 초에 정부 지원사업 공모에 재도전하는데 선정될 수 있을까?", _T,
        dry_run=True,
    )
    assert "[자리·자격 구조 — 원국 × 운에서 온 글자" in (grant.prompt_preview or "")
    # 출산 질문 — 여성 명식(甲 일간)의 자녀성(식상 = 火)이 세운 천간에 드는 해(2027 丁未).
    # 질문은 룰 파서 어휘('임신')로 쓴다 — '아이가 생길'은 저장소에 없는 의도 유사도 모델
    # (compiled/intent_onnx, gitignore)이 있어야 출산 사건으로 잡혀 CI 에서 블록이 빠졌다
    # (2026-11-21).
    child_q = "내년에 임신할 수 있을까?"
    child = chat_service.chat(_DECADE_SEAL, child_q, _T, dry_run=True)
    assert "[자녀 인연 구조 — 원국 × 운에서 온 글자" in (child.prompt_preview or "")
    assert "천간 丁 = 상관(식상" in (child.prompt_preview or "")
    # 반례 — 남성 명식(己 일간)은 자녀성이 관성(木)이라 같은 해에 들지 않는다: 블록 없음.
    no_star = chat_service.chat(_ABSENT_OFFICER, child_q, _T, dry_run=True)
    assert "[자녀 인연 구조" not in (no_star.prompt_preview or "")
    # 반례 — 이직·건강 질문에는 싣지 않는다.
    for q in ("내년에 이직하는 게 좋을까?", "내년 건강운은 어때?"):
        res = chat_service.chat(_ABSENT_OFFICER, q, _T, dry_run=True)
        assert "원국 × 운에서 온 글자(엔진 판정 · 서술 전용" not in (res.prompt_preview or "")
    # 끄면 실리지 않는다.
    monkeypatch.setattr(period_v2_config, "AXIS_LENS_BLOCK_ENABLED", False)
    off = chat_service.chat(_ABSENT_OFFICER, exam_q, _T, dry_run=True)
    assert "[자리·자격 구조" not in (off.prompt_preview or "")


def test_block_is_wired_to_chat_trailing_and_report() -> None:
    """채팅 말미와 리포트(직업·재물 강의 블록 + 학업 기간 섹션)에 같이 배선한다."""
    assert "axis_arrival_block(" in inspect.getsource(chat_service)
    lecture = inspect.getsource(report_service._ReportData.lecture_block)
    assert 'axis_lens_lines(_labels, "position_seal")' in lecture
    assert 'axis_lens_lines(_labels, "wealth")' in lecture
    assert 'axis_lens_lines(_biz, "business")' in lecture      # 사업 사건 후보 기간에만
    assert "axis_lens_lines(_child, _child_lens)" in lecture   # 출산 후보 기간에만(성별 분기)
    source = inspect.getsource(report_service)
    assert 'data.axis_lens_lines(_role_labels, "position_seal")' in source


def test_report_lecture_block_adds_lens_only_for_matching_event_periods() -> None:
    """리포트 강의 블록 — 사업 렌즈는 사업 사건 후보 기간, 자녀 렌즈는 출산 후보 기간에만."""
    from types import SimpleNamespace

    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    def _data(birth: BirthInput, topic: str):
        spec = ReportSpec(
            product_code="RPT_FOCUS",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="회원")],
            topic=topic, period=ReportPeriod(start="2026-11", end="2031-12"),
        )
        return report_service._ReportData(birth, spec, _T)

    def _cand(event_key: str, period: str):
        return SimpleNamespace(event_key=event_key, period=period, score=70)

    # 여성 甲 일간 — 2027 丁未 세운 천간 丁 = 상관(자녀성). 출산 후보 기간이면 자녀 렌즈가 붙는다.
    rel = _data(_DECADE_SEAL, "relationship")
    with_child = _text(rel.lecture_block("relationship", [_cand("childbirth", "2027")]))
    assert "[자녀 인연 구조 — 원국 × 운에서 온 글자" in with_child
    # 반례 — 같은 기간이라도 출산 후보가 아니면(결혼 신호) 자녀 렌즈는 붙지 않는다.
    without = _text(rel.lecture_block("relationship", [_cand("marriage_signal", "2027")]))
    assert "[자녀 인연 구조" not in without
    # 己 일간 남성 — 2028 戊申 세운 지지 申 = 상관(식상). 사업 사건 후보 기간이면 사업 렌즈.
    career = _data(_ABSENT_OFFICER, "career")
    biz = _text(career.lecture_block("career", [_cand("business_start", "2028")]))
    assert "[사업 구조 — 원국 × 운에서 온 글자" in biz
    # 반례 — 취업 후보뿐이면 사업 렌즈는 붙지 않는다.
    job = _text(career.lecture_block("career", [_cand("job_gain", "2028")]))
    assert "[사업 구조" not in job
