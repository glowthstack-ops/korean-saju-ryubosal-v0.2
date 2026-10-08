"""종격(從格) 공통 판정기 — 격국·용신이 같은 기준을 쓴다 (2026-10-08 데굴님 결정).

배경: 격국은 `root_score<8`(인성 통근 포함)만 보고, 용신은 root 또는 비겁·인성 세력비로 따로 판정해
같은 명식에서 결과가 갈렸다(FOLLOW_DETECTOR_UNIFICATION_C1C). 두 경로를 영구 병존시키지 않고 **통근·
인비 세력·진종/가종**을 한 기준으로 정리한다.

공통 기준(엔진 채택 규칙 — 고전 "日主孤弱無氣，天地人三元，絕無一毫生扶之意，財官等強甚，乃為真從也"
(滴天髓 從化論)를 수치화한 것이며 고전의 확정 수치가 아니다):
  A 전제: 신강약 점수 ≤ FOLLOW_MAX_SCORE(34)
  B 비겁 무근: 비겁 뿌리(본기·동기 통근, 인성 제외) < PEER_ROOT_MAX(8). 투간 비겁은 뿌리가 없으면
    허부(虛浮)라 조력으로 치지 않는다(천간 비겁 무근 不以幫身論) — 세력비 조건을 두지 않는다.
  C 압도 세력: 식·재·관 중 최대 세력비 ≥ 0.40(진종) / ≥ 0.33(가종)
  D 인성 의지처: 인성 세력비 < 0.12(진종) / < 0.28(가종) — "中有所助者，便假"
  → real(진종) = A∧B∧C(0.40)∧D(0.12) · pseudo(가종) = A∧B∧C(0.33)∧D(0.28) · 아니면 None.
종격 명칭은 세력(groups) 최대 그룹으로 통일한다(격국의 십성 개수 기준 폐기).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.analysis import ForceAnalysis

from .strength_score import FOLLOW_MAX_SCORE

PEER_ROOT_MAX: float = 8.0      # CALIBRATE — 옛 root_score<8 임계를 비겁 뿌리에만 적용
DOM_RATIO_REAL: float = 0.40
DOM_RATIO_PSEUDO: float = 0.33
RESOURCE_RATIO_REAL: float = 0.12
RESOURCE_RATIO_PSEUDO: float = 0.28
_FOLLOW_NAME = {"wealth": "종재격", "officer": "종살격", "output": "종아격"}
_FOLLOW_LABEL = {
    "wealth": "종재격(從財格)", "officer": "종살격(從殺格)", "output": "종아격(從兒格)",
}


@dataclass
class FollowCheck:
    """종격 공통 판정 1건."""

    kind: str                 # 'real' | 'pseudo'
    group: str                # output | wealth | officer
    name: str                 # 종아격/종재격/종살격
    label: str                # 한자 병기 라벨
    confidence: float
    score: float
    peer_root: float
    resource_root: float
    peer_ratio: float
    resource_ratio: float
    dom_ratio: float
    reasons: list[str] = field(default_factory=list)


def _ratios(force: ForceAnalysis) -> tuple[float, float, str, float]:
    tg = force.ten_gods.groups
    total = sum(tg.values()) or 1.0
    pressure = {k: tg.get(k, 0.0) for k in ("output", "wealth", "officer")}
    dom = max(pressure, key=lambda k: pressure[k])
    return (tg.get("peer", 0.0) / total, tg.get("resource", 0.0) / total,
            dom, pressure[dom] / total)


def detect_follow(force: ForceAnalysis) -> FollowCheck | None:
    """공통 종격 판정. 격국(special_signal)·용신(detect_special_cases)이 함께 쓴다."""
    score = float(force.strength.score)
    comps = force.strength.components
    peer_root = float(comps.get("peer_root_score", comps.get("root_score", 0.0)))
    resource_root = float(comps.get("resource_root_score", 0.0))
    peer_ratio, resource_ratio, dom, dom_ratio = _ratios(force)
    reasons: list[str] = []
    if score > FOLLOW_MAX_SCORE:
        return None
    if peer_root >= PEER_ROOT_MAX:
        return None
    reasons.append(
        f"점수 {score:.1f}≤{FOLLOW_MAX_SCORE:.0f} · 비겁 뿌리 {peer_root:.1f}<{PEER_ROOT_MAX:.0f}"
        + (f" · 투간 비겁 {peer_ratio:.2f}은 무근(허부)이라 조력 아님" if peer_ratio > 0 else "")
    )
    kind: str | None = None
    if dom_ratio >= DOM_RATIO_REAL and resource_ratio < RESOURCE_RATIO_REAL:
        kind = "real"
        reasons.append(
            f"{_FOLLOW_NAME[dom]} 세력 {dom_ratio:.2f}≥{DOM_RATIO_REAL} · 인성 {resource_ratio:.2f}"
            f"<{RESOURCE_RATIO_REAL} → 진종(眞從)"
        )
    elif dom_ratio >= DOM_RATIO_PSEUDO and resource_ratio < RESOURCE_RATIO_PSEUDO:
        kind = "pseudo"
        reasons.append(
            f"{_FOLLOW_NAME[dom]} 세력 {dom_ratio:.2f}≥{DOM_RATIO_PSEUDO} · 인성 "
            f"{resource_ratio:.2f}<{RESOURCE_RATIO_PSEUDO}(의지처 잔존) → 가종(假從)"
        )
    if kind is None:
        return None
    return FollowCheck(
        kind=kind, group=dom, name=_FOLLOW_NAME[dom], label=_FOLLOW_LABEL[dom],
        confidence=0.85 if kind == "real" else 0.5, score=score,
        peer_root=round(peer_root, 2), resource_root=round(resource_root, 2),
        peer_ratio=round(peer_ratio, 3), resource_ratio=round(resource_ratio, 3),
        dom_ratio=round(dom_ratio, 3), reasons=reasons,
    )
