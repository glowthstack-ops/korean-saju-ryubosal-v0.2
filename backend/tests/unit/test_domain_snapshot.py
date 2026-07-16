"""Phase 5b-2b 도메인 출력 snapshot — chat/period fortune 경로 고정(명식 구조 coverage 아님).

intent.domain.value → domain_to_expression_key → build_luck_grounding 의 정확한 chat 체인으로
도메인×expression_class 번역이 안정 노출되는지 고정한다. scoring 무관 — score/rank/favorability/
final/polarity/event score 불변. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §12·§13-5
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from saju_manse_analysis.yongsin.operational_role_config import EXPRESSION_GUIDANCE

import saju_engines.chart_interpretation as ci
from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.event_scoring import favorability_map
from saju_engines.shadow_scoring import domain_to_expression_key
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain

# 희신 과다 교정(2026-07-12) — 조건부·유보(壬子) 스냅샷은 조건부 희신/병이 남는 차트로.
_STD = BirthInput(calendar_type="solar", birth_date="1970-01-13", birth_time="04:30",
                  birth_place_name="Seoul", gender="male", reference_date="2026-06-11")


def _pillar(ganji: str):
    return SimpleNamespace(ganji=ganji, twelve_unseong="", relations_to_chart=[],
                           yongsin_alignment="", gongmang_activation=[])


def _line(ganji: str, domain_value: str | None) -> str:
    """chat_service.py:466-467 와 동일 체인: Domain.value → key → build_luck_grounding."""
    chart = calculate(_STD)
    domain_key = domain_to_expression_key(domain_value)
    return build_luck_grounding(chart, _pillar(ganji), domain_key=domain_key)["pillar_line"]


# ── A. adapter wiring (chat_service 가 intent.domain.value 로 호출) ──
def test_domain_adapter_wiring() -> None:
    assert domain_to_expression_key(Domain.CAREER.value) == "career"
    assert domain_to_expression_key(Domain.WEALTH.value) == "wealth"
    assert domain_to_expression_key(Domain.RELATIONSHIP.value) == "relationship"
    assert domain_to_expression_key(Domain.RELOCATION.value) == "relocation"
    assert domain_to_expression_key(Domain.EDUCATION.value) == "study_document"
    assert domain_to_expression_key(Domain.GENERAL.value) is None


# ── B. 도메인 × 水運(조건부·유보) 정확 문구 snapshot ──
def test_domain_water_phrase_snapshot() -> None:
    cases = {
        Domain.CAREER: "책임·압박·조직 이슈 동반",
        Domain.WEALTH: "계약·현실 부담 동반",
        Domain.RELATIONSHIP: "감정 과다·관계 압박 가능",
        Domain.RELOCATION: "계약 조건·방향성 확인 필요",
        Domain.EDUCATION: "문서·심리 부담 동반",
    }
    for dom, phrase in cases.items():
        line = _line("壬子", dom.value)
        assert "[표현 제한] 조건부·유보" in line
        assert phrase in line
        assert "점수·순위 불변" in line


# ── C. 5 운별 base 등급(domain=None) 고정 ──
def test_base_expression_classes_per_element() -> None:
    # 차트(1970-01-13 癸巳): 水=조건부 희신/병·金=용신(op0.85)·木=구신(제살보조)·火=기신·土=한신/병.
    assert "[표현 제한] 조건부·유보" in _line("壬子", None)            # 水
    assert "[표현 제한] 주의/흉" in _line("丙午", None)               # 火 기신
    geum = _line("庚申", None)                                         # 金 용신·작동성 0.85<0.9
    assert "[표현 제한] 길" in geum and "작동성 낮아" in geum
    assert "[표현 제한] 주의 속 일부 완화" in _line("甲寅", None)      # 木 구신→제살보조 완화
    assert "[표현 제한] 중립" in _line("戊辰", None)                   # 土 한신(0)·한신/병(0)


# ── D. GENERAL/None → base 5b-2a guidance fallback(도메인 문구 아님) ──
def test_general_falls_back_to_base() -> None:
    line = _line("壬子", Domain.GENERAL.value)
    assert EXPRESSION_GUIDANCE["조건부·유보"] in line
    assert "책임·압박·조직 이슈 동반" not in line  # 도메인 문구 미사용


# ── E. EXPRESSION_CLAMP_ENABLED=False → [표현 제한] 라인 전체 미노출 ──
def test_rollback_hides_line(monkeypatch) -> None:
    monkeypatch.setattr(ci._op_config, "EXPRESSION_CLAMP_ENABLED", False)
    line = _line("壬子", Domain.CAREER.value)
    assert "[표현 제한]" not in line and "책임·압박·조직 이슈 동반" not in line


# ── F. chat/period fortune 경로 smoke — 라인 노출 + flag off ──
def test_chat_path_surfaces_expression_limit() -> None:
    res = chat_service.chat(_STD, "올해 운 어때?", date(2026, 6, 11), dry_run=True)
    assert "[표현 제한]" in (res.prompt_preview or "")


def test_chat_path_rollback(monkeypatch) -> None:
    monkeypatch.setattr(ci._op_config, "EXPRESSION_CLAMP_ENABLED", False)
    res = chat_service.chat(_STD, "올해 운 어때?", date(2026, 6, 11), dry_run=True)
    assert "[표현 제한]" not in (res.prompt_preview or "")


# ── G. 후보 다수 경로 미노출 — 단일 기간 블록만(라인 ≤1회) ──
def test_not_per_candidate() -> None:
    res = chat_service.chat(_STD, "올해 운 어때?", date(2026, 6, 11), dry_run=True)
    pv = res.prompt_preview or ""
    assert pv.count("[표현 제한]") <= 1  # 후보별 반복이면 다수 — 단일 기간만 노출


# ── H. 불변 — domain_key 무관하게 favorability/final 동일 ──
def test_invariance_across_domains() -> None:
    chart = calculate(_STD)
    assert chart.yongsin_analysis is not None
    fav = favorability_map(chart)
    final = dict(chart.yongsin_analysis.final)
    for dom in (None, "career", "wealth", "relationship", "relocation", "education"):
        build_luck_grounding(chart, _pillar("壬子"),
                             domain_key=domain_to_expression_key(dom))
        assert favorability_map(chart) == fav
        assert dict(chart.yongsin_analysis.final) == final
