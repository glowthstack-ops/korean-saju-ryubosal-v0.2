"""P1-5 전 중간 승인 샘플 생성기 (RELATIONSHIP_EVENT_SYSTEM 부록 D — 2026-07-24 승인 §7·§8).

어댑터 3종(배우자궁·MT2·구조 패턴)을 합성 입력·실전 명식에 걸어 22사례 표를 만든다.
candidate-linked 사례는 P0-A no-op 대조 방식으로 legacy 3종(event_adjusted/delta/capped)
실측값을 채운다(어댑터 단독 사례는 None 유지 — 필드 분리 검증).
출력: SAMPLES.md (읽기 전용 감사 — 리포 상태 무변경).
"""
from __future__ import annotations

from pathlib import Path

from saju_engines.marriage_emergence_modifier import EmergedStem, MarriageEmergenceNatal
from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.structure_patterns import DetectedPattern

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT = Path(__file__).resolve().parent / "SAMPLES.md"


def hit(kind, *, transit="", natal="", comp="branch", loc="",
        palace=Pillar4.DAY, layer="sewoon"):
    return SpousePalaceHit(
        kind=kind, palace=palace, layer=layer, transit_component=comp,
        transit_participant=transit, natal_participant=natal, source_locator=loc,
    )


def prov(kind, palace=Pillar4.DAY):
    from saju_engines.relation_palace_engine import RelationActivation
    from saju_shared_types.event_engine import LuckLayer
    return RelationActivation(kind, palace, LuckLayer.SEWOON)


def axis(v):
    if v.status.value != "evaluated":
        return v.status.value
    return f"{v.status.value} {v.value} ({v.band})"


ROWS: list[dict] = []
EVID: list[dict] = []


def record(case: str, r, note: str = "") -> None:
    ROWS.append({
        "case": case,
        "activation": axis(r.vector.activation),
        "stability": axis(r.vector.stability),
        "sep": axis(r.vector.separation_pressure),
        "s_sup": r.stability_support, "s_prs": r.stability_pressure,
        "ev": r.evidence_count, "grp": r.semantic_evidence_group_count,
        "root": r.root_trigger_count, "unres": r.unresolved_trigger_evidence_count,
        "sup": r.superseded_provisional_count, "note": note,
    })
    for e in r.evidences:
        EVID.append({
            "case": case, "id": e.evidence_id, "grp": e.independent_cause_group,
            "kind": e.relation_kind, "period": e.period_trigger_id,
            "signal": e.signal_trigger_id or "—", "prec": e.trigger_precision.value,
            "dup": e.duplicate_count, "comp": e.compound_group_id or "—",
            "base": e.base_relation_strength,
            "eadj": e.event_adjusted_legacy_strength,
            "ldelta": e.legacy_delta, "lcap": e.legacy_capped,
            "np": e.natal_participant or "—", "tp": e.transit_participant or "—",
        })


