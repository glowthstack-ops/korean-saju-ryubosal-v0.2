"""P0-A 교차검증 상세: 남성 3개 연도 + C1 월운 경로."""
from datetime import date

from measure_addendum import month_activations
from measure_relation_delta import engines, make_chart, report_year

from saju_engines.event_engine_v2 import _StackIndex
from saju_shared_types.event_engine import Pillar4


def main():
    base, ctrl = engines()

    # ── 추가 1: 남성 M1 (庚申 丁亥 己亥 戊辰) ──
    m1 = make_chart(date(1980, 11, 22), "09:08", "male")
    report_year("M1남 합(壬子·방합 기여 HAP/day)", m1, 2032, base, ctrl)
    report_year("M1남 충(己巳·巳亥충×2)", m1, 2049, base, ctrl)
    report_year("M1남 간합 甲己(甲子·MT1 남성 경로)", m1, 2044, base, ctrl)

    # ── 추가 2: C1 월운 경로 ──
    c1 = make_chart(date(1985, 3, 15), "14:30", "female")
    idx = _StackIndex(c1)
    print("\n--- C1 월운 커버리지 + 일지(丑) 발동 스캔 ---")
    for ym in sorted(idx.wolwoon_by_ym):
        pil = idx.wolwoon_by_ym[ym]
        acts = month_activations(base, c1, pil)
        day_desc = [f"{a.kind.value}/{a.position}" for a in acts if a.palace is Pillar4.DAY]
        print(f"  {ym} {pil.stem}{pil.branch} DAY:[{','.join(day_desc) or '-'}]")


if __name__ == "__main__":
    main()
