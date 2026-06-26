"""풍수 형국·방위 역할 — 좌향 사신사 sector 계산(docs/12 §14, P5-1 스캐폴딩).

본 모듈은 좌향(facing_bearing) → 전후좌우 sector(현무/주작/청룡/백호) 변환만 한다(무보정·결정론).
형국 채점(back_mountain_score 등)·도로 페널티·팔택 가중은 reviewed:false라 전문가 감수 후
P5-3에서 활성화한다(docs/12 §14-10·§14-11·절대원칙 5) — 여기서는 sector 기하만 확정한다.

방위 라벨은 [region_direction.py]의 한국 8방위 컨벤션과 동일(북/북동/동/남동/남/남서/서/북서)하게
맞춰, 좌향-상대 sector와 명리형 방위 오행이 같은 축에서 결합되도록 한다.
"""

from __future__ import annotations

from saju_shared_types.region_element import (
    DirectionalSectorProfile,
    FengshuiFormProfile,
    RegionDirectionalElementSummary,
)

# 0°=북, 시계방향 45° 간격(region_direction._COMPASS_8과 동일 순서).
_COMPASS_8 = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
# 한국 8방위 라벨 → directional summary direction_code(N/NE/E/SE/S/SW/W/NW).
_LABEL_TO_CODE = {
    "북": "N", "북동": "NE", "동": "E", "남동": "SE",
    "남": "S", "남서": "SW", "서": "W", "북서": "NW",
}
# 첫 릴리즈 cap(§14-12, 검수 후 확장). 좌향 없음 ±5 / 좌향 있음 ±10(상한은 호출부 결정).
_FORM_BONUS_CAP_OPEN = 5
_NEAR_FAR_M = 8000.0  # 이 거리 밖이면 '먼 feature'(isolation 판정).


