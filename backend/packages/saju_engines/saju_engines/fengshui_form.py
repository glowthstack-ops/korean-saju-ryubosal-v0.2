"""풍수 형국·방위 역할 — 좌향 사신사 sector 계산(docs/12 §14, P5-1 스캐폴딩).

본 모듈은 좌향(facing_bearing) → 전후좌우 sector(현무/주작/청룡/백호) 변환만 한다(무보정·결정론).
형국 채점(back_mountain_score 등)·도로 페널티·팔택 가중은 reviewed:false라 전문가 감수 후
P5-3에서 활성화한다(docs/12 §14-10·§14-11·절대원칙 5) — 여기서는 sector 기하만 확정한다.

방위 라벨은 [region_direction.py]의 한국 8방위 컨벤션과 동일(북/북동/동/남동/남/남서/서/북서)하게
맞춰, 좌향-상대 sector와 명리형 방위 오행이 같은 축에서 결합되도록 한다.
"""

from __future__ import annotations

from saju_shared_types.region_element import DirectionalSectorProfile

# 0°=북, 시계방향 45° 간격(region_direction._COMPASS_8과 동일 순서).
_COMPASS_8 = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]


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
