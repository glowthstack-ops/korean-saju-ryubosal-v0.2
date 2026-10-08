"""삼재 작용 품질(복/평/악) 평가기 — docs/18 §4-2 (2026-09-20 데굴님 승인).

삼재 stage(들/눌/날)는 12신살 표가 결정하고(context), 여기서는 **그 삼재 세운이 원국·대운과
실제로 어떻게 작용하는지**를 기존 엔진 산출값만 합성해 quality(복/평/악)·강도·근거·도메인·
겹삼재로 판정한다. 새 명리 규칙은 없다 — 가중치·임계는 사전 `samjae_quality` 절의 서비스
캘리브레이션 상수다.

합성 신호(전부 기존 값):
- 세운 극성 `LuckPillar.luck_score`(충·공망·합 변환·합거 완화·희용신 합반이 이미 반영됨 —
  재감점 금지)
- 대운 극성 `DaewoonItem.luck_score`
- 충의 성격 `branch_effect.branch_label` 주석("원국 기신 충거(정리)" / "원국 용신 기반 손상")
- 십성 균형: 세운 천간·지지 십성군이 원국 부족군(<9%)이면 보완, 과다군(≥35%)이면 강화
  (E8 임계 재사용)
- 사건 방향: 그 해 후보의 (유리 점수합 − 불리 점수합)/전체합 — 후보가 주어진 경로에서만
- 대운·세운 동조: 같은 부호로 함께 기울면 보너스/페널티

불변식: 사건 점수·위험 엔진·luck_score·라벨 불변(서술 전용). `event_signal_included`는 내부
플래그이며 프롬프트·화면 문구에 쓰지 않는다.
"""

from __future__ import annotations

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.enums import Branch
from saju_shared_types.event_engine import TEN_GOD_GROUP, TEN_GOD_KO_TO_KEY
from saju_shared_types.event_taxonomy_v2 import result_direction
from saju_shared_types.events import EventCandidate
from saju_shared_types.luck import DaewoonItem, LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.sinsal_direction import SamjaeQualityConfig, SinsalDirectionDict
from saju_shared_types.twelve_sinsal import (
    SAMJAE_QUALITY_LABEL_KO,
    SamjaeDomainGrade,
    SamjaeEvidence,
    SamjaeInfo,
    SamjaeQuality,
    samjae_branches,
    samjae_for,
)

from .counterfactual_context import _year_pillar_map
from .direction_suggestion import DEFICIENT_PCT, EXCESS_PCT, _group_percents
from .report_event_input import _DOMAIN_BY_KEY, _DOMAIN_KO
from .selection_allocation import _GROUP_KO

_STRENGTH_KO = {"weak": "약", "moderate": "중", "strong": "강"}
_DOMAIN_ORDER = ("career", "wealth", "relationship", "relocation", "health", "education")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """[lo, hi] 로 자른다."""
    return max(lo, min(hi, v))


def _daewoon_by_year(result: ManseV2Result) -> dict[int, DaewoonItem]:
    """연도 → 그 해가 속한 대운(근사 교운일, 시작 포함·끝 제외 — _daewoon_lookup 과 같은 규칙)."""
    out: dict[int, DaewoonItem] = {}
    if result.luck_cycles is None:
        return out
    for d in result.luck_cycles.daewoon_table:
        for y in range(d.approx_start_date.year, d.approx_end_date.year):
            out.setdefault(y, d)
    return out


def _candidate_sign(c: EventCandidate) -> int:
    """후보의 길흉 방향 — 표준 `result_direction`(2026-07-22 확정) 재사용.

    positive=+1 / negative=−1, 그 외(activation=압박·부담 동반 활성, delay, unknown/mixed)=0.
    별도 분류표를 두지 않아 개요·연도 스펙트럼과 같은 후보가 다른 방향으로 읽히지 않는다.
    """
    d = result_direction(c.quality, c.timing)
    return 1 if d == "positive" else -1 if d == "negative" else 0


