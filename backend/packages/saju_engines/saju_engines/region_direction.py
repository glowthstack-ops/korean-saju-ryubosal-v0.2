"""이사 이동 '방위' 분석 — 현재지→목적지 8방위 + 명리 용신 방위 적합(비-택일 이사 질문용).

지역 근사 중심좌표(dictionaries/region_coords.json)로 이동 방향(8방위)을 구하고, **명리형 간방
혼합 모델**로 그 방향의 오행이 내 용신/희신/기신과 맞는지 본다. 사정(동木·남火·서金·북水)은 단일
오행, 간방(북동·남동·남서·북서)은 인접 두 사정의 혼합 + 土 전환 보정(45:45:10)으로 본다 —
예: 남동 = 木·火 전환(데굴님 확정 2026-06-25). 풍수 팔괘(巽=木 등 단일 배정)는 좌향·공간 배치용
별개 체계이며, 개인 사주 방향 적합엔 혼합 모델을 기본값으로 쓴다.

좌표·방위는 명리 표준 아님(검수 전 초안) — '참고'로만, 단정 금지. 미등재 지역은 산출 생략(graceful).
region_fit(지역 오행×용신)과 별개 축이다: 목적지 오행이 용신이어도 가는 '방향'은 부담일 수 있다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# 명리형 방위 오행 가중 — 사정=단일, 간방=인접 사정 혼합(45:45)+土 전환(10).
_DIRECTION_ELEMENTS: dict[str, dict[str, float]] = {
    "동": {"木": 1.0},
    "남동": {"木": 0.45, "火": 0.45, "土": 0.10},
    "남": {"火": 1.0},
    "남서": {"火": 0.45, "金": 0.45, "土": 0.10},
    "서": {"金": 1.0},
    "북서": {"金": 0.45, "水": 0.45, "土": 0.10},
    "북": {"水": 1.0},
    "북동": {"水": 0.45, "木": 0.45, "土": 0.10},
}
# 용희기구한 역할 점수(방위 적합 가중합용).
_ROLE_SCORE: dict[str, float] = {
    "용신": 2.0, "희신": 1.2, "한신": 0.0, "기신": -2.0, "구신": -1.2,
}
# 적합 밴드 — (하한 임계, 라벨) 내림차순. score>=임계면 그 라벨. '혼합' 뉘앙스는 근거 문구가
# 담당(간방 전환 방위) — 라벨은 사정/간방 공통으로 중립 표기.
_FIT_BANDS: list[tuple[float, str]] = [
    (1.2, "매우 유리"),
    (0.4, "유리"),
    (-0.4, "중립"),
    (-1.2, "다소 주의"),
]
# 방위 라벨(0°=북, 시계방향 45° 섹터). atan2 결과 정규화에 사용.
_COMPASS_8 = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]


class RegionDirection:
    """지역 좌표 → 이동 방위 + 용신 방위 길흉(순수·결정론)."""

    def __init__(self, dicts_dir: Path) -> None:
        raw = json.loads((dicts_dir / "region_coords.json").read_text("utf-8"))
        self._coords: dict[str, tuple[float, float]] = {
            it["region"]: (float(it["lat"]), float(it["lon"])) for it in raw["items"]
        }

    def coords(self, phrase: str) -> tuple[float, float] | None:
        """지명 구 → 좌표. 완전일치 → 접미일치 → 토큰별 접미일치(세부 동구는 시 단위로 흡수)."""
        if phrase in self._coords:
            return self._coords[phrase]
        # 접미 일치(유일할 때만 — 모호하면 None, 추측 금지).
        suffix = [k for k in self._coords if k.endswith(" " + phrase)]
        if len(suffix) == 1:
            return self._coords[suffix[0]]
        # 토큰별(시/군/구 단위) 접미 일치 — 세부 동구를 시 단위로 흡수.
        for token in phrase.split():
            hit = [k for k in self._coords if k.endswith(" " + token) or k == token]
            if len(hit) == 1:
                return self._coords[hit[0]]
        return None

    def move_direction(self, from_region: str, to_region: str) -> str | None:
        """현재지→목적지 8방위 라벨(둘 다 좌표 있을 때만; 동일/근접<~3km면 None)."""
        a = self.coords(from_region)
        b = self.coords(to_region)
        if a is None or b is None:
            return None
        return _bearing_to_compass(a, b)

    def direction_fit(
        self, move_dir: str, favorability: dict[str, str]
    ) -> tuple[str, str, str]:
        """이동 방위 오행(혼합) × 용희기구한 가중합 → (오행·역할 표기, 적합 라벨, 근거 문구).

        간방은 두 오행이 섞이므로 가중합(Σ 비중×역할점수)으로 본다 — 한쪽이 기신이어도 다른쪽이
        용·희신이면 '혼합'으로 완화된다. score≥1.2 매우유리 / 0.4 유리 / −0.4 혼합·중립 /
        −1.2 혼합·주의 / 그 이하 주의.

        Args:
            move_dir: 8방위 라벨(move_direction 산출).
            favorability: {오행 한자: 역할} (favorability_map).
        """
        weights = _DIRECTION_ELEMENTS.get(move_dir, {})
        if not weights:
            return "-", "중립", "이동 방위의 오행 정보가 없어 길흉을 판단하지 않음"
        score = 0.0
        parts: list[str] = []
        for el, w in weights.items():
            role = favorability.get(el, "한신")
            score += w * _ROLE_SCORE.get(role, 0.0)
            parts.append(f"{el}({role})")
        label = _fit_band(score)
        el_desc = "·".join(parts)
        # 근거 — 섞인 역할 구성 + 부담(기·구신) 동반 여부를 짚는다.
        has_bad = any(favorability.get(el) in ("기신", "구신") for el in weights)
        has_good = any(favorability.get(el) in ("용신", "희신") for el in weights)
        if len(weights) == 1:
            reason = f"이동 방위가 {parts[0]} 방위 — {label}"
        elif has_bad and has_good:
            reason = "길·흉 오행이 섞인 전환 방위 — 도움과 부담이 함께 깔림"
        elif has_good:
            reason = "용·희신 기운이 우세한 전환 방위 — 대체로 도움이 되는 방향"
        elif has_bad:
            reason = "기·구신 기운이 우세한 전환 방위 — 부담이 실리기 쉬운 방향"
        else:
            reason = "길흉 영향이 뚜렷하지 않은 방위"
        return el_desc, label, reason


def _fit_band(score: float) -> str:
    """방위 적합 가중합 점수 → 한글 라벨(_FIT_BANDS 내림차순)."""
    for threshold, label in _FIT_BANDS:
        if score >= threshold:
            return label
    return "주의"


def _bearing_to_compass(a: tuple[float, float], b: tuple[float, float]) -> str:
    """좌표 a→b 의 8방위 라벨(0°=북, 시계방향). 경도는 평균 위도 cos로 보정."""
    lat1, lon1 = a
    lat2, lon2 = b
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    east = (lon2 - lon1) * math.cos(mean_lat)  # 동(+)/서(-)
    north = lat2 - lat1  # 북(+)/남(-)
    bearing = (math.degrees(math.atan2(east, north)) + 360.0) % 360.0
    idx = int((bearing + 22.5) // 45.0) % 8
    return _COMPASS_8[idx]