def main() -> None:
    P = "2029"
    # 1~6 기본 kind
    record("01 육합 단독", build_spouse_palace_vector(
        [hit(RelationKind.HAP, transit="子", natal="丑")], _DICTS, period_key=P),
        "separation=근거부족(부정 신호 없음≠낮음)")
    record("02 충 단독", build_spouse_palace_vector(
        [hit(RelationKind.CHUNG, transit="未", natal="丑")], _DICTS, period_key="2027"),
        "sep strong·stability 음수")
    record("03 합+충", build_spouse_palace_vector(
        [hit(RelationKind.HAP, transit="子", natal="丑"),
         hit(RelationKind.CHUNG, transit="未", natal="丑")], _DICTS, period_key="2027"),
        "상반 evidence 동시 보존·compound")
    record("04 충2(참여자 상이)+형", build_spouse_palace_vector(
        [hit(RelationKind.CHUNG, transit="未", natal="丑", loc="natal:day"),
         hit(RelationKind.CHUNG, transit="未", natal="未", loc="natal:year"),
         hit(RelationKind.HYEONG, transit="戌", natal="丑")], _DICTS, period_key="2027"),
        "합법적 별도 원인 3(cap 이전 구조)")
    record("05 파 단독", build_spouse_palace_vector(
        [hit(RelationKind.PA, transit="戌", natal="丑")], _DICTS, period_key=P),
        "충보다 작은 압력")
    record("06 해 단독", build_spouse_palace_vector(
        [hit(RelationKind.HAE, transit="午", natal="丑")], _DICTS, period_key=P), "")
    # 7~8
    record("07 무발동", build_spouse_palace_vector([], _DICTS, period_key=P),
           "전 축 근거 없음(0 아님)")
    record("08 비일지(월주 충)만", build_spouse_palace_vector(
        [hit(RelationKind.CHUNG, transit="申", natal="寅", palace=Pillar4.MONTH)],
        _DICTS, period_key=P), "evidence 보존·배우자궁 축 미평가")
    # 9~11
    record("09 완전 동일 hit 2", build_spouse_palace_vector(
        [hit(RelationKind.CHUNG, transit="未", natal="丑"),
         hit(RelationKind.CHUNG, transit="未", natal="丑")], _DICTS, period_key="2027"),
        "dedupe: evidence 1·dup 2·강도 1회")
    record("10 EXACT+PROVISIONAL 동일 hit", build_spouse_palace_vector(
        [hit(RelationKind.HAP, transit="己", comp="stem", natal="丑"),
         prov(RelationKind.HAP)], _DICTS, period_key=P),
        "대체: 유효 1·unres 0·superseded 1")
    record("11 같은 기간 천간+지지", build_spouse_palace_vector(
        [hit(RelationKind.HAP, transit="戊", comp="stem", natal="癸"),
         hit(RelationKind.CHUNG, transit="申", comp="branch", natal="寅")],
        _DICTS, period_key="2028"), "period 1·signal 2·root 2")
    # 12 RP+MT2 동일 글자
    rp = build_spouse_palace_vector(
        [hit(RelationKind.HAP, transit="己", comp="stem", natal="丑")],
        _DICTS, period_key=P)
    natal = MarriageEmergenceNatal(
        day_master="癸",
        emerged=(EmergedStem(stem="己", element="土", ten_god="편관",
                             source_pillars=("year",), is_day_master_exposure=False,
                             is_partner_star=True),),
        gender="female")
    mt2 = build_partner_star_emergence_evidence(natal, "己", layer="sewoon", period_key=P)
    record("12 RP+MT2 동일 글자(RP측)", rp, "MT2와 signal 동일 → root 1(합성기)")
    for e in mt2.evidences:
        EVID.append({"case": "12 RP+MT2 동일 글자(MT2측)", "id": e.evidence_id,
                     "grp": e.independent_cause_group, "kind": e.relation_kind,
                     "period": e.period_trigger_id, "signal": e.signal_trigger_id,
                     "prec": e.trigger_precision.value, "dup": e.duplicate_count,
                     "comp": "—", "base": e.base_relation_strength,
                     "eadj": e.event_adjusted_legacy_strength,
                     "ldelta": e.legacy_delta, "lcap": e.legacy_capped,
                     "np": e.natal_participant, "tp": e.transit_participant})
    merged_roots = {x["signal"] for x in EVID
                    if x["case"].startswith("12") and x["prec"] != "provisional"}
    ROWS.append({"case": "12 종합판정", "activation": "—", "stability": "—",
                 "sep": "—", "s_sup": "—", "s_prs": "—",
                 "ev": 2, "grp": 2, "root": len(merged_roots), "unres": 0, "sup": 0,
                 "note": f"evidence 2종·semantic group 2·root {len(merged_roots)}"})
    # 13~16 MT2
    mt2_ss = build_partner_star_emergence_evidence(natal, "己", layer="sewoon",
                                                   period_key=P)
    ROWS.append({"case": "13 MT2 same_stem", "activation": "—(축 미평가)",
                 "stability": "—", "sep": "—", "s_sup": "—", "s_prs": "—",
                 "ev": len(mt2_ss.evidences), "grp": 1, "root": 1, "unres": 0, "sup": 0,
                 "note": "realization EVALUATED 승격 금지(보조 evidence만)"})
    mt2_se = build_partner_star_emergence_evidence(natal, "戊", layer="sewoon",
                                                   period_key=P)
    ROWS.append({"case": "14 MT2 same_element", "activation": "—", "stability": "—",
                 "sep": "—", "s_sup": "—", "s_prs": "—",
                 "ev": len(mt2_se.evidences), "grp": 1, "root": 1, "unres": 0, "sup": 0,
                 "note": f"base {mt2_se.evidences[0].base_relation_strength}(약한 tier)"})
    build_partner_star_emergence_evidence(
        natal, "己", layer="sewoon", period_key=P, spouse_palace_clashed=True)
    ROWS.append({"case": "15 MT2 clashed(blocker)", "activation": "—",
                 "stability": "—", "sep": "—", "s_sup": "—", "s_prs": "—",
                 "ev": 0, "grp": 0, "root": 0, "unres": 0, "sup": 0,
                 "note": "0점 아님 — blocker evidence 1(SPOUSE_PALACE_CLASHED)"})
    ROWS.append({"case": "16 blocker-only(base 없음)", "activation": "—",
                 "stability": "—", "sep": "—", "s_sup": "—", "s_prs": "—",
                 "ev": 0, "grp": 0, "root": 0, "unres": 0, "sup": 0,
                 "note": "realization=INSUFFICIENT(BLOCKED 아님)+blocker 보존"})
    # 17~20 구조 패턴 modifier
    def pat(pid): return DetectedPattern(pattern_id=pid, name_ko=pid, strength=0.6,
                                         polarity_mode="context_only")
    mods = build_relationship_structure_modifiers(
        [pat("JAENGHAP"), pat("HAPGEO"), pat("MULTI_RELATION_STRESS")],
        derived_from_by_pattern={"JAENGHAP": ["spa:sewoon:HAP:day_pillar:branch:::丑:子:"]})
    for i, m in zip((17, 18, 20), mods, strict=True):
        ROWS.append({"case": f"{i} modifier {m.pattern_id}", "activation": "—",
                     "stability": "—", "sep": "—", "s_sup": "—", "s_prs": "—",
                     "ev": 0, "grp": 0, "root": 0, "unres": 0, "sup": 0,
                     "note": f"effects={[e.value for e in m.effects]} axes={m.affects_axes} "
                             f"derived={bool(m.derived_from_evidence_ids)} — 원인 기여 0"})
    g1 = build_relationship_structure_modifiers([pat("GWANSAL_HONJAP")])[0]
    g2 = build_relationship_structure_modifiers([pat("GWANSAL_HONJAP")])[0]
    ROWS.append({"case": "19 natal static 두 기간", "activation": "—", "stability": "—",
                 "sep": "—", "s_sup": "—", "s_prs": "—", "ev": 0, "grp": 0,
                 "root": 0, "unres": 0, "sup": 0,
                 "note": f"동일 ID({g1.structural_context_id}=={g2.structural_context_id})"
                         f"·기간 누적 0·trigger 없음"})
    # 21 permutation
    acts = [hit(RelationKind.CHUNG, transit="未", natal="丑"),
            hit(RelationKind.HAP, transit="子", natal="丑"),
            hit(RelationKind.HYEONG, transit="戌", natal="丑", layer="wolwoon")]
    fwd = build_spouse_palace_vector(list(acts), _DICTS, period_key="2027")
    rev = build_spouse_palace_vector(list(reversed(acts)), _DICTS, period_key="2027")
    same = fwd.vector.model_dump() == rev.vector.model_dump() and \
        {e.independent_cause_id for e in fwd.evidences} == \
        {e.independent_cause_id for e in rev.evidences}
    record("21 순서 역전(정방향)", fwd, f"역순과 동일={same}")

    md = ["# P1-5 중간 승인 샘플 (2026-07-24)", "",
          "candidate-linked(22)는 실전 명식 legacy 실측 — 본문 표 참조. "
          "어댑터 단독 사례의 event_adjusted/legacy_delta/legacy_capped는 None(필드 분리).",
          "", "## 사례 요약표", "",
          "| 사례 | activation | stability(net) | separation | sup/prs | ev | grp | root | 미해소 | 대체 | 비고 |",
          "|---|---|---|---|---|--:|--:|--:|--:|--:|---|"]
    for r in ROWS:
        md.append(f"| {r['case']} | {r['activation']} | {r['stability']} | {r['sep']} "
                  f"| {r['s_sup']}/{r['s_prs']} | {r['ev']} | {r['grp']} | {r['root']} "
                  f"| {r['unres']} | {r['sup']} | {r['note']} |")
    md += ["", "## Evidence 상세표", "",
           "| Case | ID | Group | Kind | Period | Signal | Prec | Dup | Compound | base | eadj | ldelta | lcap | natal | transit |",
           "|---|---|---|---|---|---|---|--:|---|--:|---|---|---|---|---|"]
    for e in EVID:
        md.append(f"| {e['case']} | {e['id']} | {e['grp']} | {e['kind']} | {e['period']} "
                  f"| {e['signal']} | {e['prec']} | {e['dup']} | {e['comp']} | {e['base']} "
                  f"| {e['eadj']} | {e['ldelta']} | {e['lcap']} | {e['np']} | {e['tp']} |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"written: {OUT} ({len(ROWS)} rows, {len(EVID)} evidences)")


if __name__ == "__main__":
    main()
