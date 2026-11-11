"""외부 '합격운' 글 대조 후속 (2026-11-11) — 수험 질문 파서 결함 3건 + 합격 준비 성향 서술층.

① 추가 합격·예비 번호 질문이 범위 좁히기 메뉴로 반려되던 결함
② '올해 떨어졌는데 내년엔 붙을까?' 가 올해 종합운으로 잡히던 결함
   - 합격·불합격 구어 짝('떨어지다'+'붙다') → 입학·합격 사건(학업 분야 분석)
   - 과거 서술절이 붙은 연도는 배경(reference) → 뒤의 연도가 분석 대상
③ 원국 식상·재성 다자일 때 준비 방식 해설 한 줄(채팅 구조 블록·학업 주제 리포트 C-02)

시기 주장(관성·인성이 겹치는 달)은 실사례 측정에서 변별력이 확인되지 않아 엔진에 넣지 않았다
(`scripts/measure_exam_outcome_patterns.py`, doc/v2_2/EXTERNAL_TEXT_GAP_EXAM_LUCK_POST.md).
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
from saju_api.services.manse_service import calculate
from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.dictionaries import (
    ExamStageTraitsFile,
    _lint_exam_stage_traits,
    validate_dictionaries,
)
from saju_engines.exam_stage_traits import (
    EXAM_STAGE_HEADER,
    EXAM_STAGE_RULE,
    exam_stage_trait_lines,
)
from saju_engines.llm_event_serializer import (
    EXAM_CURRENT_LABEL,
    EXAM_CURRENT_RULE,
    exam_current_note,
    needs_exam_current_rule,
)
from saju_engines.query_parser import is_pass_fail_question, parse_message
from saju_engines.report_event_input import (
    month_overview_lines,
    precise_candidate_clusters,
    score_table_lines,
)
from saju_engines.report_plan import build_section_plans
from saju_engines.rewriter import assess
from saju_engines.time_parser import extract_time_constraints
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.intent import (
    Domain,
    IntentJson,
    QueryType,
    SubjectKind,
    SubjectRef,
    TimeConstraintRole,
)
from saju_shared_types.report import ReportPeriod, ReportSpec

_T = date(2026, 11, 11)
_MONTH = "2026-11"
_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _intent(q: str) -> IntentJson:
    return parse_message(q, _T, current_month_label=_MONTH).intents[0]


def _birth(d: str, t: str) -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=d, birth_time=t, birth_place_name="서울", gender="male",
    )


# 원국 십성다자(가시 글자 3개 이상) 픽스처 — 己未 丙子 丁丑 辛丑 등(2026-11-11 탐색).
_OUTPUT_MANY = ("1980-01-05", "02:00")  # 식상 4글자
_WEALTH_MANY = ("1980-03-15", "02:00")  # 재성 3글자
_BOTH_MANY = ("1980-03-05", "02:00")  # 재성 3·식상 3
_NONE_MANY = ("1980-03-05", "10:00")  # 다자 없음


# ── ① 추가 합격·예비 번호 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "q",
    [
        "예비 3번인데 붙을 수 있을까?", "추합 전화 올까?", "예비번호 받았는데 될까?",
        "추가합격 될 수 있을까?",
    ],
)
def test_waitlist_questions_route_to_admission(q: str) -> None:
    it = _intent(q)
    assert assess(it, q).status != "too_broad", q
    assert it.domain is Domain.EDUCATION
    assert it.event_key is EventKey.EDUCATION_ADMISSION
    assert it.query_type is QueryType.DOMAIN_ANALYSIS


@pytest.mark.parametrize(
    "q", ["유추합니다 이게 맞나요", "예비 신부인데 결혼운 어때", "예비군 훈련 가도 될까"],
)
def test_waitlist_lookalikes_are_not_admission(q: str) -> None:
    it = _intent(q)
    assert it.event_key is not EventKey.EDUCATION_ADMISSION, q
    assert it.domain is not Domain.EDUCATION, q


# ── ② 합격·불합격 구어 짝 + 과거 서술절 연도 ──────────────────────────────────


def test_failed_this_year_asks_about_next_year() -> None:
    """실답 형태 — 올해는 지난 일(배경), 분석 대상은 내년 학업·합격."""
    q = "올해 떨어졌는데 내년엔 붙을까?"
    it = _intent(q)
    assert assess(it, q).status == "ok"
    assert (it.query_type, it.domain) == (QueryType.DOMAIN_ANALYSIS, Domain.EDUCATION)
    assert it.event_key is EventKey.EDUCATION_ADMISSION
    assert it.time_range is not None and it.time_range.start == it.time_range.end == "2027"
    roles = [(i.role, i.start_year) for i in extract_time_constraints(q, _T)]
    assert roles == [(TimeConstraintRole.REFERENCE, 2026), (TimeConstraintRole.MENTION, 2027)]


@pytest.mark.parametrize(
    "q, year",
    [
        ("2024년에 떨어졌는데 내년엔 붙을까?", "2027"),
        ("올해 이직했는데 내년 승진 가능할까?", "2027"),  # 다른 분야도 같은 규칙
        ("올해 힘들었는데 중요한 건 내년이야", "2027"),  # 과거 서술절이 긍정 술어보다 앞
        ("작년에 떨어졌는데 올해는 붙을까?", "2026"),  # '작년'은 연도 언급 목록 밖 — 종전대로 올해
    ],
)
def test_past_clause_year_is_background(q: str, year: str) -> None:
    it = _intent(q)
    assert it.time_range is not None and it.time_range.start == year, q


def test_two_past_years_keep_previous_behavior() -> None:
    """두 연도가 모두 지난 일이면 배경으로 돌리지 않는다(종전 판정 유지)."""
    q = "2025년에 결혼했는데 2026년에 이혼했어 왜 그랬을까"
    roles = [i.role for i in extract_time_constraints(q, _T)]
    assert roles == [TimeConstraintRole.MENTION, TimeConstraintRole.MENTION]
    it = _intent(q)
    assert it.time_range is not None and it.time_range.start == "2025"


@pytest.mark.parametrize(
    "q, roles",
    [
        ("올해 말고 내년은?", [TimeConstraintRole.EXCLUDED, TimeConstraintRole.CORRECTION]),
        (
            "2026년 27년은 의미없고 2033년이 중요해",
            [TimeConstraintRole.EXCLUDED, TimeConstraintRole.TARGET],
        ),
    ],
)
def test_existing_year_roles_unchanged(q: str, roles: list[TimeConstraintRole]) -> None:
    assert [i.role for i in extract_time_constraints(q, _T)] == roles


@pytest.mark.parametrize(
    "q",
    [
        "불이 붙을까 걱정이야",  # 떨어짐 없음
        "주가가 떨어졌는데 어떻게 될까",  # 붙음 없음
        "남친이랑 떨어졌는데 다시 붙을 수 있을까",  # 사람과 떨어지고 붙는 이야기
        "그 사람이랑 떨어졌는데 다시 붙을까",
    ],
)
def test_pass_fail_lookalikes(q: str) -> None:
    assert not is_pass_fail_question(q), q
    assert _intent(q).event_key is not EventKey.EDUCATION_ADMISSION, q


def test_pass_fail_pair_yields_to_other_domain_words() -> None:
    """면접(취업 사건)이 있으면 학업으로 끌어오지 않는다 — 다른 분야·사건이 없을 때만 앵커."""
    it = _intent("면접에서 떨어졌는데 다음엔 붙을까?")
    assert it.domain is Domain.CAREER
    assert it.event_key is not EventKey.EDUCATION_ADMISSION


# ── ③ 합격 준비 성향 서술층 ───────────────────────────────────────────────────


def test_exam_stage_lines_only_for_output_or_wealth_excess() -> None:
    out = exam_stage_trait_lines(calculate(_birth(*_OUTPUT_MANY)))
    assert out[0] == EXAM_STAGE_HEADER and out[-1] == EXAM_STAGE_RULE
    assert len(out) == 3 and "면접·발표·실기" in out[1] and "(원국 식상 4글자)" in out[1]

    wealth = exam_stage_trait_lines(calculate(_birth(*_WEALTH_MANY)))
    assert len(wealth) == 3 and "실무 경력" in wealth[1] and "(원국 재성 3글자)" in wealth[1]

    both = exam_stage_trait_lines(calculate(_birth(*_BOTH_MANY)))
    assert len(both) == 4
    assert "(원국 재성 3글자)" in both[1] and "(원국 식상 3글자)" in both[2]  # 동률은 강의 순서

    assert exam_stage_trait_lines(calculate(_birth(*_NONE_MANY))) == []


def test_exam_stage_text_never_states_pass_or_fail() -> None:
    """문구는 준비 방식 해설뿐 — 당락·단정 어휘가 없고 사전 린트가 이를 지킨다."""
    lines = exam_stage_trait_lines(calculate(_birth(*_BOTH_MANY)))
    body = " ".join(lines[1:-1])
    for bad in ("반드시", "무조건", "합격한다", "불합격", "떨어진다", "붙는다", "당락"):
        assert bad not in body
    assert "근거로 쓰지 말고" in EXAM_STAGE_RULE
    assert not [e for e in validate_dictionaries(_DICTS) if "exam_stage_traits" in e]
    # 반례 — 당락 어휘가 들어가면, 또는 십성군이 정의와 다르면 린트가 잡는다.
    raw = json.loads((_DICTS / "interpretations" / "exam_stage_traits.json").read_text("utf-8"))
    assert _lint_exam_stage_traits(ExamStageTraitsFile.model_validate(raw)) == []
    stated = copy.deepcopy(raw)
    stated["items"][0]["text"] += " 면접에 가면 합격한다."
    assert _lint_exam_stage_traits(ExamStageTraitsFile.model_validate(stated))
    regrouped = copy.deepcopy(raw)
    regrouped["items"][1]["group"] = "인성"
    assert _lint_exam_stage_traits(ExamStageTraitsFile.model_validate(regrouped))


@pytest.mark.parametrize(
    "q, expected",
    [
        ("내년에 합격할 수 있을까?", True),  # 학업 도메인
        ("추합 전화 올까?", True),
        ("취업 언제 될까?", True),  # 취업 합격 사건
        ("내년 재물운 어때?", False),
        ("내년 운세 어때?", False),  # 총운에는 싣지 않는다
    ],
)
def test_exam_stage_block_wired_into_chat_prompt(q: str, expected: bool) -> None:
    res = cs.chat(_birth(*_OUTPUT_MANY), q, _T, dry_run=True)
    assert res.prompt_preview is not None
    assert (EXAM_STAGE_HEADER in res.prompt_preview) is expected, q
    assert res.prompt_preview.count(EXAM_STAGE_HEADER) <= 1


@pytest.mark.parametrize(
    "q, expected",
    [
        ("내년에 합격할 수 있을까?", True),
        ("취업 언제 될까?", True),
        ("내년 재물운 어때?", False),
        ("내년 운세 어때?", False),
    ],
)
def test_exam_current_rule_wired_into_chat_prompt(q: str, expected: bool) -> None:
    """합격 기류는 '있다'만 표지한다 — 읽는 법 규칙은 합격·취업 질문에만, 명식과 무관하게."""
    res = cs.chat(_birth(*_NONE_MANY), q, _T, dry_run=True)
    assert res.prompt_preview is not None
    assert (EXAM_CURRENT_RULE in res.prompt_preview) is expected, q
    assert "불합격 위험" not in res.prompt_preview.replace(EXAM_CURRENT_RULE, "")


def test_exam_current_rule_in_education_report_period_sections() -> None:
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="education", period=ReportPeriod(start="2026-01", end="2027-12"),
    )
    data = _ReportData(_birth(*_NONE_MANY), spec, _T, owner_id=None, subject_id=None)
    with_rule = [
        plan.section_id for plan in build_section_plans(spec)
        if EXAM_CURRENT_RULE in build_section_context(plan, spec, data).body_prompt
    ]
    assert with_rule == ["C-01", "C-03", "C-04"]


def test_exam_stage_block_absent_when_chart_has_no_excess() -> None:
    res = cs.chat(_birth(*_NONE_MANY), "내년에 합격할 수 있을까?", _T, dry_run=True)
    assert res.prompt_preview is not None and EXAM_STAGE_HEADER not in res.prompt_preview


def _sections_with_block(topic: str, birth: tuple[str, str]) -> list[str]:
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01", end="2027-12"),
    )
    data = _ReportData(_birth(*birth), spec, _T, owner_id=None, subject_id=None)
    return [
        plan.section_id for plan in build_section_plans(spec)
        if EXAM_STAGE_HEADER in build_section_context(plan, spec, data).body_prompt
    ]


def test_exam_stage_block_wired_into_education_report_only() -> None:
    """학업 주제 집중 리포트의 원국 구조 섹션(C-02)에만 — 직업 주제·미성립 명식에는 없다."""
    assert _sections_with_block("education", _OUTPUT_MANY) == ["C-02"]
    assert _sections_with_block("career", _OUTPUT_MANY) == []
    assert _sections_with_block("education", _NONE_MANY) == []


# ── 읽는 법 규칙은 표지를 따라간다 (2026-11-11 점검) ──────────────────────────
# 표지는 후보 줄에 붙어 질문 종류·섹션과 무관하게 실리는데 규칙은 질문 종류로만 붙여, 직업운·일
# 단위 질문과 학업 리포트 C-02·C-05~07 에 표지만 실렸다. 본문 조립 뒤 한 번 더 확인해 붙인다.

# 2026-11-11 기준 취업·합격 후보에 '합격 기류 있음' 표지가 실리는 명식(탐색 결과).
_LABELLED = ("1990-05-05", "12:00")


def _labelled(text: str) -> bool:
    """규칙 문장의 인용을 뺀 본문에 표지가 실렸는가."""
    return EXAM_CURRENT_LABEL in text.replace(EXAM_CURRENT_RULE, "")


def test_needs_exam_current_rule_helper() -> None:
    assert needs_exam_current_rule(f"취업·합격: 용기신 품질 → {EXAM_CURRENT_LABEL}")
    assert not needs_exam_current_rule("취업·합격: 용기신 품질")  # 표지 없음
    # 규칙이 이미 있으면 다시 붙이지 않는다(규칙 문장이 표지 문자열을 인용한다).
    assert not needs_exam_current_rule(f"… → {EXAM_CURRENT_LABEL}\n{EXAM_CURRENT_RULE}")
    assert not needs_exam_current_rule(EXAM_CURRENT_RULE)


@pytest.mark.parametrize("q", ["내년 직업운 어때?", "12월 3일 면접 보는데 어때?"])
def test_rule_follows_label_in_non_exam_chat_questions(q: str) -> None:
    """합격·취업 사건으로 분류되지 않는 질문도 표지가 실리면 규칙이 한 번 붙는다."""
    intent = _intent(q)
    assert intent.event_key not in (EventKey.EDUCATION_ADMISSION, EventKey.JOB_GAIN)  # 전제
    res = cs.chat(_birth(*_LABELLED), q, _T, dry_run=True)
    assert res.prompt_preview is not None
    assert _labelled(res.prompt_preview), q  # 전제 — 표지가 실린다
    assert res.prompt_preview.count(EXAM_CURRENT_RULE) == 1, q


def test_rule_not_duplicated_for_exam_chat_question() -> None:
    res = cs.chat(_birth(*_LABELLED), "취업 언제 될까?", _T, dry_run=True)
    assert res.prompt_preview is not None and _labelled(res.prompt_preview)
    assert res.prompt_preview.count(EXAM_CURRENT_RULE) == 1


def test_rule_absent_when_no_label_in_non_exam_chat_question() -> None:
    """반례 — 표지가 실리지 않는 질문에는 같은 명식이어도 규칙이 없다."""
    res = cs.chat(_birth(*_LABELLED), "올해 운세 어때?", _T, dry_run=True)
    assert res.prompt_preview is not None
    assert not _labelled(res.prompt_preview)
    assert EXAM_CURRENT_RULE not in res.prompt_preview


def _section_bodies(topic: str, birth: tuple[str, str]) -> dict[str, str]:
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01", end="2027-12"),
    )
    data = _ReportData(_birth(*birth), spec, _T, owner_id=None, subject_id=None)
    return {
        plan.section_id: build_section_context(plan, spec, data).body_prompt
        for plan in build_section_plans(spec)
    }


def test_rule_follows_label_in_every_education_report_section() -> None:
    bodies = _section_bodies("education", _LABELLED)
    labelled = {sid for sid, body in bodies.items() if _labelled(body)}
    # 전제 — 종전에 규칙이 없던 섹션(C-01·03·04 밖)에도 표지가 실린다.
    assert labelled - {"C-01", "C-03", "C-04"}
    for sid in labelled:
        assert bodies[sid].count(EXAM_CURRENT_RULE) == 1, sid
    # 표지도 없고 요약·기간 섹션도 아니면 규칙이 없다(반례).
    for sid, body in bodies.items():
        if sid not in labelled and sid not in {"C-01", "C-03", "C-04"}:
            assert EXAM_CURRENT_RULE not in body, sid


# ── 리포트 기간 줄의 표지 (2026-11-11) ────────────────────────────────────────
# 종전에는 리포트에서 표지가 '[내부 근거]' 블록(상위 3건의 사유 사슬 — 기간 없음)으로만 실려, 어느
# 기간에 합격 기류가 있는지 LLM 이 알 수 없었고 상위 3건에 못 든 후보의 표지는 아예 빠졌다.

_PERIOD_ROW = re.compile(r"^\d{4}-\d{2} ")


def _has_pass(c: EventCandidate) -> bool:
    return any(code.startswith("EXAM_PASS") for code in c.evidence_path)


def test_exam_current_note_only_for_pass_reasons() -> None:
    assert exam_current_note(["RELATION_HIT", "EXAM_PASS_관인상생"]) == f" · {EXAM_CURRENT_LABEL}"
    assert exam_current_note([]) == ""
    assert exam_current_note(["RELATION_HIT"]) == ""
    assert exam_current_note(["EXAM_FAIL_상관견관"]) == ""  # 불합격 패턴은 표지가 아니다


def _report_data(topic: str) -> _ReportData:
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01", end="2027-12"),
    )
    return _ReportData(_birth(*_LABELLED), spec, _T, owner_id=None, subject_id=None)


def test_cluster_candidate_rows_carry_label_per_candidate() -> None:
    """시점 클러스터의 후보 줄 — 합격 기류 사유가 있는 후보 줄에만 표지가 붙는다."""
    data = _report_data("education")
    with_pass = sum(1 for c in data.candidates if _has_pass(c))
    assert 0 < with_pass < len(data.candidates)  # 전제 — 있는 후보와 없는 후보가 섞여 있다
    rows = [
        ln for ln in precise_candidate_clusters(data.result, data.candidates)
        if ln.startswith("  - ")
    ]
    assert len(rows) == len(data.candidates)
    assert sum(1 for ln in rows if ln.endswith(f" · {EXAM_CURRENT_LABEL}")) == with_pass
    assert sum(1 for ln in rows if EXAM_CURRENT_LABEL in ln) == with_pass


def test_month_rows_carry_label_with_period_in_career_report() -> None:
    """직업 주제 월별 흐름 — 대표 사건에 합격 기류 사유가 있는 달의 줄에 표지가 붙는다."""
    data = _report_data("career")
    rows = month_overview_lines(data.result, data.scored, "career")
    labelled = [ln for ln in rows if EXAM_CURRENT_LABEL in ln]
    assert labelled and len(labelled) < len([ln for ln in rows if _PERIOD_ROW.match(ln)])
    for ln in labelled:
        assert _PERIOD_ROW.match(ln), ln  # 표지가 기간과 한 줄에 있다
        assert "취업·합격" in ln, ln  # 합격 기류 대상 사건의 줄에만


def test_rule_follows_label_in_career_report_sections() -> None:
    bodies = _section_bodies("career", _LABELLED)
    labelled = {sid for sid, body in bodies.items() if _labelled(body)}
    assert labelled  # 전제 — 월별 흐름 줄로 표지가 실린다
    for sid, body in bodies.items():
        assert body.count(EXAM_CURRENT_RULE) == (1 if sid in labelled else 0), sid


def test_score_table_never_carries_label() -> None:
    """반례 — 부록 점수표는 사용자 본문에 그대로 복사되는 표라 표지를 붙이지 않는다."""
    data = _report_data("education")
    assert any(_has_pass(c) for c in data.candidates)
    assert not any(
        EXAM_CURRENT_LABEL in ln for ln in score_table_lines(data.result, data.candidates)
    )
