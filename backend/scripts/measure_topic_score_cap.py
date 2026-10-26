"""토픽 요약 점수 100 상한 측정 — 유지/변경 결정 자료.

2026-10-26 데굴님 "테스트를 통해 유지 여부나 상한을 확정".

배경: `topic_builder._domain_series_findings`(M01 등)·`build_career_context`(M07)는 시기별 도메인
신호 가중치 합 ×100 을 0~100 으로 자르고, 그 점수로 findings 를 정렬해 채팅은 상위 3·리포트는
상위 4·TopicContext 는 상위 5 만 남긴다. 합 ≥1.0 이면 전부 100 으로 포화해 **정렬이 period_key
순(이른 달 우선)으로 퇴화**하고, 명식이 달라도 같은 줄이 나온다(실답 2026-10-26).

측정: 85사례 재생 모집단(`var/casebook_replay/subjects.jsonl`, date/time 재현된 명식)의 각 명식에
대해 '만 30세 10-26' 을 오늘로 두고 채팅과 같은 방식(연+월 composite, 올해~+5년)으로 M01·M07
시기 행을 만든 뒤 아래를 비교한다.
  A  현행: score = min(100, round(sum×100)), 정렬 score
  B  정렬만 원합(sum)·표시는 현행 상한 — 표시 의미 불변, 포화 동률만 해소
  C_S 선형 재척도: score = min(100, round(sum/S×100)), S ∈ {1.5, 2.0, 2.5, 3.0}
  D  로그 압축: score = round(100×(1−e^(−sum)))
지표: 포화 행 비율, sum 분포(p50/p90/p95/p99/max), 명식 단위 '상위 3 경계 동률'(채팅 Top-3 가
임의 절단되는 명식 비율)·'상위 5 경계 동률', A 대비 B 의 Top-3 집합 불일치 명식 비율.

사용: cd backend && ../.venv/bin/python scripts/measure_topic_score_cap.py
출력: var/topic_score_cap_20261026.json · .md
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND / "scripts"))

from casebook_replay import _VARIANTS, _birth  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import topic_builder as tb  # noqa: E402
from saju_engines.precompute import CompositeBuilder  # noqa: E402
from saju_shared_types.precompute import CompositeLevel  # noqa: E402
from saju_shared_types.topic_context import PeriodSpec  # noqa: E402

_DICTS = _BACKEND / "dictionaries"
_SUBJECTS = _ROOT / "var" / "casebook_replay" / "subjects.jsonl"
_OUT_JSON = _ROOT / "var" / "topic_score_cap_20261026.json"
_OUT_MD = _ROOT / "var" / "topic_score_cap_20261026.md"
_VARIANT_BY_NAME = dict(_VARIANTS)
_SCALES = (1.5, 2.0, 2.5, 3.0)


@dataclass
class Row:
    """명식 × 시기 한 행 — 신호 수와 원합."""

    subject: str
    module: str
    period_key: str
    n: int
    raw: float


def _variant_dict(name: str | None) -> dict[str, Any] | None:
    """subjects.jsonl 의 변형 태그('no_dst-1h' 등)에서 시간 옵션 dict 를 복원한다."""
    if not name:
        return None
    base = name.split("+")[0].split("-")[0] if name[-1] == "h" else name
    return _VARIANT_BY_NAME.get(base) or None


def _rows_for(subject: str, birth, today: date) -> list[Row]:
    """채팅 `_topic_signal_lines` 와 같은 조립으로 M01·M07 시기 행을 만든다."""
    chart = calculate(birth.model_copy(update={"reference_date": today}))
    composites = CompositeBuilder(_DICTS).build(
        chart, "chat", "1.0.0", f"{today.isoformat()}T00:00:00+00:00",
        levels={CompositeLevel.YEAR, CompositeLevel.MONTH},
    )
    period = PeriodSpec(start=str(today.year), end=str(today.year + 5), granularity="year")
    selected = [
        c for c in composites
        if c.level in tb._LEVELS_YM and tb._in_period(c.period_key, period)
    ]
    out: list[Row] = []
    stats = tb.NormalizationStats()
    for c in selected:
        love = [
            s for s in tb.normalize_domain_signals(c.domain_signals, stats)
            if s.domain in {"relationship"}
            and tb._signal_key_match(
                s, set(tb.M01_EVENT_KEYS), None, set(tb.M01_LEGACY_EXCLUDE_KEYS),
            )
        ]
        if love:
            out.append(Row(subject, "M01", c.period_key, len(love), sum(s.weight for s in love)))
        career = [s for s in c.domain_signals if s.domain == "career"]
        if career:
            out.append(
                Row(subject, "M07", c.period_key, len(career), sum(s.weight for s in career))
            )
    return out


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    k = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return ys[k]


def _score(raw: float, scheme: str) -> float:
    if scheme == "A":
        return float(max(0, min(100, round(raw * 100))))
    if scheme == "B":
        return raw  # 정렬 키만 원합
    if scheme.startswith("C_"):
        s = float(scheme[2:])
        return float(max(0, min(100, round(raw / s * 100))))
    if scheme == "D":
        return float(round(100 * (1 - math.exp(-raw))))
    raise ValueError(scheme)


def _boundary_tie(scores: list[float], k: int) -> bool:
    """내림차순 정렬에서 k번째와 k+1번째가 같은 점수인가(= Top-k 절단이 임의)."""
    if len(scores) <= k:
        return False
    ys = sorted(scores, reverse=True)
    return ys[k - 1] == ys[k]


def _topk_set(rows: list[Row], scheme: str, k: int) -> frozenset[str]:
    """채팅 정렬(점수 내림차순, 동률은 period_key 순 — 현행 sort 안정성)과 같은 Top-k 집합."""
    ordered = sorted(sorted(rows, key=lambda r: r.period_key), key=lambda r: -_score(r.raw, scheme))
    return frozenset(r.period_key for r in ordered[:k])


def summarize(rows: list[Row]) -> dict[str, Any]:
    """모듈별 지표 사전."""
    out: dict[str, Any] = {}
    by_mod: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_mod[r.module].append(r)
    schemes = ["A", "B", *[f"C_{s}" for s in _SCALES], "D"]
    for mod, rs in sorted(by_mod.items()):
        raws = [r.raw for r in rs]
        by_subj: dict[str, list[Row]] = defaultdict(list)
        for r in rs:
            by_subj[r.subject].append(r)
        n_subj = len(by_subj)
        m: dict[str, Any] = {
            "rows": len(rs), "subjects": n_subj,
            "raw_p50": round(_pct(raws, 0.5), 3),
            "raw_p90": round(_pct(raws, 0.9), 3),
            "raw_p95": round(_pct(raws, 0.95), 3),
            "raw_p99": round(_pct(raws, 0.99), 3),
            "raw_max": round(max(raws), 3) if raws else 0.0,
            "n_signals_p50": _pct([float(r.n) for r in rs], 0.5),
            "saturated_rows_share_A": (
                round(sum(1 for x in raws if x >= 1.0) / len(rs), 4) if rs else 0.0
            ),
            "subjects_ge4_saturated_share": round(
                sum(1 for v in by_subj.values() if sum(1 for r in v if r.raw >= 1.0) >= 4)
                / n_subj,
                4,
            ) if n_subj else 0.0,
            "schemes": {},
        }
        for sch in schemes:
            sat = (
                sum(1 for x in raws if _score(x, sch) >= 100) / len(rs) if sch != "B" else None
            )
            subj_scores = [[_score(r.raw, sch) for r in v] for v in by_subj.values()]
            tie3 = sum(1 for sc in subj_scores if _boundary_tie(sc, 3)) / n_subj
            tie5 = sum(1 for sc in subj_scores if _boundary_tie(sc, 5)) / n_subj
            diff3 = sum(
                1 for v in by_subj.values() if _topk_set(v, sch, 3) != _topk_set(v, "A", 3)
            ) / n_subj
            m["schemes"][sch] = {
                "saturated_rows_share": None if sat is None else round(sat, 4),
                "top3_boundary_tie_subjects_share": round(tie3, 4),
                "top5_boundary_tie_subjects_share": round(tie5, 4),
                "top3_set_differs_from_A_share": round(diff3, 4),
            }
        out[mod] = m
    return out


def main() -> int:
    rows: list[Row] = []
    n_ok = n_err = 0
    for line in _SUBJECTS.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if not rec.get("date_used") or not rec.get("time_used") or rec.get("error"):
            continue
        subject = f"{rec['case_id']}:{rec['key']}"
        try:
            birth = _birth(
                rec["date_used"], rec["time_used"], rec["gender"],
                _variant_dict(rec.get("variant")),
            )
            by = date.fromisoformat(rec["date_used"]).year
            rows.extend(_rows_for(subject, birth, date(by + 30, 10, 26)))
            n_ok += 1
        except Exception as exc:  # noqa: BLE001 — 측정 스크립트: 실패 명식은 건수로만 기록
            n_err += 1
            print(f"[skip] {subject}: {exc}", file=sys.stderr)
    summary = summarize(rows)
    payload = {"subjects_ok": n_ok, "subjects_error": n_err, "modules": summary}
    _OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# 토픽 점수 100 상한 측정 (2026-10-26) — 명식 {n_ok}건(실패 {n_err})", ""]
    for mod, m in summary.items():
        md += [
            f"## {mod} — 행 {m['rows']} · 명식 {m['subjects']}",
            f"- 원합 분포: p50 {m['raw_p50']} · p90 {m['raw_p90']} · p95 {m['raw_p95']} · "
            f"p99 {m['raw_p99']} · max {m['raw_max']} · 신호수 p50 {m['n_signals_p50']}",
            f"- 현행 포화 행 비율 {m['saturated_rows_share_A']:.1%} · "
            f"포화 시기 ≥4개 명식 비율 {m['subjects_ge4_saturated_share']:.1%}",
            "",
            "| 방식 | 포화 행 | Top-3 경계 동률 명식 | Top-5 경계 동률 명식 "
            "| Top-3 집합 ≠ A 명식 |",
            "|---|---|---|---|---|",
        ]
        for sch, v in m["schemes"].items():
            sat = (
                "—" if v["saturated_rows_share"] is None
                else f"{v['saturated_rows_share']:.1%}"
            )
            md.append(
                f"| {sch} | {sat} | {v['top3_boundary_tie_subjects_share']:.1%} | "
                f"{v['top5_boundary_tie_subjects_share']:.1%} | "
                f"{v['top3_set_differs_from_A_share']:.1%} |"
            )
        md.append("")
    _OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
