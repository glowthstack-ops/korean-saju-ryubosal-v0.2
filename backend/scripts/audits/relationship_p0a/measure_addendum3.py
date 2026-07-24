"""P0-A 교차검증 마무리: C1 월운 상세 + 양간(甲) 남성 MT1 재성 간합 경로."""
from datetime import date, timedelta

from measure_addendum import report_month
from measure_relation_delta import engines, make_chart, report_year


def main():
    base, ctrl = engines()

    # ── 추가 2 상세: C1 월운(합 월/충 월/비활성 월) ──
    c1 = make_chart(date(1985, 3, 15), "14:30", "female")
    report_month("월운 합(癸巳·巳丑삼합 기여)", c1, base, ctrl, "2026-05")
    report_month("월운 충(乙未·丑未충×2+형)", c1, base, ctrl, "2026-07")
    report_month("월운 육합(庚子·子丑합·쟁합형)", c1, base, ctrl, "2026-12")
    report_month("월운 비활성 대조(丙申)", c1, base, ctrl, "2026-08")

    # ── 추가 1 보강: 양간 甲 일간 남성 — MT1 남성(재성 干合) 경로 ──
    d = date(1984, 6, 1)
    m2 = None
    while d < date(1984, 9, 1):
        r = make_chart(d, "10:30", "male")
        if r.pillars and r.pillars.day.stem == "甲":
            m2 = r
            break
        d += timedelta(days=1)
    if m2 is None:
        print("양간 甲 남성 미발견")
        return
    p = m2.pillars
    print(f"\nM2(남·甲일간) birth={d} pillars:", p.year.stem + p.year.branch,
          p.month.stem + p.month.branch, p.day.stem + p.day.branch, p.hour.stem + p.hour.branch)
    # 己 년(甲己합·정재=남성 배우자성): 2029 己酉 / 2039 己未 / 2049 己巳 중 가까운 순서로 확인.
    for y in (2029, 2039, 2049):
        report_year(f"M2남 간합 己(={y}·MT1 재성 경로)", m2, y, base, ctrl)


if __name__ == "__main__":
    main()
