"""P0-A: relation delta(배우자궁 합충형파해 가산)의 관계 이벤트 기여 실측 (읽기 전용).

baseline = EventEngineV2(**marriage_engine_flags()) 그대로.
control  = 동일 엔진에서 _relpalace.apply만 no-op으로 패치(메모리 내 — 리포 무변경).
"""
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import (
    EventEngineV2,
    _activations,
    _bokeum_activations,
    _StackIndex,
)
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import LuckLayer
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path("/home/degool/projects/saju_v2/backend/dictionaries")
REL_KEYS = {"new_relationship", "relationship_change", "marriage_signal"}
REF = date(2026, 7, 24)


class _NoopRelPalace:
    """relation delta 제거 대조군 — 후보를 무변경 통과."""

    def apply(self, candidates, activations, **kwargs):
        return candidates


def make_chart(bd: date, bt: str, gender: str):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=bd, birth_time=bt,
        birth_place_name="서울", gender=gender, reference_date=REF,
    ))


def engines():
    base = EventEngineV2(_DICTS, **marriage_engine_flags())
    ctrl = EventEngineV2(_DICTS, **marriage_engine_flags())
    ctrl._relpalace = _NoopRelPalace()  # type: ignore[assignment]
    return base, ctrl


def fmt_reasons(codes, prefix_set=("REL_",)):
    return [c for c in codes if any(c.startswith(p) for p in prefix_set)]


def report_year(tag, r, year, base, ctrl):
    idx = _StackIndex(r)
    pil = idx.sewoon_by_year[year]
    hits = base._relation_hits(r, GanjiLevel.YEAR, pil)
    acts = _activations(hits, LuckLayer.SEWOON) + _bokeum_activations(r, pil, LuckLayer.SEWOON)
    act_desc = [f"{a.kind.value}/{a.palace.value.replace('_pillar','')}/{a.position}" for a in acts]
    b_cands = base.score_years(r, [year])
    c_cands = ctrl.score_years(r, [year])
    b_top5 = [(str(c.event_key), c.score) for c in b_cands[:5]]
    c_top5 = [(str(c.event_key), c.score) for c in c_cands[:5]]
    b_map = {str(c.event_key): c for c in b_cands}
    c_map = {str(c.event_key): c for c in c_cands}
    b_rank = {str(c.event_key): i + 1 for i, c in enumerate(b_cands)}
    c_rank = {str(c.event_key): i + 1 for i, c in enumerate(c_cands)}

    print(f"\n=== [{tag}] year={year} sewoon={pil.stem}{pil.branch} ===")
    print(f"  activations: {act_desc or '없음'}")
    print(f"  Top5 baseline: {b_top5}")
    print(f"  Top5 control : {c_top5}")
    for key in ("new_relationship", "relationship_change", "marriage_signal"):
        b = b_map.get(key)
        c = c_map.get(key)
        if b is None and c is None:
            print(f"  {key:22s} 후보 없음(양쪽)")
            continue
        bs = b.score if b else None
        cs = c.score if c else None
        rel_contrib = (b.contributions.get("relation") if b else None)
        rel_r = fmt_reasons(b.reason_codes) if b else []
        mt_r = fmt_reasons(b.reason_codes, ("MT1_", "MT2_", "MT3_", "MT4_", "SPOUSE_PALACE")) if b else []
        print(f"  {key:22s} score ctrl→base: {cs}→{bs}  relContrib={rel_contrib}  "
              f"rank ctrl→base: {c_rank.get(key)}→{b_rank.get(key)}  "
              f"conf={b.confidence_level.value if b else None}/{c.confidence_level.value if c else None}  "
              f"fav base={round(b.favorability,3) if b else None}")
        print(f"      REL={rel_r or '-'}  MT={mt_r or '-'}")
        if b:
            print(f"      all_reasons(base)={list(b.reason_codes)}")
    return b_cands, c_cands


def present_gods_of(base, r, year):
    idx = _StackIndex(r)
    pil = idx.sewoon_by_year[year]
    stack = idx.stack_for(GanjiLevel.YEAR, str(year), pil)
    sigs = [s for layer, p in stack for s in base._brancher.collect_from_pillar(
        p, layer, is_target=(layer is LuckLayer.SEWOON))]
    return {s.ten_god for s in sigs}


def main():
    base, ctrl = engines()

    # C1: 여성 1985-03-15 14:30 서울 — 乙丑 己卯 癸丑 己未 (일지 丑 = 배우자궁)
    c1 = make_chart(date(1985, 3, 15), "14:30", "female")
    p = c1.pillars
    print("C1 pillars:", p.year.stem + p.year.branch, p.month.stem + p.month.branch,
          p.day.stem + p.day.branch, p.hour.stem + p.hour.branch)

    # S1a 배우자궁 HAP 단독(방합 기여, kinds={HAP}): 2031 辛亥
    report_year("S1a C1 HAP단독(방합·잡음없음)", c1, 2031, base, ctrl)
    # S1b 배우자궁 육합(子丑) — 부수 형·해 동반: 2032 壬子 (쟁합: 子가 년지丑+일지丑 동시 합 → S4 겸용)
    report_year("S1b/S4 C1 육합+쟁합(년丑·일丑 동시합)", c1, 2032, base, ctrl)
    # S2 배우자궁 충(丑未충, 삼형 동반): 2027 丁未
    report_year("S2 C1 충(丑未충+형 동반)", c1, 2027, base, ctrl)
    # S7 대조군: 2035 乙卯 — 원국과 합충형파해 없음
    report_year("S7 C1 대조군(乙卯·무발동)", c1, 2035, base, ctrl)

    # S5 관살혼잡 탐색: C1 여성 — 정관+편관 동시 존재 연도
    print("\n--- S5 후보 탐색: C1 present_gods (2026~2040) ---")
    for y in range(2026, 2041):
        gods = present_gods_of(base, c1, y)
        names = {getattr(g, "value", str(g)) for g in gods}
        if any("정관" in n for n in names) and any("편관" in n for n in names):
            print(f"  {y}: {sorted(names)}  <-- 관살혼잡")

    # C3: 여성 1986-01-12 10:30 서울 — 乙丑 己丑 丙辰 癸巳 (일지 辰)
    c3 = make_chart(date(1986, 1, 12), "10:30", "female")
    p3 = c3.pillars
    print("\nC3 pillars:", p3.year.stem + p3.year.branch, p3.month.stem + p3.month.branch,
          p3.day.stem + p3.day.branch, p3.hour.stem + p3.hour.branch)
    # S3 배우자궁 충 + 타궁 합 복합(compound HAP+CHUNG/HYEONG+CHUNG): 2030 庚戌
    report_year("S3 C3 일지충+합 복합(辰戌충+HAP)", c3, 2030, base, ctrl)
    # C3 대조 무발동 연도 탐색용 — 2033? 확인차 몇 년 출력 생략.

    # C6: 여성 1986-03-30 10:30 서울 — 일지 癸酉, 도화=午. 2026 丙午: 일지 비활성.
    c6 = make_chart(date(1986, 3, 30), "10:30", "female")
    p6 = c6.pillars
    print("\nC6 pillars:", p6.year.stem + p6.year.branch, p6.month.stem + p6.month.branch,
          p6.day.stem + p6.day.branch, p6.hour.stem + p6.hour.branch)
    report_year("S6 C6 도화년(丙午)·배우자궁 비활성", c6, 2026, base, ctrl)


if __name__ == "__main__":
    main()
