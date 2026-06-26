"""사신사 좌향 sector 회귀(docs/12 §14-2·§14-3, P5-1 스캐폴딩).

좌향이 바뀌면 현무(back)도 바뀌어야 한다 — '북산=항상 현무' 오류 방지의 핵심. 채점은 감수 대기라
여기선 sector 기하만 고정한다.
"""

from __future__ import annotations

import pytest

from saju_engines.fengshui_form import compass_from_bearing, sasinsa_sectors


@pytest.mark.parametrize(
    ("bearing", "label"),
    [(0, "북"), (45, "북동"), (90, "동"), (180, "남"), (270, "서"), (359, "북")],
)
def test_compass_from_bearing(bearing: float, label: str) -> None:
    assert compass_from_bearing(bearing) == label


def test_sasinsa_facing_relative() -> None:
    """좌향별 전후좌우 — 남향이면 현무=북, 동향이면 현무=서(좌향 상대)."""
    s = sasinsa_sectors(180)  # 남향
    assert (s.front_sector, s.back_sector, s.left_sector, s.right_sector) == (
        "남", "북", "동", "서")  # 주작 남 / 현무 북 / 청룡 동 / 백호 서
    e = sasinsa_sectors(90)  # 동향
    assert e.back_sector == "서"  # 동향이면 현무=서(북산 고정 아님)
    assert (e.front_sector, e.left_sector, e.right_sector) == ("동", "북", "남")
    n = sasinsa_sectors(0)  # 북향
    assert (n.back_sector, n.left_sector, n.right_sector) == ("남", "서", "동")


def test_facing_bearing_modulo() -> None:
    assert sasinsa_sectors(540).facing_bearing == 180.0  # 360 밖 보정
