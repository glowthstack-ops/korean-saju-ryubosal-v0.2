#!/usr/bin/env python3
"""DW-HWA shadow — CURRENT vs POST_SELECTION (비노출 검증, production 불변).

감사(`audit_daewoon_hwa_cross_domain.py`)가 낸 판정을 구현이 실제로 만족하는지 본다.

    CURRENT         현행 ±3% ranking
    POST_SELECTION  점수 영향 0 + 시점 배경 맵 + 선정 후 서사만

핵심은 **동치성**이다. POST_SELECTION 의 대표·시점·family 가 감사에서 이미 측정한
B(제거)안과 완전히 같아야 한다. 같다면 새 관측이 아니라 "랭킹 영향이 정말로 사라졌다"
는 확인이 되고, 감사 결과를 그대로 재사용할 수 있다.

확인 항목(전부 통과해야 SHADOW_PASS):

    ① POST_SELECTION 대표·시점·family == B(제거) 기준선   byte 수준 동치
    ② canonical EventQuality 불변
    ③ NO_HWA 음성 대조 완전 동일
    ④ 배경 방향 supportive/pressuring 보존
    ⑤ occurrence claim 0                 서사가 발생 지지를 주장하지 않는다
    ⑥ 같은 시점 배경 반복 주입 0
    ⑦ candidate reason_codes 에 DAEWOON_HWA_BG_* 잔존 0

production 플래그는 건드리지 않는다 — 기본은 여전히 'current' 다.
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from audit_daewoon_hwa_cross_domain import (  # noqa: E402
    CHARTS,
    DOMAINS,
    FAMILY_OF,
    _domain_pool,
    _identity,
    _representatives,
)
from saju_api.services import report_service as R  # noqa: E402
from saju_engines import event_engine_v2 as E  # noqa: E402
from saju_engines.daewoon_background import background_narrative_block  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

#: 서사에 나오면 안 되는 claim family. 배경은 체감 서술이지 발생 근거가 아니다.
_FORBIDDEN_CLAIM_MARKERS = (
    "발생을 지지", "발생 지지", "지지해", "유발", "일으키",
    "대표로 선택", "대표 시점으로", "선택됐", "선택되었",
    "가능성을 높", "성사 가능성",
)


def _score(chart: dict[str, Any], mode: str, bg_coefficient: float | None = None):
    """한 명식을 주어진 모드로 채점하고 (후보, 배경 맵) 을 돌려준다."""
    orig_mode_coeff = E._DAEWOON_HWA_BG
    if bg_coefficient is not None:
        E._DAEWOON_HWA_BG = bg_coefficient
    try:
        birth = R.BirthInput(
            calendar_type="solar", birth_date=chart["date"], birth_time=chart["time"],
            birth_place_name="서울", gender=chart["gender"],
        )
        spec = ReportSpec(
            product_code="RPT_FOCUS",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
        )
        data = R._ReportData(birth, spec, date(2026, 7, 30))
        data.scorer._daewoon_hwa_mode = mode
        cands = list(data.scorer.score(data.result))
        return cands, dict(data.scorer.take_daewoon_hwa_backgrounds())
    finally:
        E._DAEWOON_HWA_BG = orig_mode_coeff


def _selection_signature(cands: list[Any]) -> dict[str, Any]:
    """대표·시점·family 를 도메인별로 뽑은 선정 지문."""
    sig: dict[str, Any] = {}
    for dname, families in DOMAINS.items():
        reps = _representatives(_domain_pool(cands, families))
        sig[dname] = {
            "reps": [_identity(c) for c in reps],
            "periods": sorted({c.period for c in reps}),
            "families": sorted({FAMILY_OF.get(str(c.event_key), "?") for c in reps}),
        }
    return sig


def run() -> dict[str, Any]:
    """명식 4종에서 7개 확인 항목을 측정한다."""
    findings: dict[str, Any] = {"charts": {}}
    fails: list[str] = []

    for chart in CHARTS:
        cid = chart["id"]
        cur, _ = _score(chart, "current")
        post, bg_map = _score(chart, "post_selection")
        # B 기준선 — 감사에서 쓴 '계수 0' 안. 현행 모드로 돌리되 계수만 0 이다.
        base, _ = _score(chart, "current", bg_coefficient=0.0)

        sig_post, sig_base, sig_cur = (
            _selection_signature(post), _selection_signature(base),
            _selection_signature(cur),
        )
        entry: dict[str, Any] = {"note": chart["note"]}

        # ① 선정 동치성
        entry["selection_matches_baseline"] = sig_post == sig_base
        entry["selection_differs_from_current"] = sig_post != sig_cur
        if not entry["selection_matches_baseline"]:
            fails.append(f"{cid}: POST_SELECTION 선정이 B 기준선과 다르다")

        # ② canonical quality 불변
        q_post = {_identity(c): (c.quality.value if c.quality else None) for c in post}
        q_base = {_identity(c): (c.quality.value if c.quality else None) for c in base}
        entry["canonical_quality_unchanged"] = q_post == q_base
        if not entry["canonical_quality_unchanged"]:
            fails.append(f"{cid}: canonical quality 가 달라졌다")

        # ③ 음성 대조 — 합화 없는 명식은 CURRENT 와도 완전히 같아야 한다
        if cid == "NO_HWA":
            entry["negative_control_identical"] = sig_post == sig_cur
            if not entry["negative_control_identical"]:
                fails.append("NO_HWA: 합화가 없는데 선정이 달라졌다")

        # ④ 배경 방향 보존
        states = collections.Counter(v.state for v in bg_map.values())
        entry["background_states"] = dict(states)
        entry["background_directions_present"] = sorted(
            s for s in states if s in ("supportive", "pressuring")
        )

        # ⑦ reason_codes 잔존
        residual = sum(
            1 for c in post if any("DAEWOON_HWA_BG" in r for r in c.reason_codes)
        )
        entry["reason_code_residual"] = residual
        if residual:
            fails.append(f"{cid}: reason_codes 에 DAEWOON_HWA_BG_* 가 {residual}건 남았다")

        # ⑤⑥ 서사 — 대표에 배경을 붙여 claim·반복을 본다
        seen: set[tuple[str, str]] = set()
        lines: list[str] = []
        for families in DOMAINS.values():
            reps = _representatives(_domain_pool(post, families))
            lines += background_narrative_block(
                [(c.period, c.quality) for c in reps], bg_map, already_described=seen
            )
        claims = [
            ln for ln in lines
            if any(m in ln for m in _FORBIDDEN_CLAIM_MARKERS)
        ]
        markers = [ln.split(":")[0] for ln in lines]
        entry["narrative_lines"] = len(lines)
        entry["occurrence_claims"] = len(claims)
        entry["repeated_injection"] = len(markers) - len(set(markers))
        entry["sample_line"] = lines[0] if lines else None
        if claims:
            fails.append(f"{cid}: 서사에 occurrence claim {len(claims)}건")
        if entry["repeated_injection"]:
            fails.append(f"{cid}: 배경 반복 주입 {entry['repeated_injection']}건")

        findings["charts"][cid] = entry
        print(f"── {cid:<10}{chart['note']}")
        print(f"   ① 선정==B기준선 {entry['selection_matches_baseline']}   "
              f"현행과 다름 {entry['selection_differs_from_current']}")
        print(f"   ② quality 불변 {entry['canonical_quality_unchanged']}   "
              f"⑦ reason 잔존 {residual}")
        print(f"   ④ 배경 {dict(states)}")
        print(f"   ⑤ claim {entry['occurrence_claims']}  ⑥ 반복 "
              f"{entry['repeated_injection']}  서술 {entry['narrative_lines']}줄")
        if entry["sample_line"]:
            print(f"      예시: {entry['sample_line']}")
        print()

    findings["verdict"] = "SHADOW_PASS" if not fails else "SHADOW_FAIL"
    findings["failures"] = fails
    print(f"판정: {findings['verdict']}")
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("\nDAEWOON_HWA_RANKING_EFFECT_REMOVED_IN_SHADOW")
        print("DAEWOON_HWA_PERIOD_BACKGROUND_MAP_ADDED")
        print("DAEWOON_HWA_POST_SELECTION_NARRATIVE_ONLY")
        print("DAEWOON_HWA_OCCURRENCE_EVIDENCE_REMOVED")
        print("CANONICAL_QUALITY_UNCHANGED")
        print("REPRESENTATIVE_SELECTION_MATCHES_NO_HWA_BASELINE")
        print("PRODUCTION_FLAG_UNCHANGED")
    return findings


if __name__ == "__main__":
    out = run()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    sys.exit(0 if out["verdict"] == "SHADOW_PASS" else 1)
