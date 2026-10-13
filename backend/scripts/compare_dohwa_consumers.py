"""도화 정비 소비처 전후 비교 — 같은 결정론 모집단으로 재측정 (2026-10-13 데굴님 지시).

정비 기준: 글자 보유(사정지)와 도화 성립(진도화)을 구분한다. 결혼 자원·궁합은 글자 기준을
이미 제거했고(이 스크립트는 그 전후 차이를 잰다), 외적 인상은 **새 가중치 근거가 없어** 실운영
값을 바꾸지 않은 채 후보안별 band 분포를 비교했다 — 2026-10-13 D안 확정·적용. 이후에는 실운영(A)=D
재현 확인과 가중 재조정 전후 재측정에 같은 모집단을 쓴다.

외적 인상 후보안(도화 계열 신호만 바꾸고 나머지 신호·band 규칙은 엔진 그대로):
  A 실운영      엔진 현재값(2026-10-13 D안 확정 이후에는 D와 같아야 한다 — 회귀 확인용).
                확정 전 현행은 일지 子午卯酉 1.2 + 진도화(어느 자리)·홍염 1.0 + 일지 외 子午卯酉 0.3
  B 성립 기준    일지 진도화 1.2 + 일지 외 진도화·홍염 1.0(같은 진도화 중복 가산 없음) +
                일지 외 子午卯酉 0.3 · 일지 글자만은 무가중
  C B + 글자 통합 B 에서 일지 글자만도 일지 외 글자와 같은 0.3(글자 보유 보조 1건으로 통합)
  D 글자 제거    B 에서 글자 보유 신호(0.3) 전부 제거
수치 1.2·1.0·0.3 은 모두 현행 엔진에 이미 있는 값이며 새 수치를 만들지 않는다.

사용: python scripts/compare_dohwa_consumers.py [--years 1950-2009] [--step 7]

간격은 60과 서로소여야 한다 — 일주는 60일 주기라 9일 간격이면 일지가 辰戌丑未 4종만 나와
子午卯酉 일지가 0명이 된다(2026-10-13 1차 실행 결함). 모집단이 60일주를 모두 덮는지 검사한다.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
from math import gcd

from saju_manse_analysis.sinsal.sinsal_catalog import HONGYEOM, SAJEONG

from saju_api.services.manse_service import calculate
from saju_engines.compatibility_engine import _attraction_band, analyze_compatibility
from saju_engines.context_reducer import build_birth_summary
from saju_engines.dohwa import analyze_dohwa
from saju_engines.external_impression import analyze_external_impression
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatSignalKind
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.external_impression import ExternalImpressionSignal
from saju_shared_types.manse_result import ManseV2Result

_TIMES = ("03:30:00", "09:30:00", "15:30:00", "21:30:00")
_PEACH_CODES = {"DAY_BRANCH_PEACH", "ACTUAL_DOHWA_OR_HONGYEOM", "NON_DAY_PEACH_BRANCH"}
_BANDS = ("none", "weak", "notable", "strong")


def _population(y0: int, y1: int, step: int) -> list[ManseV2Result]:
    """결정론 모집단 — y0-01-01 부터 step 일 간격, 시각·성별 순환."""
    out: list[ManseV2Result] = []
    d, i = date(y0, 1, 1), 0
    while d <= date(y1, 12, 31):
        gender = "female" if i % 2 == 0 else "male"
        out.append(calculate(BirthInput(
            birth_date=d, birth_time=_TIMES[i % 4], birth_place_name="서울", gender=gender,
        )))
        d += timedelta(days=step)
        i += 1
    return out


def _band(signals: list[ExternalImpressionSignal]) -> str:
    """엔진(analyze_external_impression)과 같은 score·gate·band 규칙."""
    scored = [s for s in signals if s.tier != "note"]
    score = sum(s.weight for s in scored)
    gated = any(s.tier == "primary" for s in scored) and len({s.category for s in scored}) >= 2
    if gated and score >= 2.8:
        return "strong"
    if gated and score >= 1.8:
        return "notable"
    return "weak" if score >= 1.0 else "none"


def _peach(code: str, weight: float, tier: str) -> ExternalImpressionSignal:
    return ExternalImpressionSignal(
        code=code, category="peach", legacy_ko=code, modern_ko=code, weight=weight, tier=tier,
    )


def _impression_candidates(r: ManseV2Result) -> dict[str, str]:
    """후보안별 band."""
    assert r.pillars is not None
    prof = analyze_external_impression(r)
    base = [s for s in prof.signals if s.code not in _PEACH_CODES]
    p = r.pillars
    dohwa = analyze_dohwa(r)
    est = dohwa.established if dohwa is not None else []
    day_jin = any(e.position == "day" for e in est)
    other_jin = any(e.position != "day" for e in est)
    branches = [Branch(x.branch) for x in (p.year, p.month, p.day, p.hour) if x is not None]
    hong = HONGYEOM.get(Stem(p.day.stem)) in branches
    day_glyph = Branch(p.day.branch) in SAJEONG
    other_glyph = any(
        Branch(x.branch) in SAJEONG for x in (p.year, p.month, p.hour) if x is not None
    )
    b_sig = list(base)
    if day_jin:
        b_sig.append(_peach("DAY_JIN", 1.2, "primary"))
    if other_jin or hong:
        b_sig.append(_peach("JIN_OR_HONG", 1.0, "primary"))
    c_sig, d_sig = list(b_sig), list(b_sig)
    if other_glyph:
        b_sig.append(_peach("GLYPH", 0.3, "secondary"))
    if other_glyph or (day_glyph and not day_jin):
        c_sig.append(_peach("GLYPH", 0.3, "secondary"))
    return {"A": prof.band, "B": _band(b_sig), "C": _band(c_sig), "D": _band(d_sig)}


def main() -> None:
    """모집단을 만들고 세 소비처의 전후 차이를 표로 출력한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1950-2009")
    ap.add_argument("--step", type=int, default=7)
    args = ap.parse_args()
    y0, y1 = (int(x) for x in args.years.split("-"))
    if gcd(args.step, 60) != 1:
        raise SystemExit(f"--step {args.step} 은 60과 서로소가 아니다 — 일주가 일부만 표집된다")
    pop = _population(y0, y1, args.step)
    n = len(pop)
    days = {r.pillars.day.ganji for r in pop if r.pillars is not None}
    if len(days) != 60:
        raise SystemExit(f"모집단 일주 {len(days)}/60 — 표집 편향")
    print(f"모집단 {n}명 ({args.years}, {args.step}일 간격, 시각 4종·성별 교대)\n")

    # 결혼 자원 — 글자 기준(전) vs 진도화·홍염 각자 조건(후).
    old_charm = new_charm = old_dohwa = new_dohwa = 0
    for r in pop:
        assert r.pillars is not None
        branches = [
            Branch(x.branch) for x in (r.pillars.year, r.pillars.month, r.pillars.day,
                                       r.pillars.hour) if x is not None
        ]
        glyph = any(b in SAJEONG for b in branches)
        hong = HONGYEOM.get(Stem(r.pillars.day.stem)) in branches
        mr = analyze_marriage_resource(r)
        old_charm += glyph or hong
        new_charm += mr.charm_present
        old_dohwa += glyph
        new_dohwa += mr.dohwa_established
    print("[결혼 자원] 도화 표기 대상", f"전 {old_dohwa}({old_dohwa / n:.1%})",
          f"→ 후 {new_dohwa}({new_dohwa / n:.1%})")
    print("[결혼 자원] 도화·홍염 끌림 문장", f"전 {old_charm}({old_charm / n:.1%})",
          f"→ 후 {new_charm}({new_charm / n:.1%})\n")

    # 궁합 — 이웃 쌍. 전: 일지 子午卯酉(어느 쪽이든) 또는 홍염 교차 → +2. 후: 홍염 교차만 +2.
    shift: Counter[tuple[str, str]] = Counter()
    pairs = 0
    for a, b in zip(pop[0::2], pop[1::2], strict=False):
        assert a.pillars is not None and b.pillars is not None
        sa, sb = build_birth_summary(a), build_birth_summary(b)
        rep = analyze_compatibility(a, b, sa.useful_gods, sb.useful_gods)
        if rep is None:
            continue
        pairs += 1
        hong_now = any(s.kind is CompatSignalKind.SINSAL_CHARM for s in rep.signals)
        da, db = Branch(a.pillars.day.branch), Branch(b.pillars.day.branch)
        old_charm_pair = da in SAJEONG or db in SAJEONG or hong_now
        old_score = rep.attraction_score - (2 if hong_now else 0) + (2 if old_charm_pair else 0)
        shift[(_attraction_band(old_score), rep.attraction_band)] += 1
    print(f"[궁합] 끌림 밴드 전→후 ({pairs}쌍)")
    for (o, nw), c in sorted(shift.items()):
        mark = "" if o == nw else "  ← 변화"
        print(f"  {o} → {nw}: {c} ({c / pairs:.1%}){mark}")
    print()

    # 외적 인상 — 후보안별 band 분포(실운영 값 불변).
    cands = [_impression_candidates(r) for r in pop]
    print("[외적 인상] 후보안별 band 분포(A=실운영 엔진값)")
    print("  안 | " + " | ".join(_BANDS) + " | notable 이상")
    for key in ("A", "B", "C", "D"):
        cnt = Counter(c[key] for c in cands)
        hi = cnt["notable"] + cnt["strong"]
        cells = " | ".join(f"{cnt[b]}({cnt[b] / n:.1%})" for b in _BANDS)
        print(f"  {key} | {cells} | {hi}({hi / n:.1%})")
    for key in ("B", "C", "D"):
        moved = Counter((c["A"], c[key]) for c in cands if c["A"] != c[key])
        print(f"  A→{key} 변화 {sum(moved.values())}명: "
              + ", ".join(f"{o}→{nw} {k}" for (o, nw), k in sorted(moved.items())))


if __name__ == "__main__":
    main()
