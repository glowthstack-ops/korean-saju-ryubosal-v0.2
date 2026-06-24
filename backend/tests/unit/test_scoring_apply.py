"""Scoring Phase 1c-α — rank guard 태그(순위·score 불변·career 한정) 검증.

게이트 조합(APPLY_ENABLED ∧ rank_guard ∧ domain∈career ∧ component≥1 ∧ delta≤−6)·max 3·reason 출처·
missing 미부착·불변. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §14-9
"""

from __future__ import annotations

from types import SimpleNamespace

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_api.services.manse_service import calculate
from saju_engines.scoring_operational import (
    guard_caution_phrase,
    operational_rank_guards,
)
from saju_shared_types.birth_input import BirthInput

_STD = BirthInput(calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
                  birth_place_name="Seoul", gender="male")
# 水(조건부 희신/병·A 감점 −6)·甲寅(용신 木)·庚申(기신)…
_GBP = {"p1": "壬子", "p2": "甲寅", "p3": "庚申", "p4": "丙午", "p5": "戊辰"}


def _sel(n=5):
    return [SimpleNamespace(period=p, score=80, event_key=f"e_{p}")
            for p in list(_GBP)[:n]]


def _on(monkeypatch, *, mode=True, intents=("career",), a=True, b=True):
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_ENABLED", True)
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_MODE",
                        {"rank_guard": mode, "near_tie_demotion": False})
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_INTENTS", list(intents))
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_COMPONENTS",
                        {"conditional_byeong_downgrade": a, "low_operability_yongsin": b})


def _guards(monkeypatch, *, domain="career", gbp=None, **kw):
    _on(monkeypatch, **kw)
    return operational_rank_guards(calculate(_STD), _sel(), gbp or _GBP, domain=domain)


# ── master off → 빈(byte-identical) ──
def test_master_off_empty(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_ENABLED", False)
    assert operational_rank_guards(calculate(_STD), _sel(), _GBP, domain="career") == []


# ── rank_guard mode off → 빈 ──
def test_mode_off_empty(monkeypatch) -> None:
    assert _guards(monkeypatch, mode=False) == []


# ── domain≠career → 빈 ──
def test_domain_not_allowed(monkeypatch) -> None:
    assert _guards(monkeypatch, domain="wealth") == []
    assert _guards(monkeypatch, domain="general") == []
    assert _guards(monkeypatch, domain="CAREER") != []   # normalize


# ── domain normalize: education value → study_document key 매칭(1c-final 버그 수정) ──
def test_domain_education_normalizes_to_study(monkeypatch) -> None:
    # APPLY_INTENTS=["study_document"]·intent.domain.value="education" → 정규화 후 매칭.
    assert _guards(monkeypatch, domain="education",
                   intents=("study_document",)) != []
    # APPLY_INTENTS 에 study_document 없으면 미적용.
    assert _guards(monkeypatch, domain="education", intents=("career",)) == []


# ── component 전부 off → 빈(감점 근거 없음) ──
def test_no_component_no_guard(monkeypatch) -> None:
    assert _guards(monkeypatch, a=False, b=False) == []


# ── career+on → 태그(조건부 희신/병 水) ──
def test_career_guards(monkeypatch) -> None:
    g = _guards(monkeypatch)
    assert g  # 최소 1개(水 조건부 희신/병 −6)
    # 반환은 (index, reason_key).
    assert all(k in cfg.SCORING_OPERATIONAL_GUARD_PHRASE for _i, k in g)
    assert all(0 <= i < 5 for i, _k in g)


# ── caution 중복 정리: 마커 있으면 compact, 없으면 full ──
def test_guard_caution_phrase_compact_vs_full() -> None:
    full = cfg.SCORING_OPERATIONAL_GUARD_PHRASE["conditional_byeong_downgrade"]
    compact = cfg.SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT["conditional_byeong_downgrade"]
    # 기존 caution 없음 → full
    assert guard_caution_phrase("conditional_byeong_downgrade", "") == full
    # 마커 없는 caution(검토월 등) → full
    assert guard_caution_phrase(
        "conditional_byeong_downgrade", "실행월 아니라 검토월로 안내") == full
    # 과대긍정 차단 마커 있음 → compact(지시문 중복 제거)
    assert guard_caution_phrase(
        "conditional_byeong_downgrade", "'좋은 달'로 과하게 단정하지 말 것") == compact
    # compact 는 '과한 긍정 금지' 미포함(중복 억제)
    assert "과한 긍정" not in compact


# ── max_guards=3 ──
def test_max_guards(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_COEF",
                        {**cfg.SCORING_OPERATIONAL_APPLY_COEF, "max_guards": 3})
    # 모든 기간 壬子(조건부 희신/병 −6) → 5후보 전부 대상이나 3개로 컷.
    g = _guards(monkeypatch, gbp=dict.fromkeys(_GBP, "壬子"))
    assert len(g) == 3


# ── reason 출처: penalty 유래 reason_key 만 ──
def test_reason_source(monkeypatch) -> None:
    g = _guards(monkeypatch)
    keys = set(cfg.SCORING_OPERATIONAL_GUARD_PHRASE)
    assert all(k in keys for _i, k in g)


# ── 조후보조신(火)·제살보조(土)는 무태그(penalty 없음) ──
def test_no_guard_for_johu_jesal(monkeypatch) -> None:
    # 丙午(火 조후보조신)·戊辰(土 제살보조)만 → A/B penalty 없음 → 무태그.
    g = _guards(monkeypatch, gbp={"p1": "丙午", "p2": "戊辰"})
    assert g == []


# ── missing ganji → 미부착(임의 계산 금지) ──
def test_missing_ganji_no_guard(monkeypatch) -> None:
    g = _guards(monkeypatch, gbp={"p1": "壬子"})  # p2.. 누락
    assert all(i == 0 for i, _c in g)  # p1(index 0)만 가능, 누락은 미부착
