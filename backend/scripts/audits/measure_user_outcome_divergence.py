"""대안 역할표의 사용자 결과 차이 감사 — MC-E1 (CAL-ROLE-MARGIN-CENSUS, 2026-08-03).

MC-B·MC-D 에서 내부 축 판별자가 두 번 다 항등식으로 판명됐다. 그래서 이번에는 내부 축이
아니라 **production 이 실제로 만드는 사용자 출력**을 비교한다.

    _build_period_fortune(birth, intent, today, "yearly")   ← 실제 진입점

새 판별자를 발명하지 않는다. 존재하지 않는 의무 필드(caution_required 등)도 만들지
않는다(MC-E0).

**플래그를 운영과 맞춘다.** 기본값으로 돌리면 계층형 grounding 이 통째로 꺼져 다른 구성을
재게 된다(실측: hierarchy_lines 0줄). 플래그는 import 전에 세팅해야 모듈 상수에 반영된다.

primary parity 가 절대 게이트다. overlay 를 설치·복원한 뒤 primary 출력이 그대로여야
alternate 차이를 어댑터 결함이 아닌 실제 의미로 볼 수 있다.

사용법:
    python scripts/audits/measure_user_outcome_divergence.py --out var/audit/user_outcome
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

#: 운영 서버 프로세스와 동일한 플래그 집합. **import 보다 먼저** 세팅한다 — 모듈 상수로
#: 읽는 플래그가 있어 나중에 바꾸면 반영되지 않는다.
PRODUCTION_FLAGS: dict[str, str] = {
    "SAJU_PERIOD_HIERARCHY_ENABLED": "true",
    "SAJU_RELATION_SEMANTIC_PATCH_ENABLED": "true",
    "SAJU_PILLAR_POLARITY_V2_ENABLED": "true",
    "SAJU_LOCAL_ADVERSE_ONLY_ENABLED": "true",
    "SAJU_SAFE_TEMPLATE_FALLBACK_ENABLED": "true",
    "SAJU_EVENT_PROCESS_DUAL_RUN_ENABLED": "true",
    "SAJU_EVENT_LOCAL_TRIGGER_GATE_ENABLED": "false",
}
for _name, _value in PRODUCTION_FLAGS.items():
    os.environ.setdefault(_name, _value)

# sys.path 를 건드리지 않는다. editable 설치가 이미 패키지를 제공하고, `packages/` 를
# 넣으면 프로젝트 디렉터리 `packages/saju_engines/` 가 실제 패키지
# `packages/saju_engines/saju_engines/` 를 네임스페이스로 가려 `from saju_engines import
# EventEngineV2` 가 깨진다(실측).

from saju_manse_analysis.yongsin import candidates as cand_mod  # noqa: E402
from saju_manse_analysis.yongsin.role_realization import (  # noqa: E402
    RealizedRoleMap,
    resolve_realized_roles,
)

from saju_api.services import chat_service as cs  # noqa: E402
from saju_api.services import manse_service  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import event_scoring, precompute  # noqa: E402
from saju_engines.period_role_summary import build_period_role_summary  # noqa: E402
from saju_engines.signal_polarity import classify_relation_polarity  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.intent import IntentJson, TimeRange  # noqa: E402

#: baseline cohort — MC-A 와 동일 13건. 성별은 판정을 바꾸지 않아 하나만 쓴다.
BASELINE_CHARTS: tuple[tuple[int, int, int, str], ...] = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)
REFERENCE_DATE = date(2026, 7, 27)
TARGET_YEAR = "2026"

#: legacy operational cutoff — 대안 보존 판별자로 쓰지 않는다(MC-A).
LEGACY_NEAR_TIE_CUTOFF = Decimal("0.02")

_ROLE_KO = {
    "yongsin": "용신", "heesin": "희신", "gisin": "기신",
    "gusin": "구신", "hansin": "한신",
}


def _birth(year: int, month: int, day: int, hhmm: str) -> BirthInput:
    return BirthInput(
        birth_date=date(year, month, day), birth_time=hhmm,
        birth_place_name="서울", gender="male", reference_date=REFERENCE_DATE,
    )


def _intent() -> IntentJson:
    return IntentJson(
        intent_id="mc-e1", query_type="fortune_overview", domain="general",
        time_range=TimeRange(
            type="absolute", granularity="year", start=TARGET_YEAR),
    )


@contextmanager
def favorability_overlay(role_map: RealizedRoleMap):
    """`favorability_map` 조회만 alternate 역할표로 바꾼다.

    composite 빌더가 **내부에서** 이 함수를 부르므로 composite 단계부터 덮어야 한다.
    production 함수에 파라미터를 뚫지 않는다 — 아직 기능이 아니라 판별력 측정이다.

    세션 전역에 남지 않도록 반드시 복원하고, 호출부가 복원 여부를 검사한다.
    """
    replacement = {
        getattr(role_map, key): korean
        for key, korean in _ROLE_KO.items() if getattr(role_map, key)
    }
    originals = {
        event_scoring: event_scoring.favorability_map,
        precompute: precompute.favorability_map,
    }

    def _patched(_result: Any) -> dict[str, str]:
        return dict(replacement)

    try:
        for module in originals:
            module.favorability_map = _patched  # type: ignore[assignment]
        yield
    finally:
        for module, original in originals.items():
            module.favorability_map = original  # type: ignore[assignment]


def _fresh_capture(birth: BirthInput) -> tuple[Any, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    original = cand_mod.resolve_realized_roles
    cand_mod.resolve_realized_roles = _spy
    try:
        manse_service._cache.clear()
        result = calculate(birth)
        manse_service._cache.clear()
    finally:
        cand_mod.resolve_realized_roles = original
    return result, captured


def _fortune(birth: BirthInput) -> Any:
    manse_service._cache.clear()
    fortune = cs._build_period_fortune(birth, _intent(), REFERENCE_DATE, "yearly")
    manse_service._cache.clear()
    return fortune


def _signature(fortune: Any, favorability: dict[str, str]) -> dict[str, Any]:
    """3층 서명. 존재하는 production 값만 쓴다."""
    hierarchy = fortune.luck_hierarchy
    semantic: dict[str, Any] = {
        "overall_direction": None, "target_state": None, "background_state": None,
        "claim_axes": [], "polarity_states": {},
        "score_exclusions": {}, "active_layers": [],
    }
    if hierarchy is not None:
        summary = build_period_role_summary(hierarchy, favorability)
        semantic["overall_direction"] = summary.hierarchy_summary.value
        semantic["target_state"] = summary.target_state.value
        semantic["background_state"] = summary.background_state.value
        semantic["active_layers"] = [
            f"{p.layer.value}:{p.ganji}" for p in hierarchy.active_layers
        ]
        polarities = [classify_relation_polarity(i) for i in hierarchy.interactions]
        semantic["claim_axes"] = sorted({p.narrative_axis for p in polarities})
        semantic["polarity_states"] = dict(
            Counter(p.polarity_state.value for p in polarities))
        semantic["score_exclusions"] = dict(
            Counter(p.exclusion_reason.value for p in polarities))
    return {
        "semantic": semantic,
        "surface": {
            "hierarchy_lines": list(fortune.hierarchy_lines),
            "hierarchy_appendix": list(fortune.hierarchy_appendix),
            "luck_label": fortune.luck_label,
            "luck_summary": fortune.luck_summary,
            "pillar_line": fortune.pillar_line,
            "relation_lines": list(fortune.relation_lines),
            "slots": [
                {"name": s.name, "score": s.score, "summary": s.summary}
                for s in fortune.slots
            ],
        },
    }


def _classify(primary: dict[str, Any], alternate: dict[str, Any]) -> str:
    p_sem, a_sem = primary["semantic"], alternate["semantic"]
    p_sur, a_sur = primary["surface"], alternate["surface"]
    if p_sem == a_sem and p_sur == a_sur:
        return "USER_OUTPUT_IDENTICAL"
    if p_sem == a_sem:
        return "SURFACE_ONLY_DIVERGENCE"

    direction_changed = (
        p_sem["overall_direction"] != a_sem["overall_direction"]
        or p_sem["target_state"] != a_sem["target_state"]
        or p_sem["background_state"] != a_sem["background_state"]
    )
    axes_changed = p_sem["claim_axes"] != a_sem["claim_axes"]
    if direction_changed and axes_changed:
        return "MULTI_LAYER_DIVERGENCE"
    if direction_changed:
        return "RENDERED_CONCLUSION_DIVERGENCE"
    if axes_changed:
        return "AXIS_SET_DIVERGENCE"
    return "SCORING_DIVERGENCE_ONLY"


def _row(chart: tuple[int, int, int, str]) -> dict[str, Any]:
    birth = _birth(*chart)
    result, captured = _fresh_capture(birth)
    candidates = list(result.yongsin_analysis.useful_candidates)
    raw_scores = captured["useful_scores"]
    margin = (
        Decimal(repr(raw_scores[candidates[0].element][0]))
        - Decimal(repr(raw_scores[candidates[1].element][0]))
    )
    primary_roles = resolve_realized_roles(**captured).result
    _, second = _fresh_capture(birth)
    alternate_roles = resolve_realized_roles(**{
        **second, "selected_yongsin_element": candidates[1].element,
    }).result

    primary_favorability = {
        getattr(primary_roles.final_role_map, k): v for k, v in _ROLE_KO.items()
        if getattr(primary_roles.final_role_map, k)
    }
    alternate_favorability = {
        getattr(alternate_roles.final_role_map, k): v for k, v in _ROLE_KO.items()
        if getattr(alternate_roles.final_role_map, k)
    }

    before = _fortune(birth)
    with favorability_overlay(alternate_roles.final_role_map):
        overlay_installed = event_scoring.favorability_map(result) == (
            alternate_favorability)
        alternate_fortune = _fortune(birth)
    restored = event_scoring.favorability_map(result) == primary_favorability
    after = _fortune(birth)

    parity = before.model_dump() == after.model_dump()
    return {
        "chart": f"{chart[0]}-{chart[1]:02d}-{chart[2]:02d} {chart[3]}",
        "raw_margin": str(margin),
        "near_tie_legacy": margin <= LEGACY_NEAR_TIE_CUTOFF,
        "primary_element": candidates[0].element,
        "alternate_element": candidates[1].element,
        "overlay_installed": overlay_installed,
        "overlay_restored": restored,
        "primary_parity": parity,
        "primary_signature": _signature(before, primary_favorability),
        "alternate_signature": _signature(alternate_fortune, alternate_favorability),
        "divergence": _classify(
            _signature(before, primary_favorability),
            _signature(alternate_fortune, alternate_favorability),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = [_row(chart) for chart in BASELINE_CHARTS]
    parity_failures = [r["chart"] for r in rows if not r["primary_parity"]]
    overlay_failures = [
        r["chart"] for r in rows
        if not r["overlay_installed"] or not r["overlay_restored"]
    ]

    near = [r for r in rows if r["near_tie_legacy"]]
    wide = [r for r in rows if not r["near_tie_legacy"]]
    summary: dict[str, Any] = {
        "verdict": (
            "PRIMARY_SHADOW_PARITY_FAILED" if parity_failures or overlay_failures
            else "USER_OUTCOME_DIVERGENCE_DISTRIBUTION_MEASURED"
        ),
        "production_flags": PRODUCTION_FLAGS,
        "cohort": "baseline",
        "charts": len(rows),
        "primary_parity_failures": parity_failures,
        "overlay_failures": overlay_failures,
        "divergence_distribution": dict(Counter(r["divergence"] for r in rows)),
        "near_tie": dict(Counter(r["divergence"] for r in near)),
        "non_near_tie": dict(Counter(r["divergence"] for r in wide)),
        "by_chart": [
            {
                "chart": r["chart"], "raw_margin": r["raw_margin"],
                "near_tie": r["near_tie_legacy"], "divergence": r["divergence"],
                "primary_direction":
                    r["primary_signature"]["semantic"]["overall_direction"],
                "alternate_direction":
                    r["alternate_signature"]["semantic"]["overall_direction"],
                "primary_axes": r["primary_signature"]["semantic"]["claim_axes"],
                "alternate_axes": r["alternate_signature"]["semantic"]["claim_axes"],
            }
            for r in sorted(rows, key=lambda x: Decimal(x["raw_margin"]))
        ],
    }

    (args.out / "rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
