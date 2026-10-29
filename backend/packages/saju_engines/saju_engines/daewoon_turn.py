"""교운 방향 조언 — 외부 강의 「길흉은 혼자 오지 않는다」 번역층(2026-10-29 데굴님 결정).

대조 문서: doc/v2_2/EXTERNAL_TEXT_GAP_DAEWOON_TURN.md.

- 방향: 앞 대운 역할 좋음(강한·부분 용신운) → 다음 나쁨(강한·부분 기신운) = 과열·무리한 확장 경계,
  나쁨 → 좋음 = 마지막 고비는 길지 않으니 준비. 혼합·평운·트리거운은 방향 판정에서 뺀다(결정 3).
- 범위: 엔진 교운 가중(`event_scoring.daewoon_transition_weight`, 교운일 기준 라플라스형
  스케일 365일)으로 가중 ≥ e^-1(앞뒤 1년) = 교운기 핵심, ≥ e^-2(앞뒤 2년) = 교운기 여파
  (결정 2: 엔진 기준).
- 교운일은 엔진 점수와 같은 출처(만세력 trace 의 정확 교운일, 없으면 대운 시작 근사일).

서술 전용 — 점수·판정 불변. 문구는 사전 `interpretations/daewoon_turn_text.json` 에서 고르기만 한다.
"""

from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import daewoon_transition_weight

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
GOOD_CODES = frozenset({"pure_yongsin_luck", "partial_yongsin"})
BAD_CODES = frozenset({"pure_gisin_luck", "partial_gisin"})
CORE_WEIGHT = math.exp(-1.0)  # 앞뒤 1년(스케일 365일)
EXTENDED_WEIGHT = math.exp(-2.0)  # 앞뒤 2년
_MAX_GAP_DAYS = 400  # 근사 시작일 ↔ 정확 교운일 매칭 허용(context_reducer 와 같은 값)


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    path = dictionaries_dir / "interpretations" / "daewoon_turn_text.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["id"]: it["text"] for it in data["items"]}


def _jiao_date(result: ManseV2Result, approx: date) -> date:
    """대운 시작 근사일에 가장 가까운 정확 교운일(없거나 멀면 근사일)."""
    lc = result.luck_cycles
    exact: list[date] = []
    for x in (lc.trace.get("exact_jiao_un_dates", []) if lc is not None and lc.trace else []):
        try:
            exact.append(date.fromisoformat(x) if isinstance(x, str) else x)
        except (ValueError, TypeError):
            continue
    if not exact:
        return approx
    nearest = min(exact, key=lambda d: abs((d - approx).days))
    return nearest if abs((nearest - approx).days) <= _MAX_GAP_DAYS else approx


def daewoon_turn_lines(result: ManseV2Result, start_year: int, end_year: int) -> list[str]:
    """[start_year, end_year] 창이 방향이 분명한 교운의 교운기(앞뒤 2년)에 걸리면 1블록.

    Args:
        result: 대운표가 있는 만세 결과.
        start_year, end_year: 질문·페이지 창(연, 양끝 포함).

    Returns:
        머리말 + 교운마다 1줄(없으면 빈 목록).
    """
    lc = result.luck_cycles
    if lc is None or len(lc.daewoon_table) < 2:
        return []
    t = _texts()
    lo, hi = date(start_year, 1, 1), date(end_year, 12, 31)
    lines: list[str] = []
    table = lc.daewoon_table
    for prev, nxt in zip(table, table[1:], strict=False):
        if prev.luck_label_code in GOOD_CODES and nxt.luck_label_code in BAD_CODES:
            key = "good_to_bad"
        elif prev.luck_label_code in BAD_CODES and nxt.luck_label_code in GOOD_CODES:
            key = "bad_to_good"
        else:
            continue
        jiao = _jiao_date(result, nxt.approx_start_date)
        nearest = min(max(jiao, lo), hi)  # 창 안이면 교운일 자체, 밖이면 가장 가까운 창 끝
        weight = daewoon_transition_weight(nearest, [jiao])
        if weight >= CORE_WEIGHT:
            span = t["core_label"]
        elif weight >= EXTENDED_WEIGHT:
            span = t["extended_label"]
        else:
            continue
        lines.append(
            f"- {jiao.year}년 무렵 교운({prev.ganji} {prev.luck_label} → {nxt.ganji} "
            f"{nxt.luck_label}) [{span}]: {t[key]}"
        )
    if not lines:
        return []
    return [
        "[교운 방향 — 맞는 흐름↔맞지 않는 흐름의 경계(엔진 대운 역할·교운 가중), 서술 전용 — "
        "사건을 단정하지 말 것]",
        *lines,
    ]
