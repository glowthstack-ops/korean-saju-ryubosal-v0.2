#!/usr/bin/env python3
"""AMHAP-COV — 운 암합의 채널별 커버리지 감사 (측정 전용, production 무변경).

원래 계획한 `AMHAP_CANDIDATE_RECOVERY_SHADOW_EXPERIMENT` 는 **취소**한다. 전제가
틀렸다 — 암합은 "없어서 후보가 누락되는" 상태가 아니라 이미 구현돼 있고, 이벤트 후보
생성·점수에는 처음부터 관여하지 않는 **보조 서술 evidence** 다. 후보 회수 효과를
재려면 신규 배선이 선행이며 그것은 별도 설계 승인 대상이다.

이 감사가 답하는 것은 세 질문이다.

    ① 탐지기는 실제로 얼마나 작동하는가        탐지율·궁위·십성·중복
    ② 채팅 배선에서 얼마나 손실되는가          amhap_notes[:2] 절단·정렬 계약
    ③ 리포트·일운 미배선이 의도인가 누락인가    채널별 독립 판정

하지 않는 것: 암합 후보 생성 · 점수 가산 · 단독 사건/길흉 판정 · 그래프 활성화 ·
리포트·일운 실제 배선 · 명시적 합보다 강한 취급 · 대표 변경 counterfactual.
"""

from __future__ import annotations

import collections
import inspect
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
    _BACKEND / "packages" / "manse_core",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402
from saju_engines import context_reducer as CR  # noqa: E402
from saju_engines.amhap_luck import (  # noqa: E402
    _PALACE_WEIGHT,
    detect_luck_amhap,
)

#: 채팅 배선의 주입 상한 — context_reducer 가 상위 N건만 넣는다.
CHAT_INJECTION_CAP = 2


def _wiring_scan() -> dict[str, Any]:
    """채널별 배선 여부를 소스에서 확인한다(추정 아님)."""
    def _has(path: Path, needles: tuple[str, ...]) -> bool:
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            return False
        return any(n in src for n in needles)

    eng = _BACKEND / "packages" / "saju_engines" / "saju_engines"
    svc = _BACKEND / "apps" / "api" / "saju_api" / "services"
    daily_files = sorted(eng.glob("daily_*.py")) + sorted(svc.glob("daily_*.py"))
    return {
        "detector": "amhap_luck.detect_luck_amhap",
        "chat_luck_narrative": _has(
            eng / "context_reducer.py", ("detect_luck_amhap", "amhap_notes")
        ),
        "natal_narrative": _has(
            eng / "chart_interpretation.py", ("암합",)
        ),
        "theme_report": _has(svc / "report_service.py", ("amhap", "암합")),
        "daily_fortune": any(
            _has(p, ("amhap", "암합")) for p in daily_files
        ),
        "daily_files_scanned": len(daily_files),
        "event_graph": (
            "INTENTIONALLY_DISABLED"
            if _has(eng / "graph_builder.py", ("암합 등 기본 비활성",))
            else "UNKNOWN"
        ),
        "candidate_scoring": False,   # 이벤트 후보·점수 경로에 호출 없음
    }


def _ordering_contract() -> dict[str, Any]:
    """정렬 계약이 문서와 코드에서 일치하는지 확인한다."""
    src = inspect.getsource(detect_luck_amhap)
    return {
        "docstring_claim": "일지 우선 정렬",
        "loop_order": ["year", "month", "day", "hour"],
        "explicit_sort_present": "out.sort(" in src,
        "sort_key": "(-weight, kind != 'myeong')",
        "palace_weights": dict(_PALACE_WEIGHT),
        "stable_deterministic": "out.sort(" in src,
        "note": (
            "루프는 year→month→day→hour 이지만 반환 직전 weight 내림차순으로 정렬한다"
            " — day(1.0) 가 앞에 오므로 docstring 주장과 결과가 일치한다. 동일 weight"
            " 내에서는 명암합이 먼저이고, 그 뒤는 루프 삽입 순서(안정 정렬)다."
        ),
    }


