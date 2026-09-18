"""REPORT-S1 — 도메인 후보 '흉운 예약' 정책 A/B/C replay (LLM 미호출, 결정론).

배경(2026-08-21 데굴님 확정): 현행 domain_candidates는 polarity 가 부정이라는 이유로
노출 슬롯을 예약한다(NEGATIVE_QUOTA ≤2). 상담 결론 의미론의 원칙은 '부정이라서'가
아니라 '사용자 판단을 바꿀 수 있어서(decision relevance)' 싣는 것이다. 세 정책을
같은 후보 풀에 돌려 선별 수준 지표를 비교한다 — production 변경 전 실측.

정책:
  A. 현행 — negative polarity reserve ≤2
  B. reserve 없음 — salience 순 상위 n
  C. decision-relevant caution reserve ≤1 — 아래 술어를 만족하는 부정 후보만 예약
     (favorability ≤ −0.2 / 차단형 게이트 / EXAM_FAIL·CAREER_EXIT 계열 결과축 코드)

지표: 정책별 부정 후보 수 · decision-relevant 포함/누락 수 · 단순 극성 예약으로만
실린 후보 수(결과 무관 caution 노출) · 같은 event family 중복.

사용:
  .venv/bin/python backend/scripts/report_reserve_replay.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (
    _BACKEND / "packages" / "shared_types",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "manse_core",
    _BACKEND / "packages" / "manse_analysis",
    _BACKEND / "packages" / "manse_calibration",
    _BACKEND / "apps" / "api",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services.report_service import _EVENT_DOMAIN, _ReportData  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.events import EventCandidate, EventPolarity  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_TODAY = date(2026, 8, 21)
_DOMAINS = ("career", "wealth", "relationship", "health")
_N = 6
_BLOCKING = ("GATE_business_start_no_wealth",)
_OUTCOME_ADVERSE = ("EXAM_FAIL", "CAREER_EXIT")


def _decision_relevant(c: EventCandidate) -> bool:
    """상담 행동을 바꿀 수 있는 caution 인가 — 단순 극성(압박·기신)만으로는 아니오."""
    if c.favorability <= -0.2:
        return True
    if any(code in _BLOCKING for code in c.evidence_path):
        return True
    return any(code.startswith(_OUTCOME_ADVERSE) for code in c.evidence_path)


def _select(pool: list[EventCandidate], policy: str, n: int = _N) -> list[EventCandidate]:
    """정책별 선별 — domain_candidates의 예약 tail만 교체(풀·정렬은 동일)."""
    negatives = [c for c in pool if str(c.polarity) == EventPolarity.NEGATIVE_OR_FORCED]
    others = [c for c in pool if str(c.polarity) != EventPolarity.NEGATIVE_OR_FORCED]
    if policy == "A":
        reserve = min(2, len(negatives))
        picked = others[: max(0, n - reserve)] + negatives[:reserve]
    elif policy == "B":
        picked = pool[:n]
    else:  # C — decision-relevant caution 만 예약(≤1)
        relevant = [c for c in negatives if _decision_relevant(c)]
        reserve = min(1, len(relevant))
        rest = [c for c in pool if not (reserve and c is relevant[0])]
        picked = rest[: max(0, n - reserve)] + relevant[:reserve]
    return picked[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    rows = [
        json.loads(line)
        for line in _CHARTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][: args.limit]
    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2026", end="2031"),
    )
    agg: dict[str, Counter] = {p: Counter() for p in ("A", "B", "C")}
    for row in rows:
        birth = BirthInput(**{**row["input"], "reference_date": str(_TODAY)})
        data = _ReportData(birth, spec, _TODAY)
        for domain in _DOMAINS:
            scoped = sorted(
                (
                    c for c in data.scored
                    if _EVENT_DOMAIN.get(str(c.event_key)) == domain
                    and "2026" <= c.period[:4] <= "2031"
                ),
                key=lambda c: (-c.score, c.period),
            )
            if not scoped:
                continue
            # 시점 대표 병합은 세 정책 공통 전제 — 여기서는 기간별 최고점만 남긴다.
            by_period: dict[str, EventCandidate] = {}
            for c in scoped:
                by_period.setdefault(c.period, c)
            pool = sorted(by_period.values(), key=lambda c: (-c.score, c.period))
            relevant_ids = {
                id(c) for c in pool
                if str(c.polarity) == EventPolarity.NEGATIVE_OR_FORCED
                and _decision_relevant(c)
            }
            for policy in ("A", "B", "C"):
                picked = _select(pool, policy)
                neg = [
                    c for c in picked
                    if str(c.polarity) == EventPolarity.NEGATIVE_OR_FORCED
                ]
                a = agg[policy]
                a["slots"] += len(picked)
                a["neg_picked"] += len(neg)
                a["relevant_picked"] += sum(1 for c in neg if id(c) in relevant_ids)
                a["irrelevant_neg_picked"] += sum(
                    1 for c in neg if id(c) not in relevant_ids
                )
                a["relevant_missed"] += sum(
                    1 for c in pool
                    if id(c) in relevant_ids and c not in picked
                )
                fams = Counter(str(c.event_key) for c in picked)
                a["family_dup"] += sum(v - 1 for v in fams.values() if v > 1)
    print(f"charts={len(rows)} domains={_DOMAINS} n={_N}")
    print(
        "policy | slots | neg | decision-relevant 포함 | 결과무관 부정 노출 | "
        "relevant 누락 | family 중복"
    )
    for p in ("A", "B", "C"):
        a = agg[p]
        print(
            f"  {p}    | {a['slots']:5d} | {a['neg_picked']:3d} | "
            f"{a['relevant_picked']:3d} | {a['irrelevant_neg_picked']:3d} | "
            f"{a['relevant_missed']:3d} | {a['family_dup']:3d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