def _net_direction(cands: list[EventCandidate]) -> float | None:
    """(유리 점수합 − 불리 점수합) / 전체합. 방향 있는 후보가 없으면 None."""
    pos = sum(c.score for c in cands if _candidate_sign(c) > 0)
    neg = sum(c.score for c in cands if _candidate_sign(c) < 0)
    total = pos + neg
    if total <= 0:
        return None
    return _clamp((pos - neg) / total)


def _effect(v: float, eps: float = 1e-9) -> str:
    """부호 → 근거 effect 라벨. 기여분(반올림 후)에 적용해 표시 부호와 기여 부호를 일치시킨다."""
    return "positive" if v > eps else "negative" if v < -eps else "neutral"


def _pillar_groups(pillar: LuckPillar) -> list[str]:
    """세운 천간·지지(본기) 십성군 — 중복 제거, 순서 유지."""
    out: list[str] = []
    for ko in (pillar.stem_ten_god, pillar.branch_ten_god):
        tg = TEN_GOD_KO_TO_KEY.get(ko)
        if tg is None:
            continue
        g = TEN_GOD_GROUP[tg].value
        if g not in out:
            out.append(g)
    return out


def domain_grades_for_year(
    cands: list[EventCandidate], cfg: SamjaeQualityConfig
) -> list[SamjaeDomainGrade]:
    """한 해 후보 목록 → 도메인별 길흉 등급(유리/혼합/주의). 후보 없는 도메인은 생략.

    삼재 quality(⑤항)와 방향 회피 판정(docs/19 §4 조건 ④)이 공유한다 — 같은 후보가 두 곳에서
    다른 등급으로 읽히지 않게 한 함수로 둔다. 임계는 사전 `samjae_quality.thresholds.domain`.
    """
    by_domain: dict[str, list[EventCandidate]] = {}
    for c in cands:
        dom = _DOMAIN_BY_KEY.get(str(c.event_key))
        if dom is None:
            continue
        by_domain.setdefault(dom, []).append(c)
    out: list[SamjaeDomainGrade] = []
    for dom in _DOMAIN_ORDER:
        dnet = _net_direction(by_domain.get(dom, []))
        if dnet is None:
            continue
        grade = (
            "favorable" if dnet >= cfg.thresholds.domain
            else "caution" if dnet <= -cfg.thresholds.domain
            else "mixed"
        )
        out.append(SamjaeDomainGrade(
            domain=dom, domain_ko=_DOMAIN_KO[dom], grade=grade, net=round(dnet, 4),
        ))
    return out


def evaluate_samjae(
    result: ManseV2Result,
    year: int,
    candidates: list[EventCandidate] | None = None,
    *,
    dictionary: SinsalDirectionDict | None = None,
) -> SamjaeInfo | None:
    """그 해가 삼재면 stage + quality/강도/근거/도메인/겹삼재까지 채운 SamjaeInfo, 아니면 None.

    Args:
        result: 만세력 결과(원국·대운·세운 필요).
        year: 달력연도(입춘 기준 세운 간지로 삼재 판정).
        candidates: 그 해를 포함하는 사건 후보(있으면 사건 방향·도메인 항 합성). None이면
            해당 항 없이 판정하고 `event_signal_included=False`(내부 플래그).
        dictionary: 방위·삼재 사전(캘리브레이션 상수·9칸 표현). None이면 기본 로드.
    """
    pillar = _year_pillar_map(result).get(str(year))
    if pillar is None:
        # 세운 기둥이 없는 해(첫 대운 이전 유년·대운표 밖) — stage만 결정론적으로 판정하고
        # quality는 비운다(입력이 없으면 '삼재 해가 아니다'로 오판하지 않는다 — 리뷰 수정).
        if result.pillars is None:
            return None
        return samjae_for(Branch(result.pillars.year.branch), year_ganzi(year)[1])
    return evaluate_samjae_pillar(
        result, pillar, _daewoon_by_year(result).get(year), candidates, dictionary=dictionary,
    )


