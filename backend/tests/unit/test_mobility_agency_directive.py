"""이동 주체 미상 지시문 + 로그 전용 감사 (2026-10-15 데굴님 승인).

라이브 실측 반례: 실사례(1980-11-22 09:40 서울 남, 2026-10 戊戌월 권고사직)에 "내가 원해서 나가는
걸까, 회사가 내보내는 걸까"를 물었더니 답이 "외부의 강요에 의한 이탈이라기보다 … 자발적인 성격이
강하며", "단순히 밀려나는 것이 아니라 본인이 주도하여"로 주체를 단정했다. 입력 계약(이동 문구
'자의·타의 모두', 극성 '조건부')은 지켜졌고 답변 단계에서 깨졌다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_CASE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_TODAY = date(2026, 10, 15)
_Q_AGENCY = (
    "2026년 10월에 직장 이동이 있을까? 있다면 내가 원해서 나가는 걸까, 회사가 내보내는 걸까?"
)
_LIVE_BAD = (
    "결론부터 말씀드리면, 이번 변화는 외부의 강요에 의한 이탈이라기보다 본인의 의지와 경쟁력을 "
    "바탕으로 더 나은 기반을 다지려는 자발적인 성격이 강하며 결과 또한 유리합니다. "
    "직장에서 단순히 밀려나는 것이 아니라 본인이 주도하여 더 나은 자리를 쟁취하려는 구도입니다."
)
_LIVE_OK = (
    "10월은 직장·역할의 이동이 걸릴 수 있는 기간입니다. 스스로 택하는 독립·이직일 수도, "
    "권고사직처럼 타의로 오는 이동일 수도 있어 사주로는 어느 쪽인지 정해지지 않습니다."
)


def _cand(key: str):
    return SimpleNamespace(event_key=key)


# ── 지시문 필요 판정 ────────────────────────────────────────────────────────

def test_directive_needed_when_question_asks_agency_or_mobility_candidate_present():
    assert chat_service._mobility_agency_directive_needed(_Q_AGENCY, [])
    assert chat_service._mobility_agency_directive_needed("권고사직 당할까?", [])
    assert chat_service._mobility_agency_directive_needed(
        "10월 직장 변동 있을까?", [_cand("wealth_change"), _cand("career_change")],
    )
    assert not chat_service._mobility_agency_directive_needed(
        "10월 연애운은 어때?", [_cand("new_relationship"), _cand("wealth_change")],
    )
    assert not chat_service._mobility_agency_directive_needed("10월 연애운은 어때?", [])


# ── 감사 어구 ────────────────────────────────────────────────────────────────

def test_audit_regexes_catch_live_claims_and_pass_hedged_wording():
    hits = [m.group(0) for rx in chat_service._AGENCY_CLAIM_RES for m in rx.finditer(_LIVE_BAD)]
    assert any("자발적" in h for h in hits) and any("밀려나는 것이 아니" in h for h in hits)
    assert any("강요" in h and "보다" in h for h in hits)  # 비교 부정도 타의 부정
    assert not [m for rx in chat_service._AGENCY_CLAIM_RES for m in rx.finditer(_LIVE_OK)]


def test_audit_is_log_only_and_returns_answer_unchanged(monkeypatch):
    calls: list[tuple[str, tuple]] = []
    monkeypatch.setattr(
        chat_service._logger, "warning", lambda msg, *a, **k: calls.append(("warning", a)),
    )
    monkeypatch.setattr(
        chat_service._logger, "info", lambda msg, *a, **k: calls.append(("info", a)),
    )
    payload = SimpleNamespace(event_candidates=[_cand("career_change")])
    audit = chat_service._audit_mobility_agency_answer
    assert audit(_LIVE_BAD, payload, "10월 직장?", "t") == _LIVE_BAD
    assert calls and calls[-1][0] == "warning"
    calls.clear()
    assert audit(_LIVE_OK, payload, "10월 직장?", "t") == _LIVE_OK
    assert calls[-1][0] == "info"
    calls.clear()  # 대상 아님(이동 후보·주체 질문 없음) — 로그조차 남기지 않는다
    none = SimpleNamespace(event_candidates=[_cand("wealth_change")])
    assert audit(_LIVE_BAD, none, "10월 재물운?", "t") == _LIVE_BAD
    assert not calls


# ── dry-run 프롬프트 ──────────────────────────────────────────────────────────

def test_dry_run_prompt_carries_directive_for_real_case_question():
    resp = chat_service.chat(_CASE, _Q_AGENCY, _TODAY, True)
    assert resp.status == "dry_run"
    assert "[이동 주체 미상]" in (resp.prompt_preview or "")


def test_dry_run_prompt_without_mobility_candidate_has_no_directive():
    resp = chat_service.chat(_CASE, "2026년 10월 연애운은 어때?", _TODAY, True)
    assert resp.status == "dry_run"
    p = resp.prompt_preview or ""
    if "career_change" not in p and "직업 변화" not in p:
        assert "[이동 주체 미상]" not in p