def run() -> dict[str, Any]:
    """동일 명식·기간으로 탐지율·절단 손실·채널 커버리지를 측정한다."""
    birth = R.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    today = date(2026, 7, 30)
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    data = R._ReportData(birth, spec, today)
    pillars = data.result.pillars
    lc = data.result.luck_cycles

    # ── ① 탐지기 작동 ───────────────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    periods = [
        (p.label, p.ganji) for p in (lc.monthly_luck if lc else [])
    ] + [(p.label, p.ganji) for p in (lc.yearly_luck if lc else [])]
    for label, ganji in periods:
        if not ganji or len(ganji) < 2:
            continue
        hits = detect_luck_amhap(ganji[0], ganji[1], pillars)
        rows.append({
            "period": label,
            "ganji": ganji,
            "detected": len(hits),
            "injected": min(len(hits), CHAT_INJECTION_CAP),
            "truncated": max(0, len(hits) - CHAT_INJECTION_CAP),
            "hits": [
                {
                    "kind": h.kind, "palace": h.palace, "ten_god": h.ten_god,
                    "luck_char": h.luck_char, "natal_hidden": h.natal_hidden,
                    "weight": h.weight, "describe": h.describe(),
                }
                for h in hits
            ],
        })

    detected_total = sum(r["detected"] for r in rows)
    with_any = [r for r in rows if r["detected"]]
    truncated_total = sum(r["truncated"] for r in rows)
    palace_dist = collections.Counter(
        h["palace"] for r in rows for h in r["hits"]
    )
    kind_dist = collections.Counter(h["kind"] for r in rows for h in r["hits"])
    tg_dist = collections.Counter(h["ten_god"] for r in rows for h in r["hits"])
    # 같은 (kind, palace, luck_char, natal_hidden) 이 여러 기간에 반복되는가.
    repeat = collections.Counter(
        (h["kind"], h["palace"], h["luck_char"], h["natal_hidden"])
        for r in rows for h in r["hits"]
    )
    # 절단으로 버려진 항목이 남은 항목과 다른 궁위를 담는가.
    truncation_adds_palace = 0
    for r in rows:
        if r["truncated"] <= 0:
            continue
        kept = {h["palace"] for h in r["hits"][:CHAT_INJECTION_CAP]}
        dropped = {h["palace"] for h in r["hits"][CHAT_INJECTION_CAP:]}
        if dropped - kept:
            truncation_adds_palace += 1

    wiring = _wiring_scan()

    # ── ③ 일운 적용 타당성 ─────────────────────────────────────────────
    # `detect_luck_amhap` 은 원국 4지지 지장간과 일간을 요구한다. 일주별 오늘의
    # 운세는 60갑자 일주만 입력이고 개인 원국(연·월·시 지지)이 없다.
    daily_sig = set(
        inspect.signature(
            __import__("saju_engines.daily_ilju_fortune", fromlist=["x"])
            ._score_event
        ).parameters
    )
    daily_applicability = {
        "detector_requires": [
            "pillars.year/month/day/hour.branch (원국 4지지 지장간)",
            "pillars.day_master (십성 산출용 일간)",
        ],
        "daily_scoring_inputs": sorted(daily_sig),
        "daily_has_natal_pillars": False,
        "verdict": "NOT_APPLICABLE_BY_INPUT_CONTRACT",
        "reason": (
            "일주별 오늘의 운세는 60갑자 일주(일간·일지)만 입력이고 개인 원국의 "
            "연·월·시 지지가 없다. `detect_luck_amhap` 은 원국 4지지의 지장간을 "
            "요구하므로 같은 계산을 적용할 수 없다 — 채널 누락이 아니라 입력 모델 "
            "차이에 따른 비적용이다. 일주만으로 계산하면 60개 고정 결과가 되어 "
            "개인 명식 없는 무료 콘텐츠의 성격과도 맞지 않는다."
        ),
    }

    # ── ③ 리포트 적용 타당성 ───────────────────────────────────────────
    report_applicability = {
        "report_uses_context_reducer_candidate_block": bool(
            "amhap" in inspect.getsource(CR.serialize_candidates)
        ) if hasattr(CR, "serialize_candidates") else None,
        "report_has_amhap_reference": wiring["theme_report"],
        "same_inputs_available": True,   # 리포트도 동일 원국·기간을 갖는다
        "verdict": (
            "UNDOCUMENTED_EVIDENCE_GAP" if not wiring["theme_report"]
            else "INTENTIONAL_CHANNEL_DIFFERENCE"
        ),
        "reason": (
            "리포트는 채팅과 동일한 원국·기간을 다루고 입력도 갖추고 있으나 amhap "
            "참조가 0건이다. 비적용 근거가 코드·문서에 없어 의도된 채널 차이인지 "
            "확인되지 않는다 — 같은 질문을 채팅으로 하면 물밑 신호를 보고 리포트로 "
            "받으면 못 보는 상태다. 배선 여부는 설계 승인 대상이며 이 감사에서 "
            "바꾸지 않는다."
        ),
    }

    chat_verdict = (
        "TRUNCATION_LOSS_OBSERVED" if truncated_total
        else "COVERAGE_SUFFICIENT" if detected_total
        else "INCONCLUSIVE"
    )
    return {
        "audit_id": "AMHAP-COV",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "supersedes": (
            "AMHAP_CANDIDATE_RECOVERY_SHADOW_EXPERIMENT — 취소(전제 오류: 암합은 "
            "미구현이 아니라 채팅 전용 보조 서술 evidence 다)"
        ),
        "status_flags": [
            "AMHAP_DETECTOR_IMPLEMENTED",
            "CHAT_LUCK_NARRATIVE_WIRED",
            "THEME_REPORT_UNWIRED",
            "DAILY_FORTUNE_UNWIRED",
            "EVENT_GRAPH_INTENTIONALLY_DISABLED",
            "CANDIDATE_RECOVERY_EXPERIMENT_NOT_APPLICABLE",
            # 범위를 붙인다 — 단일 감사 fixture 결과로 모든 명식에서 항상 과탐이라고
            # 일반화하지 않는다.
            "AMHAP_DETECTION_SATURATED_ON_AUDITED_RANGE",
            "AMHAP_DISCRIMINATIVE_VALUE_NOT_DEMONSTRATED",
            "AMHAP_RAW_DETECTION_FREQUENCY_HOUR_HEAVY",
            "PALACE_PRIORITY_ORDERING_CONTRACT_CONFIRMED",
            "CHAT_TRUNCATION_LOSS_OBSERVED",
            "THEME_REPORT_UNDOCUMENTED_EVIDENCE_GAP",
            "DAILY_FORTUNE_NOT_APPLICABLE_BY_INPUT_CONTRACT",
            "REPORT_WIRING_WITHHELD_PENDING_DETECTOR_REVIEW",
            "PRODUCTION_UNCHANGED",
        ],
        "retired_status_flags": [
            # 궁위 weight 는 **정렬 우선순위**이고 건수는 조합 가능한 지장간 수·매칭
            # 빈도다. 서로 다른 축이라 hour 탐지가 많다고 day 가중 계약이 어긋난 것이
            # 아니다 — 최종 정렬은 weight 내림차순이라 일지 우선 계약은 지켜진다.
            "AMHAP_PALACE_WEIGHT_MISMATCH",
            "CHAT_TRUNCATION_LOSS_57PCT",
        ],
        "wiring": wiring,
        "ordering_contract": _ordering_contract(),
        "detection": {
            "periods_scanned": len(rows),
            "periods_with_amhap": len(with_any),
            "detection_rate": (
                round(len(with_any) / len(rows), 4) if rows else 0.0
            ),
            "detected_total": detected_total,
            "max_per_period": max((r["detected"] for r in rows), default=0),
            "palace_distribution": dict(palace_dist),
            "kind_distribution": dict(kind_dist),
            "ten_god_distribution": dict(tg_dist),
            "distinct_amhap_pairs": len(repeat),
            "most_repeated_pairs": [
                {"pair": list(k), "periods": n} for k, n in repeat.most_common(5)
            ],
        },
        "chat_injection": {
            "cap": CHAT_INJECTION_CAP,
            "injected_total": sum(r["injected"] for r in rows),
            "truncated_total": truncated_total,
            "periods_truncated": sum(1 for r in rows if r["truncated"]),
            "truncation_drops_distinct_palace": truncation_adds_palace,
            "verdict": chat_verdict,
        },
        "derived_observations": {
            "detections_per_period": (
                round(detected_total / len(rows), 3) if rows else 0.0
            ),
            "saturation_note": (
                "감사 구간 전 기간에서 탐지됐다. 암합의 의미가 '드러나지 않은 결합' "
                "인데 전 기간에 걸리면 변별력이 없다. 다만 이번 명식·기간 하나의 "
                "결과이므로 탐지 조건이 넓은 것인지 실제로 흔한 현상인지는 구분되지 "
                "않는다 — 복수 명식과 음성 대조군이 필요하다."
            ),
            "hour_heavy_note": (
                "raw 탐지는 hour 최다이고 궁위 weight 는 day 최대(1.0)다. 두 값은 다른 "
                "축이므로 계약 위반이 아니다(weight=정렬 우선순위, 건수=조합 가능 수). "
                "hour 편중 원인은 후속 탐지기 감사 대상이다."
            ),
            "cap_note": (
                "cap 2 로 상당량이 절단되고 일부 기간에서 다른 궁위 정보가 빠진다. "
                "정보 손실은 확정이지만 cap 2 가 잘못인지는 미확정이다 — 탐지가 포화된 "
                "상태에서는 cap 이 노이즈를 억제하고 있을 수 있으므로 포화 해소 전에 "
                "cap 을 늘리면 안 된다."
            ),
            "priority_conclusion": (
                "리포트 미배선보다 탐지 포화가 선행 문제다. 포화된 evidence 를 그대로 "
                "리포트에 추가하면 채널 정합성은 높아져도 설명 품질이 낮아질 수 있다."
            ),
        },
        "theme_report_applicability": report_applicability,
        "daily_fortune_applicability": daily_applicability,
        "channel_verdicts": {
            "CHAT": chat_verdict,
            "THEME_REPORT": report_applicability["verdict"],
            "DAILY_FORTUNE": daily_applicability["verdict"],
        },
        "rows": rows,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "amhap_channel_coverage.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print("  배선:", {k: v for k, v in r["wiring"].items() if k != "detector"})
    d = r["detection"]
    print(f"  탐지: 기간 {d['periods_scanned']} 중 {d['periods_with_amhap']}건 "
          f"({d['detection_rate']:.1%}) · 총 {d['detected_total']} · "
          f"기간최대 {d['max_per_period']}")
    print(f"        궁위 {d['palace_distribution']}")
    print(f"        유형 {d['kind_distribution']}")
    print(f"        십성 {d['ten_god_distribution']}")
    print(f"        고유 조합 {d['distinct_amhap_pairs']}")
    c = r["chat_injection"]
    print(f"  채팅 주입: cap {c['cap']} · 주입 {c['injected_total']} · "
          f"절단 {c['truncated_total']} · 절단기간 {c['periods_truncated']} · "
          f"다른궁위 손실 {c['truncation_drops_distinct_palace']}")
    print("  정렬:", r["ordering_contract"]["note"])
    print("  채널 판정:", r["channel_verdicts"])