def evaluate_samjae_pillar(
    result: ManseV2Result,
    pillar: LuckPillar,
    dw: DaewoonItem | None,
    candidates: list[EventCandidate] | None = None,
    *,
    dictionary: SinsalDirectionDict | None = None,
) -> SamjaeInfo | None:
    """세운 기둥 1건의 삼재 quality 판정(조회 맵을 호출자가 1회 구성해 넘기는 경로).

    stage는 `pillar.samjae`(luck_cycles가 저장한 값)를 그대로 쓴다 — 재계산하지 않는다.
    """
    if result.pillars is None or pillar.samjae is None:
        return None
    from .sinsal_direction import load_sinsal_direction_dict  # 순환 import 방지(지연)

    dic = dictionary or load_sinsal_direction_dict()
    cfg: SamjaeQualityConfig = dic.samjae_quality
    year_branch = Branch(result.pillars.year.branch)
    base = pillar.samjae
    year = int(pillar.label[:4])

    evidence: list[SamjaeEvidence] = []
    score = 0.0

    # ① 세운 극성(충·공망·합은 이미 포함 — 이중 감점 금지)
    annual = _clamp(pillar.luck_score)
    contrib = round(cfg.weights.annual_luck * annual, 4)
    score += contrib
    evidence.append(SamjaeEvidence(
        signal="annual_luck", effect=_effect(contrib), contribution=contrib,
        note=f"세운 {pillar.luck_label or pillar.yongsin_alignment}",
    ))

    # ② 대운 극성
    dw_v = _clamp(dw.luck_score) if dw is not None else 0.0
    if dw is not None:
        contrib = round(cfg.weights.daewoon_luck * dw_v, 4)
        score += contrib
        evidence.append(SamjaeEvidence(
            signal="daewoon_luck", effect=_effect(contrib), contribution=contrib,
            note=f"대운 {dw.ganji} {dw.luck_label or dw.yongsin_relation}",
        ))

    # ③ 충의 성격(점수엔 미반영된 주석 — 기신 충거는 정리, 용신 기반 손상은 부담)
    be = pillar.branch_effect
    label = be.branch_label if be is not None else ""
    if "충거" in label:
        score += cfg.weights.clash_note
        evidence.append(SamjaeEvidence(
            signal="clash_note", effect="positive", contribution=cfg.weights.clash_note,
            note="세운 지지가 원국 기신을 충거(정리)",
        ))
    elif "기반 손상" in label:
        score -= cfg.weights.clash_note
        evidence.append(SamjaeEvidence(
            signal="clash_note", effect="negative", contribution=-cfg.weights.clash_note,
            note="세운 지지가 원국 용신 기반을 충으로 손상",
        ))

    # ④ 십성 균형 — 원국 분포(운 미합산)에서 세운 십성군이 부족군이면 보완, 과다군이면 강화
    natal = _group_percents(result.pillars, [])
    for g in _pillar_groups(pillar):
        pct = natal.get(g, 0.0)
        if pct < DEFICIENT_PCT:
            score += cfg.weights.ten_god_balance
            evidence.append(SamjaeEvidence(
                signal="ten_god_balance", effect="positive",
                contribution=cfg.weights.ten_god_balance,
                note=f"원국에 부족한 {_GROUP_KO[g]}을 세운이 보충",
            ))
        elif pct >= EXCESS_PCT:
            score -= cfg.weights.ten_god_balance
            evidence.append(SamjaeEvidence(
                signal="ten_god_balance", effect="negative",
                contribution=-cfg.weights.ten_god_balance,
                note=f"원국에 과다한 {_GROUP_KO[g]}을 세운이 다시 강화",
            ))

    # ⑤ 사건 방향 + 도메인(후보가 주어진 경로에서만)
    domains: list[SamjaeDomainGrade] = []
    included = False
    if candidates is not None:
        cands = [c for c in candidates if str(c.period)[:4] == str(year)]
        net = _net_direction(cands)
        if net is not None:
            included = True
            contrib = round(cfg.weights.event_direction * net, 4)
            score += contrib
            evidence.append(SamjaeEvidence(
                signal="event_direction", effect=_effect(contrib),
                contribution=contrib,
                note="그 해 사건 후보의 길흉 방향이 "
                + ("유리 쪽" if net > 0.05 else "불리 쪽" if net < -0.05 else "혼재"),
            ))
            domains = domain_grades_for_year(cands, cfg)

    # ⑥ 대운·세운 동조
    amin = cfg.thresholds.alignment_min_abs
    if dw is not None and abs(annual) >= amin and abs(dw_v) >= amin and (annual > 0) == (dw_v > 0):
        bonus = cfg.weights.alignment_bonus if annual > 0 else -cfg.weights.alignment_bonus
        score += bonus
        evidence.append(SamjaeEvidence(
            signal="alignment", effect=_effect(bonus), contribution=bonus,
            note="대운과 세운이 같은 방향으로 기욺"
            + ("(지원 강화)" if bonus > 0 else "(부담 중첩)"),
        ))

    score = round(_clamp(score), 4)
    quality = (
        SamjaeQuality.BOK if score >= cfg.thresholds.bok
        else SamjaeQuality.AK if score <= cfg.thresholds.ak
        else SamjaeQuality.NORMAL
    )

    # 겹삼재(다른 축 — 강도에만 가산): 대운 지지가 삼재권 / 삼재 세운 지지가 원국 지지와 충
    # (relations_to_chart의 '충:' 항목 재사용). 일지 삼합 기준 삼재는 연지 삼재와 지지 집합이
    # 서로소라 같은 해에 겹칠 수 없어 정의하지 않는다(2026-09-20 실측).
    overlap: list[str] = []
    if dw is not None and Branch(dw.branch) in samjae_branches(year_branch):
        overlap.append("daewoon")
    if any(r.startswith("충:") for r in pillar.relations_to_chart):
        overlap.append("natal_clash")
    overlap_labels = [k.label_ko for k in cfg.overlap_kinds if k.kind in overlap]

    trigger = min(1.0, (be.event_trigger if be is not None else 0.0) / cfg.strength.trigger_max)
    strength = (
        cfg.strength.luck_weight * min(1.0, abs(pillar.luck_score))
        + cfg.strength.trigger_weight * trigger
        + cfg.strength.overlap_bonus * len(overlap)
    )
    strength = round(_clamp(strength, 0.0, 1.0), 4)
    band = (
        "weak" if strength < cfg.strength.bands.weak
        else "moderate" if strength < cfg.strength.bands.moderate
        else "strong"
    )
    phrase = next(
        (p.phrase for p in cfg.stage_quality_phrases
         if p.stage == base.stage.value and p.quality == quality.value),
        None,
    )
    return base.model_copy(update={
        "quality": quality,
        "quality_label": SAMJAE_QUALITY_LABEL_KO[quality],
        "quality_score": score,
        "strength": strength,
        "strength_label": _STRENGTH_KO[band],
        "stage_quality_phrase": phrase,
        "evidence": evidence,
        "domains": domains,
        "overlap": overlap,
        "overlap_label": " · ".join(overlap_labels) if overlap_labels else None,
        "event_signal_included": included,
    })


def enrich_samjae_quality(result: ManseV2Result) -> None:
    """만세력 결과의 세운(yearly_luck + 대운표 sewoon) samjae를 quality까지 채운다(제자리).

    사건 후보 없는 경로(만세력 페이지) — 사건 방향·도메인 항은 빠진다. 대운·세운 점수는 불변.
    """
    lc = result.luck_cycles
    if lc is None or result.pillars is None:
        return
    from .sinsal_direction import load_sinsal_direction_dict

    dic = load_sinsal_direction_dict()
    dw_by_year = _daewoon_by_year(result)  # 조회 맵 1회(기둥마다 재스캔하지 않는다)
    pillars: list[LuckPillar] = list(lc.yearly_luck)
    for d in lc.daewoon_table:
        pillars.extend(d.sewoon)
    for p in pillars:
        if p.samjae is None or not p.label.isdigit():
            continue
        info = evaluate_samjae_pillar(result, p, dw_by_year.get(int(p.label)), dictionary=dic)
        if info is not None:
            p.samjae = info
