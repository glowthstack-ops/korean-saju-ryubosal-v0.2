"""관리자 코드(F-n) 근거 병기 + 코드 근거 질문 라우팅 (2026-10-10 데굴님 승인).

실로그(데굴 1980-11-22 09:40 서울 구로구): '2031년에 F-2 코드의 위험이 있다고 알려준 근거를 알고
싶어'가 총운(Q1/general)으로 라우팅되고, 코드 줄에 근거가 없어 LLM 이 巳亥충·亥亥형·원진·공망을
근거처럼 끌어왔다. 실제 근거는 취약 장기(심·혈관 火) 재공격(세운 亥·대운 壬 水) + 대운·세운 중첩,
본인 p93 이상.
"""

from __future__ import annotations

from datetime import date

import saju_api.services.chat_service as cs
from saju_api.services.manse_service import calculate
from saju_engines.event_scoring import favorability_map
from saju_engines.health_vulnerability import (
    analyze_health_vulnerability,
    health_percentile_thresholds,
    health_window_evidence,
    lifetime_health_scores,
    percentile_top_label,
    severe_event_code,
)
from saju_engines.query_parser import SEVERE_CODE_QUESTION_RE, parse_message
from saju_engines.structural_context import health_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, QueryType

_TODAY = date(2026, 10, 10)
_Q = "2031년에 F-2 코드의 위험이 있다고 알려준 근거를 알고 싶어"
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
    gender="male", reference_date="2026-10-10",
)


def _degul():
    return calculate(_BIRTH)


def test_regex_matches_code_mentions_only() -> None:
    assert SEVERE_CODE_QUESTION_RE.search("코드 F-2 근거")
    assert SEVERE_CODE_QUESTION_RE.search("f-1 이 뭐야")
    assert not SEVERE_CODE_QUESTION_RE.search("2031년 건강운 어때")
    assert not SEVERE_CODE_QUESTION_RE.search("F1 경기")


def test_code_question_routes_to_health_domain_analysis() -> None:
    it = parse_message(_Q, _TODAY).intents[0]
    assert it.query_type is QueryType.DOMAIN_ANALYSIS
    assert it.domain is Domain.HEALTH and it.domains == []
    assert it.time_range is not None and it.time_range.start == "2031"


def test_evidence_names_luck_chars_and_organ() -> None:
    r = _degul()
    hv = analyze_health_vulnerability(r, favorability_map(r))
    life = lifetime_health_scores(r, hv)
    th = health_percentile_thresholds(life)
    w = life[2031]
    assert severe_event_code(w, th) == "F-2"
    ev = health_window_evidence(w, r, hv, th)
    joined = " / ".join(ev)
    assert "심·혈관 계열(火)" in joined
    assert "세운 亥(水)" in joined and "대운 壬(水)" in joined
    assert "대운 壬辰이 같은 근거로 겹침" in joined
    assert percentile_top_label(w.score, th) == "상위 7%"
    assert "상위 7%" in joined
    # 의미(사고·질병·사망) 어휘는 근거에 없다.
    for banned in ("사고", "질병", "사망", "부상"):
        assert banned not in joined


def test_health_lines_code_row_carries_evidence_without_meaning() -> None:
    r = _degul()
    hv = analyze_health_vulnerability(r, favorability_map(r))
    lines = health_lines(r, hv, 2026)
    row = next(ln for ln in lines if "2031년" in ln and "코드 F-2" in ln)
    assert "[근거:" in row and "재공격" in row
    guard = next(ln for ln in lines if ln.startswith("[관리자 코드 표기"))
    assert "[근거]" in guard and "끌어오지 말 것" in guard


def test_dry_run_prompt_has_evidence_row_and_directive_not_yearly_overview() -> None:
    res = cs.chat(_BIRTH, _Q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer
    pv = res.prompt_preview or ""
    assert "코드 F-2에 해당하는 사건" in pv and "[근거:" in pv
    assert "[코드 근거 질문]" in pv
    assert "한 해(특정 연)의 총운" not in pv
