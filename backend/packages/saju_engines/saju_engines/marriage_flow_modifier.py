"""비식재(比食財) 흐름 결혼 발동 모디파이어 (v2.2, 2026-06-22).

정통 배우자성 경로(여=관성합·남=재성합)가 약/부재인 사주가 **비겁→식상→재성** 생성 흐름을 통해
결혼하는 메커니즘을 모델링한다(영상 자료 — 비식재 부조 결혼). 원국 비식재 구조(그릇) × 그 시점 운의
식재/재생관 보강(발동)을 결합해 marriage_signal·relationship_change 후보를 **보수적으로** 가산한다.

WealthActivationModifier(횡재 발동)와 동일한 구조다 — 그릇은 하드 게이트가 아니라 **배율**이고,
같은 계열 복수 발동은 감쇠한다. 가중치는 단일 사례 가설의 **잠정값**이며 캘리브레이션 전 미보장
(절대원칙 5). 결혼을 단정하지 않는다 — 점수는 내부값이고 단정 금지는 별도 금기룰·프롬프트가 강제.

성별 인지: 여성은 재생관(財生官)으로 관성=배우자가 보강될 때, 남성은 식상생재로 재성=배우자가
도달할 때 완성으로 본다. **기존 후보만 증폭**하며(횡재·복음과 동일) 후보를 새로 만들지 않는다
(2026-06-22 사용자 확정 — 증폭만).
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.event_engine import EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import EventKeyV2
from saju_shared_types.manse_result import ManseV2Result

from .marriage_resource import analyze_marriage_resource

# 원국 비식재 그릇 배율 — 배우자성 약 + 비식재 라인이 가장 의미 크다(라인만 있으면 절반).
_BAND_MULT: dict[str, float] = {"strong": 1.0, "moderate": 0.5, "none": 0.0}
# 발동별 base 가중(잠정 — 캘리브레이션 전). 완성(재생관/식상생재) > 재성 보강 > 식상 보강.
_ACT_WEIGHT: dict[str, float] = {
    "식상 보강": 0.08,
    "재성 보강": 0.12,
    "재생관 완성": 0.16,
    "식상생재 완성": 0.16,
}
# 계열 인지 감쇠 — 발동은 모두 '비식재 흐름' 한 계열이라 대표 1개만 full, 추가는 감쇠(중복 방지).
_DIMINISH_TIERS: tuple[float, ...] = (1.0, 0.45, 0.25)
# 원국 비식재 라인 판정 임계 — 식상 분포(>=10%)와 재성 분포(>=5%)로 식상생재 라인 성립.
_OUTPUT_MIN_PCT = 10.0
_WEALTH_MIN_PCT = 5.0
_TARGET_KEYS = (EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.RELATIONSHIP_CHANGE)


# ── 배우자성 성별 가중(③) — 남=재성·여=관성. 반대 성별 별만으로 뜬 결혼신호 약화 ──
# 구동 십성을 base 조합 reason_code(SINGLE_/SPEC_/TRI_)로 식별한다(브랜칭 직후 적용 — amplifier
# 전). 남성 정관 단독 = 직위·자식(배우자 아님), 여성 재성 단독 = 시댁·물질(직접 배우자 아님)이라
# 약화한다. 잠정값(reviewed:false) — 캘리브레이션 전 미보장.
_OFFICER_DRIVE_TOKENS = ("ZHENGGUAN", "PIANGUAN", "AUTHORITY")
_WEALTH_DRIVE_TOKENS = ("ZHENGCAI", "PIANCAI", "WEALTH")
_GENDER_TARGET_KEYS = (EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.NEW_RELATIONSHIP)
_MALE_OFFICER_ONLY_MULT = 0.6   # 남성 정관 단독 — 배우자성 아님
_FEMALE_WEALTH_ONLY_MULT = 0.7  # 여성 재성 단독 — 시댁·물질(간접)


def apply_marriage_gender_weight(
    candidates: list[EventCandidateV2], gender: str,
) -> list[EventCandidateV2]:
    """구동 십성 × 성별로 결혼/새인연 후보를 재가중한다(배우자성 불일치 약화).

    남=재성·여=관성이 배우자성이다. 반대 성별의 별만으로 생성된 결혼신호(남:정관 단독 /
    여:재성 단독)는 직접 배우자 인연이 아니므로 약화한다. 재성·관성이 함께 있으면(재생관 등)
    배우자 구조가 성립하므로 약화하지 않는다. 브랜칭 직후 적용해 amplifier 전 base를 교정한다.

    Args:
        candidates: 브랜칭 직후 후보(SINGLE_/SPEC_/TRI_ 구동 코드 보유).
        gender: 'male'/'female'/그 외(미상은 무변경).

    Returns:
        성별 가중을 반영한 후보 목록.
    """
    if gender not in ("male", "female"):
        return candidates
    out: list[EventCandidateV2] = []
    for c in candidates:
        if c.event_key not in _GENDER_TARGET_KEYS:
            out.append(c)
            continue
        codes = " ".join(c.reason_codes)
        has_officer = any(t in codes for t in _OFFICER_DRIVE_TOKENS)
        has_wealth = any(t in codes for t in _WEALTH_DRIVE_TOKENS)
        mult = 1.0
        if gender == "male" and has_officer and not has_wealth:
            mult = _MALE_OFFICER_ONLY_MULT
        elif gender == "female" and has_wealth and not has_officer:
            mult = _FEMALE_WEALTH_ONLY_MULT
        if mult < 1.0:
            new_score = max(0, round(c.score * mult))
            out.append(c.model_copy(update={
                "score": new_score,
                "reason_codes": [*c.reason_codes, f"MARRIAGE_GENDER_{gender.upper()}_x{mult}"],
                "contributions": {
                    **c.contributions, "marriage_gender": float(new_score - c.score),
                },
            }))
        else:
            out.append(c)
    return out


@dataclass(frozen=True)
class MarriageFlowNatal:
    """원국 비식재 결혼 그릇(운 미반영, 성별 인지). band가 'none'이면 발동 가산 없음."""

    band: str  # strong(비식재 라인 + 배우자성 약) / moderate(라인만) / none
    gender: str  # female/male/unknown


def analyze_marriage_flow_natal(result: ManseV2Result) -> MarriageFlowNatal:
    """원국 비식재 흐름 결혼 그릇을 판정한다(식상생재 라인 × 배우자성 약).

    비식재 라인 = 식상생재('self' 출처 경향) 또는 식상(>=10%)·재성(>=5%) 분포 동시 존재.
    배우자성 약 = 배우자 별(여=관성/남=재성) 미투출. 둘 다면 strong, 라인만이면 moderate.

    Args:
        result: 만세 결과(force_analysis·pillars·input_summary 필요).

    Returns:
        MarriageFlowNatal — band·gender. force_analysis 부재 시 band='none'.
    """
    if result.force_analysis is None or result.pillars is None:
        return MarriageFlowNatal(band="none", gender="unknown")
    mr = analyze_marriage_resource(result)
    groups = result.force_analysis.ten_gods.groups
    output_pct = float(groups.get("output", 0.0))
    wealth_pct = float(groups.get("wealth", 0.0))
    flow_present = ("self" in mr.wealth_source_leans) or (
        output_pct >= _OUTPUT_MIN_PCT and wealth_pct >= _WEALTH_MIN_PCT
    )
    spouse_weak = not mr.spouse_star_present
    if flow_present and spouse_weak:
        band = "strong"
    elif flow_present:
        band = "moderate"
    else:
        band = "none"
    return MarriageFlowNatal(band=band, gender=mr.gender)


def detect_marriage_flow_activations(present_groups: set[str], gender: str) -> list[str]:
    """그 시점 운 십성군으로 비식재 흐름 발동을 판정한다(성별 인지).

    식상(output)·재성(wealth) 보강과, 완성(여=재성+관성 재생관 / 남=식상+재성 식상생재)을 잡는다.
    present_groups는 시점 십성을 그룹값으로 환원한 집합(관성=event 엔진에선 'authority').

    Args:
        present_groups: 시점 운 십성군 집합({'peer','output','wealth','authority','resource'}).
        gender: 성별(female/male/unknown) — 완성 조건의 배우자성 방향 결정.

    Returns:
        발동 라벨 목록(없으면 빈 목록).
    """
    acts: list[str] = []
    has_output = "output" in present_groups
    has_wealth = "wealth" in present_groups
    has_authority = "authority" in present_groups
    if has_output:
        acts.append("식상 보강")
    if has_wealth:
        acts.append("재성 보강")
    if gender == "female" and has_wealth and has_authority:
        acts.append("재생관 완성")  # 재생관 — 재성이 관성(배우자)을 생
    elif gender != "female" and has_output and has_wealth:
        acts.append("식상생재 완성")  # 식상생재 — 식상이 재성(배우자)을 생
    return acts


def _flow_boost(activations: list[str], mult: float) -> float:
    """발동들을 '비식재 흐름' 한 계열로 보고 대표 강·추가 감쇠 합으로 boost를 산출한다."""
    items = sorted(
        ((_ACT_WEIGHT.get(a, 0.0), a) for a in activations if _ACT_WEIGHT.get(a, 0.0) > 0),
        key=lambda x: -x[0],
    )
    total = 0.0
    for i, (w, _a) in enumerate(items):
        factor = _DIMINISH_TIERS[i] if i < len(_DIMINISH_TIERS) else 0.1
        total += w * factor
    return total * mult


class MarriageFlowModifier:
    """원국 비식재 그릇 × 운 발동 → 결혼/관계 후보 보수 가산(다른 도메인·미발동 시 무영향)."""

    @staticmethod
    def apply(
        candidates: list[EventCandidateV2],
        natal: MarriageFlowNatal,
        activations: list[str],
    ) -> list[EventCandidateV2]:
        """그릇 band가 있고 발동이 있을 때만 결혼·관계 후보를 (1+boost)배 한다(증폭만)."""
        mult = _BAND_MULT.get(natal.band, 0.0)
        if mult <= 0.0 or not activations:
            return candidates
        boost = _flow_boost(activations, mult)
        if boost <= 0.0:
            return candidates
        tag = "MARRIAGEFLOW_" + "+".join(activations)
        diminished = len(activations) > 1  # 같은 계열 복수 발동 → 감쇠 적용 표식
        out: list[EventCandidateV2] = []
        for c in candidates:
            if c.event_key in _TARGET_KEYS:
                reasons = [*c.reason_codes, tag]
                if diminished:
                    reasons.append("MARRIAGEFLOW_FAMILY_DIMINISH")
                new_score = max(0, round(c.score * (1 + boost)))  # 중간 100 클램프 제거
                out.append(c.model_copy(update={
                    "score": new_score,
                    "reason_codes": reasons,
                    "contributions": {
                        **c.contributions, "marriage_flow": float(new_score - c.score),
                    },
                }))
            else:
                out.append(c)
        return out