def compass_from_bearing(bearing: float) -> str:
    """방위각(0°=북, 시계방향) → 한국 8방위 라벨."""
    idx = int(((bearing % 360.0) + 22.5) // 45.0) % 8
    return _COMPASS_8[idx]


def sasinsa_sectors(facing_bearing: float) -> DirectionalSectorProfile:
    """좌향(바라보는 방위) → 전후좌우 sector(모드 B, docs/12 §14-2·§14-3).

    front=주작(바라보는 쪽)·back=현무(뒤)·left=청룡(좌)·right=백호(우). facing 상대로 계산하므로
    남향이면 현무=북, 동향이면 현무=서 — '북쪽 산이 항상 현무'가 되는 오류를 피한다.

    Args:
        facing_bearing: 바라보는 방위각(0°=북, 시계방향). 0~360 밖이면 modulo 보정.
    """
    f = facing_bearing % 360.0
    return DirectionalSectorProfile(
        facing_bearing=f,
        front_sector=compass_from_bearing(f),
        back_sector=compass_from_bearing(f + 180.0),
        left_sector=compass_from_bearing(f - 90.0),
        right_sector=compass_from_bearing(f + 90.0),
    )


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _by_code(
    rows: list[RegionDirectionalElementSummary],
) -> dict[str, RegionDirectionalElementSummary]:
    return {r.direction_code: r for r in rows}


def _avg_conf(rows: list[RegionDirectionalElementSummary]) -> float:
    confs = [r.confidence for r in rows if r.confidence > 0]
    return sum(confs) / len(confs) if confs else 0.5


def derive_open_signals(rows: list[RegionDirectionalElementSummary]) -> dict[str, float]:
    """8방위 directional_terrain → 좌향-없음 형국 신호(0~1, docs/12 §14-12·§14-4 좌향 없음).

    지역 단위라 사신사를 강판정하지 않고 '산수분포·수계접근·지형균형'만 본다(§14-11 금지 4).
    mountain/forest/water는 방위 최대 신호, balance는 2개 이상 공존, overwater/isolation은 페널티.
    """
    if not rows:
        return {k: 0.0 for k in (
            "mountain_support", "water_access", "forest_support",
            "terrain_balance", "overwater_penalty", "isolation_penalty")}
    mountain = _clamp01(max(r.earth_score for r in rows))
    forest = _clamp01(max(r.wood_score for r in rows))
    water = _clamp01(max(r.water_score for r in rows))
    present = sum(1 for s in (mountain, forest, water) if s >= 0.30)
    balance = 1.0 if present >= 2 else (0.3 if present == 1 else 0.0)
    land = max(mountain, forest)
    overwater = _clamp01(water - land - 0.20) if water > 0.45 else 0.0
    # 유의미 feature가 모두 멀거나(>8km) 신호가 거의 없으면 고립(약감점).
    def _near(attr: str) -> bool:
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return any(v <= _NEAR_FAR_M for v in vals)
    has_near = _near("nearest_mountain_m") or _near("nearest_river_m") or _near("nearest_water_m")
    isolation = 1.0 if (not has_near and max(mountain, forest, water) < 0.15) else 0.0
    return {
        "mountain_support": mountain, "water_access": water, "forest_support": forest,
        "terrain_balance": balance, "overwater_penalty": overwater,
        "isolation_penalty": isolation,
    }


def compute_form_quality_open(
    rows: list[RegionDirectionalElementSummary], region_code: str
) -> FengshuiFormProfile:
    """좌향 없음 형국 품질(§14-12 산식). region_element_vector와 분리된 B 계층 점수."""
    s = derive_open_signals(rows)
    raw = (0.25 * s["mountain_support"] + 0.20 * s["water_access"]
           + 0.20 * s["forest_support"] + 0.15 * s["terrain_balance"]
           - 0.20 * s["overwater_penalty"] - 0.15 * s["isolation_penalty"])
    conf = _avg_conf(rows)
    pos = [k for k in ("mountain_support", "water_access", "forest_support") if s[k] >= 0.30]
    neg = [k for k in ("overwater_penalty", "isolation_penalty") if s[k] > 0.0]
    return FengshuiFormProfile(
        region_code=region_code,
        back_mountain_score=s["mountain_support"], front_water_score=s["water_access"],
        open_front_score=s["terrain_balance"],
        water_escape_penalty=s["overwater_penalty"], isolated_flat_penalty=s["isolation_penalty"],
        form_quality_score=max(-1.0, min(1.0, raw)) * conf,
        confidence=conf, available=bool(rows),
        evidence=[f"+{k}" for k in pos] + [f"-{k}" for k in neg],
    )


def compute_form_quality_facing(
    rows: list[RegionDirectionalElementSummary], region_code: str, facing_bearing: float
) -> FengshuiFormProfile:
    """좌향 있음 사신사 형국(§14-12 산식). facing_bearing 입력 시만 전후좌우 판정.

    road_rush는 도로 feature(transport OFF 기본)라 0 — P5-3 transport 활성 시 결합. front_blocked는
    앞산 과근접(전방 土 강 + 근접) 추정.
    """
    sec = sasinsa_sectors(facing_bearing)
    by = _by_code(rows)

    def _row(label: str) -> RegionDirectionalElementSummary | None:
        return by.get(_LABEL_TO_CODE[label])
    back = _row(sec.back_sector)
    front = _row(sec.front_sector)
    left = _row(sec.left_sector)
    right = _row(sec.right_sector)
    back_m = _clamp01(back.earth_score) if back else 0.0
    front_w = _clamp01(front.water_score) if front else 0.0
    left_d = _clamp01((left.earth_score + left.wood_score) / 2) if left else 0.0
    right_e = _clamp01(right.earth_score) if right else 0.0
    tiger_balance = _clamp01(1.0 - abs(right_e - left_d))  # 백호가 청룡보다 과하지 않게
    front_blocked = 1.0 if (front and front.earth_score > 0.5
                            and (front.nearest_mountain_m or 9e9) < 1500) else 0.0
    overwater = _clamp01(front_w - max(back_m, left_d) - 0.2) if front_w > 0.5 else 0.0
    raw = (0.30 * back_m + 0.20 * front_w + 0.15 * left_d + 0.10 * tiger_balance
           - 0.20 * front_blocked - 0.20 * 0.0 - 0.15 * overwater)  # road_rush=0(transport OFF)
    conf = _avg_conf(rows)
    return FengshuiFormProfile(
        region_code=region_code,
        back_mountain_score=back_m, front_water_score=front_w,
        left_dragon_score=left_d, right_tiger_score=right_e,
        excessive_pressure_penalty=front_blocked, water_escape_penalty=overwater,
        form_quality_score=max(-1.0, min(1.0, raw)) * conf,
        confidence=conf, available=bool(rows),
        evidence=[f"현무 {sec.back_sector}", f"주작 {sec.front_sector}",
                  f"청룡 {sec.left_sector}", f"백호 {sec.right_sector}"],
    )


def form_quality_bonus(profile: FengshuiFormProfile, cap: int = _FORM_BONUS_CAP_OPEN) -> int:
    """form_quality_score(이미 ×confidence) → 추천 점수 보정(±cap, §14-12). base를 뒤집지 못함."""
    return int(round(max(-cap, min(cap, profile.form_quality_score * 8.0))))
