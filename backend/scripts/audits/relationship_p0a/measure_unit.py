"""P0-A 유닛 격리: RelationPalaceEngine.apply에 합성 발동을 넣어 순수 delta 측정."""
from datetime import date
from pathlib import Path

from measure_relation_delta import engines, make_chart, report_year

from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)

_DICTS = Path("/home/degool/projects/saju_v2/backend/dictionaries")
KEYS = ["new_relationship", "relationship_change", "marriage_signal"]


def run(label, acts):
    eng = RelationPalaceEngine(_DICTS)
    cands = [EventCandidateV2(event_key=k, period="2027", score=50) for k in KEYS]
    out = {str(c.event_key): c for c in eng.apply(cands, acts)}
    print(f"\n[unit] {label}")
    for k in KEYS:
        c = out[k]
        rel = [r for r in c.reason_codes if r.startswith("REL_")]
        print(f"  {k:22s} 50→{c.score}  delta={c.score-50}  palace={c.palace.value if c.palace else None}  {rel}")


def main():
    sew = LuckLayer.SEWOON
    D = Pillar4.DAY
    # 1) 배우자궁 육합 단독 (branch)
    run("육합 단독 HAP/day/branch", [RelationActivation(RelationKind.HAP, D, sew, position="branch", hap_subtype="six_harmony")])
    # 2) 배우자궁 충 단독
    run("충 단독 CHUNG/day/branch", [RelationActivation(RelationKind.CHUNG, D, sew, position="branch")])
    # 3) 합+충 복합 (충=일지, 합=타궁·월지) — compound HAP+CHUNG
    run("합+충 복합 CHUNG/day + HAP/month", [
        RelationActivation(RelationKind.CHUNG, D, sew, position="branch"),
        RelationActivation(RelationKind.HAP, Pillar4.MONTH, sew, position="branch", hap_subtype="six_harmony"),
    ])
    # 4) 쟁합 — 같은 글자가 년지·일지 두 곳과 합 (HAP/day + HAP/year)
    run("쟁합 HAP/day + HAP/year", [
        RelationActivation(RelationKind.HAP, D, sew, position="branch", hap_subtype="six_harmony"),
        RelationActivation(RelationKind.HAP, Pillar4.YEAR, sew, position="branch", hap_subtype="six_harmony"),
    ])
    # 참고: 형/파/해 단독
    run("형 단독 HYEONG/day", [RelationActivation(RelationKind.HYEONG, D, sew, position="branch")])
    run("파 단독 PA/day", [RelationActivation(RelationKind.PA, D, sew, position="branch")])
    run("해 단독 HAE/day", [RelationActivation(RelationKind.HAE, D, sew, position="branch")])
    # 충 3중첩(2027 실측 재현: CHUNG×2 + HYEONG) — 상한 22 확인
    run("충×2+형(상한 확인)", [
        RelationActivation(RelationKind.CHUNG, D, sew, position="branch"),
        RelationActivation(RelationKind.CHUNG, D, sew, position="branch"),
        RelationActivation(RelationKind.HYEONG, D, sew, position="branch"),
    ])

    # S5 관살혼잡 실측 — C1 여성, 2030(庚戌: ZHENGGUAN+QISHA, 丑戌형), 2036(丙辰: 관살혼잡+丑辰파)
    base, ctrl = engines()
    c1 = make_chart(date(1985, 3, 15), "14:30", "female")
    report_year("S5a C1 관살혼잡+형(庚戌)", c1, 2030, base, ctrl)
    report_year("S5b C1 관살혼잡+파(丙辰)", c1, 2036, base, ctrl)


if __name__ == "__main__":
    main()
