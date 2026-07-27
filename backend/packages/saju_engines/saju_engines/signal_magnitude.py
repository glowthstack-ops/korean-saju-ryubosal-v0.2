"""V2 무부호 강도 파생 (P3 — 2026-07-27 데굴님 확정).

`unsigned_magnitude_v2`는 V2 signed contribution에 쓰는 **유일한** magnitude다.

계약:
  - 방향과 무관한 구조적 보정(관계 고유 강도, 부분 성립 감쇠)은 **보존**한다.
  - 용희기구한 modifier(±0.2/±0.1)와 그로 인해 생긴 clamp는 **제외**한다.
    "모든 clamp 제거"가 아니라 "유불리 modifier 때문에 생긴 clamp만 분리"다.
  - V2 계산은 `unsigned_magnitude_v2 × score_polarity` 하나뿐이다. 층위 가중이나
    구조 보정을 여기서 다시 곱하면 이중 반영이다.

write-time과 read-time fallback이 **같은 순수 함수**를 호출한다. 지역변수를 캡처하고
구형 캐시는 다른 코드로 재계산하면 drift가 되살아난다.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

#: 부분 성립(반합·부분 방합) 감쇠 — 기존 산식과 동일 계수(방향 무관 구조 보정).
PARTIAL_DECAY = 0.6
STRUCTURAL_WEIGHT_VERSION = "relations_base_score_v1"


class MagnitudeResult(BaseModel):
    """무부호 강도 파생 결과 — 값과 산출 경로를 함께 보존한다."""

    unsigned_magnitude_v2: float
    magnitude_formula_id: str  # 'base' | 'base_x_partial_v1' — 계산 공식만(출처 제외)
    components: dict[str, float] = {}  # 진단용(계산 입력 아님)
    structural_weight_version: str = STRUCTURAL_WEIGHT_VERSION


class MagnitudeUnavailable(Exception):
    """원본 입력이 부족해 재현할 수 없을 때 — 임의 추정 대신 실패로 둔다."""


def derive_unsigned_magnitude_v2(
    *, base_weight: float | None, partial: bool | None
) -> MagnitudeResult:
    """관계의 무부호 강도를 파생한다(write-time·read-time 공용).

    Args:
        base_weight: 사전 relations.json의 baseScore(방향 무관 고유 강도).
        partial: 반합·부분 방합 여부.

    Returns:
        무부호 강도와 산출 경로.

    Raises:
        MagnitudeUnavailable: 입력이 없거나 유한하지 않은 경우(구형 캐시 등).
    """
    if base_weight is None or partial is None:
        raise MagnitudeUnavailable("base_weight/partial 미보유 — 재현 불가")
    if not math.isfinite(base_weight) or base_weight < 0:
        raise MagnitudeUnavailable(f"유효하지 않은 base_weight: {base_weight}")

    magnitude = base_weight
    components = {"base_weight": base_weight}
    formula = "base"
    if partial:
        magnitude *= PARTIAL_DECAY
        components["partial_decay"] = PARTIAL_DECAY
        formula = "base_x_partial_v1"

    # 이름이 unsigned인 만큼 계약을 코드로 못박는다.
    magnitude = round(magnitude, 6)
    if not math.isfinite(magnitude) or magnitude < 0:  # pragma: no cover - 방어
        raise MagnitudeUnavailable(f"무부호 계약 위반: {magnitude}")
    return MagnitudeResult(
        unsigned_magnitude_v2=magnitude, magnitude_formula_id=formula,
        components=components
    )


def v2_contribution(unsigned_magnitude_v2: float, score_polarity: int) -> float:
    """V2 기여도 — 이 곱셈 하나가 전부다.

    층위 가중·구조 보정을 여기서 다시 곱하면 이중 반영이므로 인자를 받지 않는다.
    """
    return round(unsigned_magnitude_v2 * score_polarity, 6)
