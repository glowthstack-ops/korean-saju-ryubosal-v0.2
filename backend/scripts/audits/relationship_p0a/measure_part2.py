"""P0-A 보강 측정: HAP 단독(후보 존재 연도), MT1 공존(戊申), S5 관살혼잡 디버그."""
from datetime import date

from measure_relation_delta import (
    engines,
    make_chart,
    present_gods_of,
    report_year,
)


def main():
    base, ctrl = engines()
    c1 = make_chart(date(1985, 3, 15), "14:30", "female")

    # S1c: 2028 戊申 — 일간 戊癸합(HAP/day/stem 단독) + MT1(干合 배우자성) 공존 확인
    report_year("S1c C1 천간합 단독(戊癸합·MT1 공존확인)", c1, 2028, base, ctrl)
    # S1d: 2049 己巳 — 삼합 기여 HAP/day/branch (편관 己 천간 → 관계 후보 존재 기대)
    report_year("S1d C1 삼합 HAP(己巳·편관 천간)", c1, 2049, base, ctrl)
    # 참고: 2039 己未 — 충+형 + 편관 천간(관계 후보 존재하는 충 연도 재확인)
    report_year("S2b C1 충(己未·편관 천간)", c1, 2039, base, ctrl)
    # S4 쟁합 참고 재측정: 2044 甲子(子가 년丑·일丑 동시 합 + 천간합 다수)
    report_year("S4b C1 쟁합(甲子)", c1, 2044, base, ctrl)

    # S5 디버그 — ten god 키 실제 값 확인
    print("\n--- S5 debug: C1 연도별 present_gods (2026~2040) ---")
    for y in range(2026, 2041):
        gods = present_gods_of(base, c1, y)
        names = sorted(str(g) for g in gods)
        mark = ""
        low = [n.lower() for n in names]
        has_jeong = any("jeonggwan" in n or "zhengguan" in n for n in low)
        has_pian = any("piangwan" in n or "pianguan" in n or "chilsal" in n or "qisha" in n for n in low)
        if has_jeong and has_pian:
            mark = "  <-- 관살혼잡"
        print(f"  {y}: {names}{mark}")

if __name__ == "__main__":
    main()
