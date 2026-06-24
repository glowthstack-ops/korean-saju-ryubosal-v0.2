"""Scoring 토큰 헤드룸 가드 — guard 태그가 본문 절단을 유발하지 않음(본문 우선). spec §14-9.

relationship+kansal_taewang 절단 재현 방지·career 정상 부착·헤드룸 부족 시 미부착·APPLY off
byte-identical. 실제 .score/rank/reduce 불변.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_api.services import chat_service
from saju_engines.llm_guard import estimate_tokens
from saju_shared_types.birth_input import BirthInput

_CHARTS = Path(__file__).resolve().parents[2] / "data" / "shadow_charts" / "charts.jsonl"
_ROWS = {json.loads(line)["chart_id"]: json.loads(line)
         for line in _CHARTS.read_text(encoding="utf-8").splitlines() if line.strip()}
_TODAY = date(2026, 6, 11)
_TAG = "[해석 주의]"


def _birth(cid: str) -> BirthInput:
    return BirthInput(**{**_ROWS[cid]["input"], "reference_date": "2026-06-11"})


def _on(monkeypatch, domain: str) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_ENABLED", True)
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_MODE",
                        {"rank_guard": True, "near_tie_demotion": False})
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_INTENTS", [domain])
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_COMPONENTS",
                        {"conditional_byeong_downgrade": True, "low_operability_yongsin": True})


def _preview(birth, q):
    return chat_service.chat(birth, q, _TODAY, dry_run=True).prompt_preview or ""


# ── relationship+kansal: 절단 재발 금지(본문 보존) ──
def test_relationship_kansal_no_truncation(monkeypatch) -> None:
    b = _birth("kansal_taewang_01")
    off = _preview(b, "올해 연애운 어때?")
    _on(monkeypatch, "relationship")
    on = _preview(b, "올해 연애운 어때?")
    # 태그가 본문을 밀어내 재축소되면 tokΔ 가 크게 음수(−1384). 헤드룸 가드 후 그러면 안 됨.
    assert estimate_tokens(on) - estimate_tokens(off) >= 0


# ── career: 헤드룸 충분 → 태그 정상 부착 ──
def test_career_tags_attached(monkeypatch) -> None:
    _on(monkeypatch, "career")
    on = _preview(_birth("operational_std"), "올해 직업운 어때?")
    assert _TAG in on


# ── 헤드룸 부족(예약 과대) → 동적 미부착(본문 우선) ──
def test_headroom_insufficient_suppresses(monkeypatch) -> None:
    _on(monkeypatch, "career")
    # reserve 를 한도 전체로 → 헤드룸 음수 → 태그 0개(본문 보존).
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_HEADROOM_RESERVE", 99999)
    on = _preview(_birth("operational_std"), "올해 직업운 어때?")
    assert _TAG not in on


# ── APPLY off → byte-identical(태그·추가 직렬화 없음) ──
def test_apply_off_byte_identical(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_ENABLED", False)
    b = _birth("operational_std")
    a = _preview(b, "올해 직업운 어때?")
    c = _preview(b, "올해 직업운 어때?")
    assert a == c and _TAG not in a
