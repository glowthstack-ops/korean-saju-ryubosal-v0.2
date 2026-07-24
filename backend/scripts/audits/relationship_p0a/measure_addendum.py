"""P0-A 교차검증 추가 측정: (1) 남성 실전 명식, (2) 월운 경로(C1).

리포 무수정 — 기존 p0a 하네스 재사용. 월운은 chat_service와 동일 경로
(engine.score(chart, levels={GanjiLevel.MONTH}) — monthly_luck 전체 스코어링 후 period 필터).
"""
from datetime import date

from measure_relation_delta import engines, fmt_reasons, make_chart

from saju_engines.event_engine_v2 import _activations, _bokeum_activations, _StackIndex
from saju_shared_types.event_engine import LuckLayer, Pillar4
from saju_shared_types.ganji_calendar import GanjiLevel

REL_KEYS = ("new_relationship", "relationship_change", "marriage_signal")


def month_activations(base, r, pil):
    hits = base._relation_hits(r, GanjiLevel.MONTH, pil)
    return _activations(hits, LuckLayer.WOLWOON) + _bokeum_activations(r, pil, LuckLayer.WOLWOON)


def scan_male(base, ctrl, r, years):
    """남성 명식 — 연도별 일지 발동 + 관계 후보 존재 여부 훑기."""
    idx = _StackIndex(r)
    for y in years:
        pil = idx.sewoon_by_year.get(y)
        if pil is None:
            continue
        hits = base._relation_hits(r, GanjiLevel.YEAR, pil)
        acts = _activations(hits, LuckLayer.SEWOON) + _bokeum_activations(r, pil, LuckLayer.SEWOON)
        day_desc = [f"{a.kind.value}/{a.position}" for a in acts if a.palace is Pillar4.DAY]
        cands = base.score_years(r, [y])
        rels = {str(c.event_key): c.score for c in cands if str(c.event_key) in REL_KEYS}
        print(f"  {y} {pil.stem}{pil.branch} DAY:[{','.join(day_desc) or '-'}] relCands={rels or '-'}")


def report_month(tag, r, base, ctrl, ym):
    """월운 경로 — score(levels={MONTH}) 후 해당 월 필터, ctrl 비교."""
    b_all = base.score(r, levels={GanjiLevel.MONTH})
    c_all = ctrl.score(r, levels={GanjiLevel.MONTH})
    b_m = [c for c in b_all if c.period == ym]
    c_m = [c for c in c_all if c.period == ym]
    idx = _StackIndex(r)
    pil = idx.wolwoon_by_ym.get(ym)
    acts = month_activations(base, r, pil) if pil else []
    act_desc = [f"{a.kind.value}/{a.palace.value.replace('_pillar','')}/{a.position}" for a in acts]
    b_map = {str(c.event_key): c for c in b_m}
    c_map = {str(c.event_key): c for c in c_m}
    b_rank = {str(c.event_key): i + 1 for i, c in enumerate(b_m)}
    c_rank = {str(c.event_key): i + 1 for i, c in enumerate(c_m)}
    print(f"\n=== [{tag}] month={ym} wolwoon={pil.stem}{pil.branch if pil else '?'} ===")
    print(f"  activations(월운층): {act_desc or '없음'}")
    print(f"  Top5 baseline: {[(str(c.event_key), c.score) for c in b_m[:5]]}")
    print(f"  Top5 control : {[(str(c.event_key), c.score) for c in c_m[:5]]}")
    for key in REL_KEYS:
        b, c = b_map.get(key), c_map.get(key)
        if b is None and c is None:
            print(f"  {key:22s} 후보 없음(양쪽)")
            continue
        rel_r = fmt_reasons(b.reason_codes) if b else []
        mt_r = fmt_reasons(b.reason_codes, ("MT1_", "MT2_", "MT3_", "MT4_", "SPOUSE_PALACE")) if b else []
        print(f"  {key:22s} score ctrl→base: {c.score if c else None}→{b.score if b else None}  "
              f"relContrib={b.contributions.get('relation') if b else None}  "
              f"rank ctrl→base: {c_rank.get(key)}→{b_rank.get(key)}  "
              f"conf={b.confidence_level.value if b else None}/{c.confidence_level.value if c else None}  "
              f"fav={round(b.favorability, 3) if b else None}")
        print(f"      REL={rel_r or '-'}  MT={mt_r or '-'}")
        if b:
            print(f"      all_reasons(base)={list(b.reason_codes)}")


def main():
    base, ctrl = engines()

    # ── 추가 1: 남성 실전 명식 ────────────────────────────────────
    # 기존 유닛테스트 픽스처 명식(test_event_engine_v2.py): 남성 1980-11-22 09:08 서울.
    m1 = make_chart(date(1980, 11, 22), "09:08", "male")
    p = m1.pillars
    print("M1(남성 픽스처) pillars:", p.year.stem + p.year.branch, p.month.stem + p.month.branch,
          p.day.stem + p.day.branch, p.hour.stem + p.hour.branch)
    print("--- M1 연도 스캔(2026~2049): 일지 발동 × 관계 후보 존재 ---")
    scan_male(base, ctrl, m1, range(2026, 2050))


if __name__ == "__main__":
    main()
