"""경계 당일 명식 변형별 사건 점수 완전 분기 (2026-10-06, HOUR_UNKNOWN_POLICY.md §7).

출생시간 미상 + 경계 당일(입춘·절입·일 경계)이면 명식 자체가 2갈래 이상이다. 표시 변형의 후보만
LLM 에 주면 다른 변형의 시기는 추측하게 되므로, **변형마다 그 변형의 명식으로 사건 점수 파이프라인을
따로 돌려** 변형별 시기 후보 블록을 만든다. 점수·극성은 변형별 엔진 계산값이며 LLM 은 재계산하지
않는다(절대원칙 1).

- 대상: 표시(base) 변형을 제외한 나머지 변형. 표시 변형 후보는 기존 payload 가 이미 담는다.
- 범위: 표시 변형의 선별 후보가 있는 기간(월·연) 집합으로 맞춘다 — 같은 창 안에서 비교하기 위해서.
  후보가 없으면 보고서 기간(연 범위) 또는 전체.
- 변형 명식 계산은 `hour_branch_candidates` 로 그 변형을 선택한 BirthInput 을 `calculate()` 에 넣어
  얻는다(manse_service._unknown_anchor 가 기준 시각을 그 범위로 잡는다).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any

from saju_engines.context_reducer import event_ko, polarity_ko, tone_for_score
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.manse_result import ManseV2Result

from . import manse_service

_logger = logging.getLogger(__name__)
_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}
MAX_PER_VARIANT = 5
MAX_DIFF = 3


def _letter(i: int) -> str:
    return chr(ord("A") + i)


def _period_scope(
    base_candidates: Sequence[Any], period_start: str | None, period_end: str | None,
) -> tuple[set[str], set[str], tuple[str, str] | None]:
    periods = {str(c.period) for c in base_candidates}
    years = {p[:4] for p in periods}
    rng = (period_start[:4], period_end[:4]) if period_start and period_end else None
    return periods, years, rng


def _in_scope(
    period: str, periods: set[str], years: set[str], rng: tuple[str, str] | None,
) -> bool:
    """표시 변형 후보가 있는 월·연 집합 안인가(없으면 보고서 연 범위, 그것도 없으면 전체)."""
    if periods:
        return period in periods or period[:4] in years
    return rng is None or rng[0] <= period[:4] <= rng[1]


def variant_candidate_blocks(
    result: ManseV2Result,
    birth: BirthInput,
    *,
    scorer: Any,
    base_candidates: Sequence[Any] = (),
    period_start: str | None = None,
    period_end: str | None = None,
    fav_override: dict[str, str] | None = None,
    occupation_status: str | None = None,
    relationship_status: str | None = None,
    max_per_variant: int = MAX_PER_VARIANT,
) -> list[str]:
    """변형별 시기 후보 블록(LLM 입력 줄). 변형이 하나뿐이거나 시간이 있으면 빈 목록."""
    hu = result.hour_unknown
    if hu is None or len(hu.pillar_variants) <= 1:
        return []
    periods, years, rng = _period_scope(base_candidates, period_start, period_end)
    base_idx = next((i for i, v in enumerate(hu.pillar_variants) if v.is_base), 0)
    base_keys = {(str(c.period), str(c.event_key)) for c in base_candidates}
    out: list[str] = []
    for i, v in enumerate(hu.pillar_variants):
        if v.is_base:
            continue
        try:
            vbirth = birth.model_copy(update={
                "birth_time": None, "birth_time_unknown": True,
                "hour_branch_candidates": list(v.hour_branches),
                "hour_branch_hint": None, "birth_time_approx": None,
            })
            vresult = manse_service.calculate(vbirth)
            scored = scorer.score_legacy(
                vresult, levels=_LEVELS, fav_override=fav_override,
                occupation_status=occupation_status, relationship_status=relationship_status,
            )
        except Exception:  # noqa: BLE001 — 한 변형 실패가 본 응답을 막지 않도록
            _logger.warning("variant branching 채점 실패 variant=%s", _letter(i), exc_info=True)
            continue
        finally:
            # 보조 채점이 싱글턴 scorer 의 shadow 상태를 덮지 않도록 비운다(관측 전용 — 본 요청은
            # 주 채점 직후 이미 스냅샷을 확보했다).
            for name in ("take_risk_shadow", "take_relationship_shadow"):
                fn = getattr(scorer, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        pass
        in_scope = [c for c in scored if _in_scope(str(c.period), periods, years, rng)]
        top = sorted(in_scope or scored, key=lambda c: -c.score)[:max_per_variant]
        hours = "".join(v.hour_branches)
        out.append(
            f"[명식 변형 {_letter(i)} 시기 후보 — {v.year_ganji}·{v.month_ganji}·{v.day_ganji}"
            f"({hours}시) 명식으로 따로 채점. 변형 {_letter(base_idx)}(현재 표시) 후보와 비교해 "
            "변형별로 나누어 서술할 것 — 점수·극성은 변형별 엔진 계산값이며 재계산·합산 금지]"
        )
        if not top:
            out.append("이 변형에서는 같은 창 안의 두드러진 시기 후보가 없음.")
        for c in top:
            out.append(
                f"{c.period} {event_ko(c.event_key)} — {tone_for_score(c.score)}"
                f"({polarity_ko(str(c.polarity))}) · 신호 {len(c.signals)}"
            )
        top_keys = {(str(c.period), str(c.event_key)) for c in top}
        only_base = [k for k in base_keys if k not in top_keys][:MAX_DIFF]
        only_var = [k for k in top_keys if k not in base_keys][:MAX_DIFF]
        if only_base or only_var:
            parts = []
            if only_base:
                parts.append(
                    "표시 변형에만: " + ", ".join(f"{p} {event_ko(e)}" for p, e in only_base)
                )
            if only_var:
                parts.append(
                    f"변형 {_letter(i)}에만: "
                    + ", ".join(f"{p} {event_ko(e)}" for p, e in only_var)
                )
            out.append("차이 — " + " / ".join(parts))
    return out


def iter_variant_letters(result: ManseV2Result) -> Iterable[tuple[str, bool]]:
    """(변형 문자, 표시 여부) — 화면·로그 표기용."""
    hu = result.hour_unknown
    if hu is None:
        return []
    return [(_letter(i), v.is_base) for i, v in enumerate(hu.pillar_variants)]
