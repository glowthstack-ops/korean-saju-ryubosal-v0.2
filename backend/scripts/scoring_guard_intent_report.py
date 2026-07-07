#!/usr/bin/env python3
"""Scoring 1c-α intent 확대 검증 — career 외 핵심 intent rank guard 적용 가능성 리포트.

career 유지 + relocation/wealth/relationship/study_document 를 in-process 일시 적용(APPLY_INTENTS=
[domain]·config default 불변)해 chat 경로에서 guard 부착 수·토큰·절단 위험을 본다. **운영 미적용·
score/rank/reduce 불변.** intent별 운영 적용은 리포트 후 건별 승인. 규격: §14-9

사용: python scripts/scoring_guard_intent_report.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
# 대표 차트(조건부 희신/병 운 보유 — guard 발동) + 대표 질문(domain 라우팅).
_CHART_IDS = ["operational_std", "kansal_taewang_01", "conditional_byeong_water_01"]
_DOMAINS = {
    "career": "올해 직업운 어때?",
    "relocation": "올해 이사운 어때?",
    "wealth": "올해 재물운 어때?",
    "relationship": "올해 연애운 어때?",
    "study_document": "올해 시험운 어때?",
}
_FEAR = ("흉", "나쁨", "불행", "위험")


def main() -> None:
    import saju_api.services.chat_service as chat_service
    from saju_engines.llm_guard import estimate_tokens
    from saju_shared_types.birth_input import BirthInput

    rows = {json.loads(line)["chart_id"]: json.loads(line)
            for line in _CHARTS.read_text(encoding="utf-8").splitlines() if line.strip()}
    births = {cid: BirthInput(**{**rows[cid]["input"], "reference_date": "2026-06-11"})
              for cid in _CHART_IDS if cid in rows}
    today = date(2026, 6, 11)

    # guard 문구 자체의 과장 단어 — config 보장(태그 라인의 기존 caution 텍스트는 무관).
    phrase_fear = sum(any(w in p for w in _FEAR)
                      for p in (list(cfg.SCORING_OPERATIONAL_GUARD_PHRASE.values())
                                + list(cfg.SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT.values())))
    print("=" * 76)
    print("Scoring 1c-α intent 확대 검증 — 운영 미적용·score/rank/reduce 불변")
    print(f"대표 차트 {len(births)} · APPLY_INTENTS 일시 적용(config default 불변)")
    print(f"guard 문구 자체 과장단어(흉/위험): {phrase_fear} (config 보장·0)")
    print("=" * 76)
    print(f"{'intent':<16}{'tags':>6}{'max/resp':>10}{'tok Δ범위':>14}{'절단(<0)':>9}")

    for domain, q in _DOMAINS.items():
        total = 0
        per_max = 0
        tok_deltas: list[int] = []
        truncated = 0       # tokΔ<0 = +태그가 토큰예산을 넘겨 본문 절단된 차트(위험)
        for b in births.values():
            cfg.SCORING_OPERATIONAL_APPLY_ENABLED = False
            off = chat_service.chat(b, q, today, dry_run=True).prompt_preview or ""
            cfg.SCORING_OPERATIONAL_APPLY_ENABLED = True
            cfg.SCORING_OPERATIONAL_APPLY_MODE = {"rank_guard": True,
                                                  "near_tie_demotion": False}
            cfg.SCORING_OPERATIONAL_APPLY_INTENTS = [domain]
            cfg.SCORING_OPERATIONAL_COMPONENTS = {"conditional_byeong_downgrade": True,
                                                  "low_operability_yongsin": True}
            on = chat_service.chat(b, q, today, dry_run=True).prompt_preview or ""
            total += on.count("[해석 주의]")
            per_max = max(per_max, on.count("[해석 주의]"))
            d = estimate_tokens(on) - estimate_tokens(off)
            tok_deltas.append(d)
            if d < 0:
                truncated += 1
        td = f"{min(tok_deltas)}~{max(tok_deltas)}" if tok_deltas else "-"
        print(f"{domain:<16}{total:>6}{per_max:>10}{td:>14}{truncated:>9}")
    cfg.SCORING_OPERATIONAL_APPLY_ENABLED = False  # 복원
    print("=" * 76)
    print("주: reason 전 intent 공통 conditional_byeong_downgrade(B 미발동·1b 일치).")
    print("   coverage guard G1/G3/G4 는 operational 산출 불변·flag 무관 위반 0(별도 검증).")
    print("   ★ 절단(<0)>0 = +태그가 토큰예산 초과→본문 절단(위험). 0 이어야 운영 적용 검토 가능.")
    print("   tags=0 = 질문이 후보 경로/도메인으로 라우팅 안 됨(해당 질문에선 guard 미발동).")


if __name__ == "__main__":
    main()
