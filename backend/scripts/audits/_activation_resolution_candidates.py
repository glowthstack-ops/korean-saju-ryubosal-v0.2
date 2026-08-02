"""활성도 해상도 후보 투영 — 감사 전용 (CAL-ACTIVATION-RESOLUTION-01a, 2026-08-02).

**production 타입을 전혀 바꾸지 않는다.** `ActivationLevel`·`RoleActivationResult`·P2-3
매핑·직렬화 모두 그대로 두고, 여기서 별도 타입으로 병렬 투영해 비교만 한다.

후보 A 를 빼면 "등급 자체를 나누는 방식" 과 "기존 등급에 보조 해상도를 붙이는 방식" 의 비교가
불가능해진다. 그렇다고 production enum 을 먼저 확장하면 measurement-only 원칙을 어긴다.
그래서 감사 전용 band 를 둔다.

의존 방향은 한 방향뿐이다 — 감사가 production 타입을 읽되, production 은 이 모듈을 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import Any

from saju_engines.element_operability_grade import OperabilityStatus
from saju_engines.role_activation_projection import ActivationLevel

ACTIVATION_RESOLUTION_CANDIDATES_V1 = "activation-resolution-candidates-v1"

#: 후보 A 식별용 **실험 라벨**이다. 제품 용어가 아니며 사용자 노출 enum 후보도 아니다.
class AuditActivationBand(StrEnum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NONE = "none"
    UNKNOWN = "unknown"


#: 후보 A — 실현도 등급을 밴드로 직접 나눈다.
_BAND_BY_STATUS: dict[str, AuditActivationBand] = {
    OperabilityStatus.FULLY_OPERABLE.value: AuditActivationBand.VERY_HIGH,
    OperabilityStatus.OPERABLE.value: AuditActivationBand.HIGH,
    OperabilityStatus.PARTIALLY_OPERABLE.value: AuditActivationBand.MODERATE,
    OperabilityStatus.WEAKENED.value: AuditActivationBand.LOW,
    OperabilityStatus.SUPPRESSED.value: AuditActivationBand.LOW,
    OperabilityStatus.UNKNOWN.value: AuditActivationBand.UNKNOWN,
}

#: 기존 P2-3 매핑(변경하지 않는다) — 후보 B·C 의 band 는 이 값을 그대로 쓴다.
_LEVEL_BY_STATUS: dict[str, str] = {
    "fully_operable": ActivationLevel.HIGH.value,
    "operable": ActivationLevel.HIGH.value,
    "partially_operable": ActivationLevel.MODERATE.value,
    "weakened": ActivationLevel.LOW.value,
    "suppressed": ActivationLevel.LOW.value,
    "unknown": ActivationLevel.UNKNOWN.value,
}

#: 역할 → 활성화되는 축. 비대상 축은 계속 NONE 이다.
_AXES_BY_ROLE: dict[str, tuple[str, ...]] = {
    "용신": ("favorable", "mitigation"), "희신": ("favorable", "mitigation"),
    "기신": ("adverse",), "구신": ("adverse",), "한신": ("neutral",),
}


@dataclass(frozen=True)
class AuditAxisProjection:
    """세 후보를 같은 구조로 비교한다 — 형태가 다르면 차이가 정책 탓인지 표현 탓인지 모른다."""

    baseline_level: str
    candidate_band: str
    resolution_value: float | None
    qualifier: str | None


def project_candidate(
    candidate: str, *, status: str, operability_anchor: float | None,
) -> AuditAxisProjection:
    """후보별 투영. **새 수치를 만들지 않는다** — B 는 P2-2 의 anchor 를 그대로 소비한다."""
    baseline = _LEVEL_BY_STATUS[status]
    if candidate == "A":
        return AuditAxisProjection(baseline, _BAND_BY_STATUS[status].value, None, None)
    if candidate == "B":
        return AuditAxisProjection(baseline, baseline, operability_anchor, None)
    # C — 첫 측정에서는 HIGH 구간에만 태그를 붙인다. 다른 등급까지 넓히면 비교 범위가
    # 불필요하게 커진다.
    qualifier = None
    if baseline == ActivationLevel.HIGH.value:
        qualifier = "FULL" if status == "fully_operable" else "STANDARD"
    return AuditAxisProjection(baseline, baseline, None, qualifier)


def _key(p: AuditAxisProjection) -> tuple[str, float | None, str | None]:
    return (p.candidate_band, p.resolution_value, p.qualifier)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """후보별 구분력·표현 위험·정렬 가능성. **실제 사건 점수 공식은 만들지 않는다.**"""
    out: dict[str, Any] = {"target_count": len(rows)}
    migrated = [r for r in rows if "NON_MAIN_ROOT_CAP" in r["matched_rule_id"]]
    out["root_depth_migrated"] = len(migrated)

    for cand in ("A", "B", "C"):
        proj = {
            id(r): project_candidate(
                cand, status=r["operability_status"],
                operability_anchor=r.get("baseline_anchor"))
            for r in rows
        }
        level_changed = sum(
            1 for r in rows
            if proj[id(r)].candidate_band != _LEVEL_BY_STATUS[r["operability_status"]]
        )
        # FULLY vs OPERABLE — 같은 역할·같은 축에서 두 등급이 만나는 쌍만 본다.
        pairs = [
            (a, b) for a, b in combinations(rows, 2)
            if a["canonical_role"] == b["canonical_role"]
            and {a["operability_status"], b["operability_status"]}
            == {"fully_operable", "operable"}
        ]
        orderable = sum(1 for a, b in pairs if _key(proj[id(a)]) != _key(proj[id(b)]))
        very_high: dict[str, int] = {}
        if cand == "A":
            for r in rows:
                if proj[id(r)].candidate_band != AuditActivationBand.VERY_HIGH.value:
                    continue
                for axis in _AXES_BY_ROLE.get(r["canonical_role"], ()):
                    very_high[axis] = very_high.get(axis, 0) + 1
        out[f"candidate_{cand.lower()}"] = {
            "activation_level_changed": level_changed,
            "fully_vs_operable_pairs": len(pairs),
            "newly_orderable_pairs": orderable,
            "remaining_tied_pairs": len(pairs) - orderable,
            "migrated_distinguished": sum(
                1 for r in migrated
                if _key(proj[id(r)]) != _key(project_candidate(
                    cand, status="fully_operable",
                    operability_anchor=0.90))
            ),
            "very_high_by_axis": dict(sorted(very_high.items())),
            "representationally_distinct": orderable > 0,
            # C 는 태그만으로 순서가 생기지 않는다 — 소비 정책이 따로 필요하다.
            "ordering_policy_required": cand == "C",
        }
    return out
