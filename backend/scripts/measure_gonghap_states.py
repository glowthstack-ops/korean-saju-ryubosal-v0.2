#!/usr/bin/env python3
"""공합 상태 비교 측정(2026-10-25 데굴님 확정 기준) — 85사례 180명식 원국의 공합을 두 정책으로 판정.

정책 A: 월령 旺·相만 유효 허용 / 정책 B(기본): 休 조건부(투간 + 독립 지원) 허용.
B 에서만 새로 유효(effective/strengthened)가 된 사례를 나열한다 — 자료 권고 "休 때문에 새로
유효해진 사례만 검토". 점수·배포 불변(측정 전용). 결과 var/gonghap_states_<날짜>.md.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_manse_analysis.relations import hap_modes as hm  # noqa: E402

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402

_CASES = _BACKEND / "tests" / "fixtures" / "comparison_casebook" / "cases.jsonl"


def _states(result, xiu: bool) -> list[tuple[str, str, str]]:
    hm.HAP_EXPERIMENTS["gonghap_xiu_conditional"] = xiu
    out = []
    for r in hm.resolve_branch_hap(result.pillars, {}):
        if r.kind == "gonghap":
            out.append(("".join(r.members), r.gonghap_state, r.notes[0] if r.notes else ""))
    return out


def main() -> int:
    saved = hm.HAP_EXPERIMENTS["gonghap_xiu_conditional"]
    cnt_a: Counter[str] = Counter()
    cnt_b: Counter[str] = Counter()
    newly: list[str] = []
    subjects = 0
    for line in _CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        for s in case["subjects"]:
            try:
                r = calculate(BirthInput(
                    calendar_type="solar", birth_date=s["date"],
                    birth_time=s.get("time") or "12:00", birth_place_name="서울",
                    gender="male" if s["gender"] == "M" else "female",
                ))
            except Exception:  # noqa: BLE001
                continue
            if r.pillars is None:
                continue
            subjects += 1
            a = _states(r, False)
            b = _states(r, True)
            for _m, st, _w in a:
                cnt_a[st] += 1
            for _m, st, _w in b:
                cnt_b[st] += 1
            sa = {m: st for m, st, _ in a}
            good = ("effective", "strengthened")
            for m, st, why in b:
                if st in good and sa.get(m) not in good:
                    newly.append(
                        f"| {case['case_id']}/{s['key']} | {m} | {sa.get(m)}→{st} | {why} |"
                    )
    hm.HAP_EXPERIMENTS["gonghap_xiu_conditional"] = saved
    stamp = dt.date.today().strftime("%Y%m%d")
    out = _BACKEND.parent / "var" / f"gonghap_states_{stamp}.md"
    lines = [
        "# 공합 상태 비교 — 정책 A(旺·相만) vs 정책 B(休 조건부)",
        f"명식 {subjects}개(85사례 원국만, 운 미포함)",
        "",
        f"- A 상태 분포: {dict(cnt_a)}",
        f"- B 상태 분포: {dict(cnt_b)}",
        f"- B 에서만 새로 유효: {len(newly)}건",
        "", "| 사례 | 공합 | 상태 변화 | 근거 |", "|---|---|---|---|", *newly,
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
