#!/usr/bin/env python3
"""Scoring 1c-final 최종 회귀 — 핵심 intent 전체 rank guard 안전성 리포트.

5 핵심 intent 각각 33차트 chat 경로에서 guard 부착·절단·토큰을 본다(domain normalize 후).
**운영 미적용·score/rank/reduce 불변·본문 우선 헤드룸 가드 유지.**
규격: §14-9

사용: python scripts/scoring_guard_final_report.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_DOMAINS = {
    "career": "올해 직업운 어때?",
    "wealth": "올해 재물운 어때?",
    "relationship": "올해 연애운 어때?",
    "relocation": "올해 이사운 어때?",
    "study_document": "올해 시험운 어때?",
}
_FEAR = ("흉", "위험", "손실", "투자주의", "이별", "파탄")
_TAG = "[해석 주의]"


def main() -> None:
    import saju_api.services.chat_service as chat_service
    from saju_engines.llm_guard import estimate_tokens
    from saju_shared_types.birth_input import BirthInput

    rows = [json.loads(line) for line in _CHARTS.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    today = date(2026, 6, 11)

    # guard 문구 자체 과장단어(config 보장).
    phrase_fear = sum(any(w in p for w in _FEAR)
                      for p in (list(cfg.SCORING_OPERATIONAL_GUARD_PHRASE.values())
                                + list(cfg.SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT.values())))
    print("=" * 78)
    print(f"Scoring 1c-final 최종 회귀 — 차트 {len(rows)} · 핵심 intent 5 "
          "(운영 미적용·score/rank/reduce 불변)")
    print(f"guard 문구 자체 과장단어({'/'.join(_FEAR)}): {phrase_fear} (config 보장·0)")
    print("=" * 78)
    print(f"{'intent':<16}{'tags':>6}{'차트':>6}{'max/resp':>9}{'절단':>6}{'tokΔ범위':>14}")

    for domain, q in _DOMAINS.items():
        tags = charts_with = per_max = truncated = 0
        deltas: list[int] = []
        for rec in rows:
            b = BirthInput(**{**rec["input"], "reference_date": "2026-06-11"})
            cfg.SCORING_OPERATIONAL_APPLY_ENABLED = False
            off = chat_service.chat(b, q, today, dry_run=True).prompt_preview or ""
            cfg.SCORING_OPERATIONAL_APPLY_ENABLED = True
            cfg.SCORING_OPERATIONAL_APPLY_MODE = {"rank_guard": True,
                                                  "near_tie_demotion": False}
            cfg.SCORING_OPERATIONAL_COMPONENTS = {"conditional_byeong_downgrade": True,
                                                  "low_operability_yongsin": True}
            on = chat_service.chat(b, q, today, dry_run=True).prompt_preview or ""
            n = on.count(_TAG)
            tags += n
            charts_with += 1 if n else 0
            per_max = max(per_max, n)
            d = estimate_tokens(on) - estimate_tokens(off)
            deltas.append(d)
            if d < 0:
                truncated += 1
        td = f"{min(deltas)}~{max(deltas)}" if deltas else "-"
        print(f"{domain:<16}{tags:>6}{charts_with:>6}{per_max:>9}{truncated:>6}{td:>14}")
    cfg.SCORING_OPERATIONAL_APPLY_ENABLED = False  # 복원
    print("=" * 78)
    print("주: 절단=0·max/resp≤3·과장단어0 이어야 안전. tags=0 = 후보경로에 guardable 없음.")
    print("   coverage guard·score/rank/final/favorability 는 operational 산출 불변→flag 무관.")


if __name__ == "__main__":
    main()
