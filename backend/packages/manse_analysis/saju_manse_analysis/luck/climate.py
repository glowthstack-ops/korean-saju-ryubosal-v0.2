"""조후(調候) 온도 축 — 월지 계절의 필요 온도와 운 지지의 온도(2026-11-08 데굴님 승인 A/B안).

데굴님: "조후로만 봐도 겨울에 태어나서 가을로 가는 중이라 바닥에서 시작해서 서서히 쌓여갈 수밖에
없어."
억부 용신 점수(`_luck_effect`)는 용·희·기신 역할만 보므로 겨울생의 봄 대운(卯)을 木 기신으로 최저로
찍지만, 조후 축으로는 子丑(한겨울) → 寅卯(봄) → 巳午未(여름)로 **온기가 서서히 쌓이는** 궤적이다.

- 월지 조후 축(`MONTH_CLIMATE_AXIS`)은 조후 용신 사전(`compiled/johu_yongsin_v*.json` 의
  `climate_axis`, 월지별로 일간 무관하게 동일)과 같다 — 테스트가 사전과의 일치를 강제한다(SSOT 는
  사전).
- 필요 온도(`climate_need`): cold → 온기(warm) 1.0 · heat → 서늘함(cool) 1.0 · damp(辰) → 온기 0.5 ·
  dry(戌) → 서늘함 0.5 · neutral(卯申酉) → 축 없음(0).
- 지지 온도(`BRANCH_WARMTH`, −1~+1): 子 −1.0 丑 −0.8 寅 −0.3 卯 0 辰 +0.3 巳 +0.7 午 +1.0 未 +0.8
  申 +0.3 酉 0 戌 −0.3 亥 −0.8. 필요가 cool 이면 부호를 뒤집는다(더울수록 나쁨).
- 천간은 보지 않는다(승인 범위: 대운·세운 **지지**의 온도표).

A안(인생 그래프 조후 흐름선)은 설명용 층이고, B안(`luck_cycles.CLIMATE_LUCK_MODE` blend)은 점수
규칙이라 85사례 재생 적중률로 ON/OFF 를 정한다(기본 off).
"""

from __future__ import annotations

from saju_shared_types.enums import Branch

#: 월지 → 조후 축(조후 용신 사전 `climate_axis` 와 동일, 일간 무관).
MONTH_CLIMATE_AXIS: dict[str, str] = {
    "寅": "cold", "卯": "neutral", "辰": "damp", "巳": "heat", "午": "heat", "未": "heat",
    "申": "neutral", "酉": "neutral", "戌": "dry", "亥": "cold", "子": "cold", "丑": "cold",
}

#: 조후 축 → (필요 온도 방향, 가중). warm=온기가 필요(겨울·습), cool=서늘함이 필요(여름·조).
_AXIS_NEED: dict[str, tuple[str, float]] = {
    "cold": ("warm", 1.0), "heat": ("cool", 1.0), "damp": ("warm", 0.5), "dry": ("cool", 0.5),
    "neutral": ("", 0.0),
}

#: 지지 온도(−1 한겨울 ~ +1 한여름).
BRANCH_WARMTH: dict[str, float] = {
    "子": -1.0, "丑": -0.8, "寅": -0.3, "卯": 0.0, "辰": 0.3, "巳": 0.7,
    "午": 1.0, "未": 0.8, "申": 0.3, "酉": 0.0, "戌": -0.3, "亥": -0.8,
}

NEED_KO: dict[str, str] = {"warm": "온기(火)", "cool": "서늘함(水)"}
AXIS_KO: dict[str, str] = {
    "cold": "한습(겨울)", "heat": "조열(여름)", "damp": "습(辰월)", "dry": "조(戌월)",
    "neutral": "중립",
}


def climate_need(month_branch: Branch | str) -> tuple[str, str, float]:
    """월지 → (조후 축, 필요 온도 방향, 가중). 중립 월이면 ('neutral', '', 0.0)."""
    axis = MONTH_CLIMATE_AXIS.get(str(month_branch), "neutral")
    need, weight = _AXIS_NEED[axis]
    return axis, need, weight


def branch_climate_score(branch: Branch | str, need: str) -> float:
    """운 지지의 조후 점수(−1~+1). need='warm' 이면 온도 그대로, 'cool' 이면 부호 반전, 없으면 0."""
    warmth = BRANCH_WARMTH.get(str(branch), 0.0)
    if need == "warm":
        return warmth
    if need == "cool":
        return -warmth
    return 0.0


def climate_score(month_branch: Branch | str, branch: Branch | str) -> float:
    """월지 필요 온도 × 가중을 적용한 운 지지의 조후 점수(중립 월은 0)."""
    _axis, need, weight = climate_need(month_branch)
    return round(weight * branch_climate_score(branch, need), 3)
