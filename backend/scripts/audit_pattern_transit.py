"""운 적용 구조 상태 감사 — 무작위 명식 × 전 대운(대운 층)의 상태 분포를 집계한다.

`doc/v2_2/PATTERN_TRANSIT_STATES.md` §6 의 실측 표를 다시 만드는 스크립트다(2026-11-13 데굴님 검수
"구조 배합 흐름 … 전체적으로 검수"). 읽기 전용이며 점수·저장소를 건드리지 않는다.

사용:
    cd backend && ../.venv/bin/python scripts/audit_pattern_transit.py [명식 수=150] [시드=20261113]

출력: 대운당 신규 성립 건수 분포, 유형별 신규, 원국 성립 패턴의 상태 분포, 맞수 구조 동시 작동 건수,
패턴별 (원국 성립 명식 수, 대운 신규 건수).
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from datetime import date, time

from saju_api.services import manse_service
from saju_engines import pattern_transit as pt
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput

#: 한 층에서 함께 작동하면 안 되는 구조 쌍(같은 재료를 반대로 부르는 이름).
RIVAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("JAE_SAENGGWAN", "JAE_SAENGSAL"),
    ("SUHWA_GIJE", "SUHWA_MIJE"),
    ("JESAL_TAEGWA", "SIKSIN_JESAL"),
    ("JESAL_TAEGWA", "SANGGWAN_JESAL"),
    ("JESAL_TAEGWA", "GWANSAL_YUJE"),
    ("GWANSAL_YUJE", "SALJUNG_JEGYEONG"),
)


def run(n_charts: int, seed: int) -> None:
    """무작위 명식 `n_charts` 개의 전 대운을 훑어 집계를 출력한다.

    Args:
        n_charts: 표본 명식 수(시주가 있는 명식만 센다).
        seed: 난수 시드(같은 시드면 같은 표본).
    """
    rng = random.Random(seed)
    new_by_pid: Counter[str] = Counter()
    new_by_type: Counter[str] = Counter()
    natal_status: Counter[tuple[str, str]] = Counter()
    natal_charts: Counter[str] = Counter()
    rival_hits: Counter[tuple[str, str]] = Counter()
    per_daewoon: list[int] = []
    charts = 0
    while charts < n_charts:
        birth = BirthInput(
            birth_date=date(rng.randint(1950, 2005), rng.randint(1, 12), rng.randint(1, 28)),
            birth_time=time(rng.randint(0, 23), rng.randint(0, 59)),
            birth_place_name="서울",
            gender=rng.choice(["male", "female"]),
        )
        result = manse_service.calculate(birth)
        if result.pillars is None or result.pillars.hour is None or result.force_analysis is None:
            continue
        charts += 1
        natal = detect_structure_patterns(result)
        for d in natal:
            if pt.transit_type_of(d.pattern_id) is not None:
                natal_charts[d.pattern_id] += 1
        daewoon: list[str] = []
        for _year, ganji in sorted(pt.daewoon_ganji_by_year(result).items()):
            if ganji not in daewoon:
                daewoon.append(ganji)
        for ganji in daewoon:
            states = pt.evaluate_pattern_states(
                result, natal, [pt.LuckGlyph("daewoon", ganji[0], ganji[1])]
            )
            news = [st for st in states if st.status_vs_parent == "new"]
            per_daewoon.append(len(news))
            for st in news:
                new_by_pid[st.pattern_id] += 1
                new_by_type[st.transit_type] += 1
            for st in states:
                if st.natal_established:
                    natal_status[(st.transit_type, st.status_vs_parent)] += 1
            operating = {st.pattern_id for st in states if st.operating}
            for pair in RIVAL_PAIRS:
                if set(pair) <= operating:
                    rival_hits[pair] += 1
    total = len(per_daewoon)
    print(f"명식 {charts} · 대운 {total} · 시드 {seed}")
    print(
        f"신규 성립 합 {sum(per_daewoon)} · 대운당 {sum(per_daewoon) / total:.2f}"
        f" · 0건 {sum(v == 0 for v in per_daewoon)} · 3건+ {sum(v >= 3 for v in per_daewoon)}"
        f" · 5건+ {sum(v >= 5 for v in per_daewoon)} · 최대 {max(per_daewoon)}"
    )
    print("유형별 신규:", dict(sorted(new_by_type.items())))
    print(
        "원국 성립 패턴 상태:",
        {f"{t}:{s}": c for (t, s), c in sorted(natal_status.items())},
    )
    print("맞수 구조 동시 작동:", {"+".join(k): c for k, c in rival_hits.items()} or "0건")
    print("\n패턴 | 원국 성립 명식 | 대운 신규")
    for pid, count in new_by_pid.most_common():
        print(f"  {pid:22s} {natal_charts[pid]:4d} {count:5d}")


if __name__ == "__main__":
    run(
        int(sys.argv[1]) if len(sys.argv) > 1 else 150,
        int(sys.argv[2]) if len(sys.argv) > 2 else 20261113,
    )
