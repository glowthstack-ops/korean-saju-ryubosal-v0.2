"""QA-P0 — CAL-P0/FE-P0 probe pre-live 수동 QA (synthetic 20건).

transition_probe·trait_probe가 사용자 흐름에서 안전하게 동작하는지 오픈 전에 검증한다
(2026-07-03 데굴님 지시). 엔진 정확도 평가가 아니라 **probe 노출 조건·cap·payload·
LLM 힌트·판정 불변식** 검사다.

버킷 구성(합 20):
  A. 교운기 명확(기준일 ±1년 내 교체) 5건
  B. 교운기 멀리(기준일에서 4년 이상) 3건 — 과거 교운 해에 앵커된 probe는 정상
  C. 현침 → communication_style trait 4건
  D. 관성 표면 부재 → decision_style trait 4건(현침 없음)
  E. probe 미노출 일반 케이스 2건(대운 없음·trait 후보 없음)
  F. trait 반박(denied/mixed + 자유 진술) 시나리오 2건

금지 준수: probe 응답을 점수·favorability·role에 반영하지 않음(불변식으로 검사).

사용법: python scripts/qa_calibration_probes.py   (종료 코드 0=전건 통과)
"""

from __future__ import annotations

import sys
from datetime import date
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from saju_manse_calibration import generate_questions, select_validation_periods

from saju_api.services.manse_service import (
    _trait_probe_candidates,
    calculate,
    calibrate_feedback,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import CalibrationQuestionSet, FeedbackAnswer

_REF = date(2026, 7, 3)
_BANNED_WORDS = ("반드시", "무조건", "확실히", "됩니다", "옵니다", "생깁니다")


def _birth(y: int, m: int, d: int, hh: int, mm: int, gender: str) -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(y, m, d),
        birth_time=f"{hh:02d}:{mm:02d}", birth_place_name="서울",
        gender=gender, reference_date=_REF,
    )


def _case_facts(birth: BirthInput) -> dict:
    """케이스 분류에 필요한 사실(교운 거리·trait 후보·질문셋)을 수집한다."""
    r = calculate(birth)
    transitions = (
        [dw.approx_start_date.year for dw in r.luck_cycles.daewoon_table]
        if r.luck_cycles is not None
        else []
    )
    near = min((abs(_REF.year - t) for t in transitions), default=None)
    traits = _trait_probe_candidates(r)
    roles = dict(r.yongsin_analysis.canonical_roles) if r.yongsin_analysis else {}
    return {
        "birth": birth, "result": r, "cal": r.calibration,
        "transitions": transitions, "near": near,
        "trait_targets": [c.target for c in traits], "roles": roles,
    }


def _scan_pool() -> list[dict]:
    """후보 명식 풀 스캔 — 버킷을 채울 만큼 다양한 생년·시각·성별 조합."""
    pool: list[dict] = []
    dates = [
        (1980, 11, 22), (1975, 3, 8), (1988, 6, 15), (1992, 1, 30), (1969, 9, 9),
        (1984, 4, 17), (1996, 12, 5), (2001, 7, 21), (1972, 2, 14), (1990, 10, 3),
        (1986, 8, 26), (1978, 5, 11), (1994, 3, 3), (1965, 6, 6), (1999, 11, 11),
        (1982, 7, 7), (1970, 12, 25), (2004, 2, 2), (1987, 9, 18), (1976, 10, 29),
        (1991, 5, 24), (1968, 4, 1), (1997, 8, 8), (1983, 1, 15), (1971, 7, 31),
    ]
    times = [(9, 40), (23, 10), (4, 30)]
    genders = ["male", "female"]
    for (y, m, d), (hh, mm), g in product(dates, times, genders):
        pool.append(_case_facts(_birth(y, m, d, hh, mm, g)))
        if len(pool) >= 150:
            break
    # E 버킷 후보 — 성별 미상(대운 없음) 케이스도 스캔.
    for (y, m, d) in dates[:12]:
        pool.append(_case_facts(_birth(y, m, d, 9, 40, "unknown")))
    return pool


def _pick_buckets(pool: list[dict]) -> dict[str, list[dict]]:
    """버킷 A~F를 서로 다른 명식으로 채운다(부족 시 해당 버킷 축소 보고)."""
    taken: set[str] = set()

    def take(bucket: list[dict], pred, n: int) -> None:
        for c in pool:
            if len(bucket) >= n:
                return
            cid = c["result"].chart_id
            if cid in taken or c["cal"] is None or not pred(c):
                continue
            taken.add(cid)
            bucket.append(c)

    b: dict[str, list[dict]] = {k: [] for k in "ABCDEF"}
    take(b["A"], lambda c: c["near"] is not None and c["near"] <= 1, 5)
    take(b["B"], lambda c: c["near"] is not None and c["near"] >= 4, 3)
    take(b["C"], lambda c: c["trait_targets"][:1] == ["communication_style"], 4)
    take(b["D"], lambda c: c["trait_targets"][:1] == ["decision_style"], 4)
    take(b["E"], lambda c: not c["transitions"] and not c["trait_targets"], 2)
    take(b["F"], lambda c: bool(c["trait_targets"]), 2)
    return b


def _q_types(cal: CalibrationQuestionSet) -> dict[str, int]:
    out: dict[str, int] = {}
    for q in cal.questions:
        out[q.question_type] = out.get(q.question_type, 0) + 1
    return out


def _fe_payload(cal: CalibrationQuestionSet, trait_response: str | None,
                statement: str | None) -> list[FeedbackAnswer]:
    """FE 제출 payload와 동일 형태(전 문항 trait_response 키 포함)."""
    out = []
    for q in cal.questions:
        d = {"question_id": q.id, "overall_rating": "unknown", "selected_events": [],
             "event_ratings": {}, "domain_ratings": {}, "event_intensity": {},
             "trait_response": None, "trait_statement": None}
        if q.question_type == "trait_probe":
            d["trait_response"] = trait_response
            d["trait_statement"] = statement
        elif q.question_type == "transition_probe":
            d["selected_events"] = ["직업", "이동"]
        else:
            d["overall_rating"] = "positive"
        out.append(FeedbackAnswer.model_validate(d))
    return out


def _check_case(tag: str, c: dict, failures: list[str]) -> None:
    """체크 1~9 — 노출 조건·cap·q1~q5·불변식·힌트·문구."""
    cal = c["cal"]
    counts = _q_types(cal)
    n_tr, n_trait = counts.get("transition_probe", 0), counts.get("trait_probe", 0)

    def fail(msg: str) -> None:
        failures.append(f"[{tag}] {msg}")

    # 1·2 — transition 노출 조건 + cap.
    if c["transitions"]:
        if n_tr != 1:
            fail(f"교운 존재인데 q_transition {n_tr}개")
        else:
            q = next(q for q in cal.questions if q.question_type == "transition_probe")
            if not any(abs(q.year - t) <= 1 for t in c["transitions"]):
                fail(f"q_transition 앵커({q.year})가 교체 연도 ±1 밖")
            if any(w in q.question_text for w in _BANNED_WORDS):
                fail("q_transition 문구에 단정 표현")
    elif n_tr != 0:
        fail(f"교운 없음(대운 미산출)인데 q_transition {n_tr}개")
    # 3·4 — trait 노출 조건 + cap. CAL-P1-b 이후 trait는 pair 생성·cap(≤3)·suppress에
    # 밀려 0개일 수 있다(§1-C 우선순위 transition > pair > trait) — 상한과 무후보 0만 고정.
    if not c["trait_targets"] and n_trait:
        fail(f"trait 후보 없음인데 q_trait {n_trait}개")
    if n_trait > 1:
        fail(f"q_trait cap 초과: {n_trait}개")
    # CAL-P1-b — pair는 A/B 통째(0 또는 2), 추가 probe 총합 ≤3.
    n_pair = counts.get("static_deficiency_probe", 0) + counts.get(
        "transit_activation_probe", 0
    )
    if n_pair not in (0, 2):
        fail(f"pair 문항 수 이상(A 단독 금지): {n_pair}개")
    if n_tr + n_trait + n_pair > 3:
        fail(f"추가 probe 총합 cap 초과: {n_tr + n_trait + n_pair}개")
    # 5 — 기본 질문 구성 불변: probe 미주입(cap 0) 기준선과 (id, year)가 동일해야 한다.
    # 주의: q1~q5는 '최대 5종' — 갈림 해가 없으면 q3이 원래 생성되지 않는다(CAL-P0 이전
    # 동작). 그래서 '5개 존재'가 아니라 '기준선과 동일'이 정확한 불변식이다.
    r = c["result"]
    periods = select_validation_periods(
        r.yongsin_analysis, c["birth"].birth_date.year, _REF.year,
        pillars=r.pillars, transition_years=c["transitions"] or None,
    )
    baseline = generate_questions(
        periods, r.yongsin_analysis, gender=c["birth"].gender,
        max_transition_probes=0,
    )
    base_now = {
        (q.id, q.year) for q in cal.questions
        if not q.id.startswith(("q_transition", "q_trait", "q_pair"))
    }
    base_ref = {(q.id, q.year) for q in baseline.questions}
    if base_now != base_ref:
        fail(f"기본 질문 구성 변형: {sorted(base_now)} ≠ 기준선 {sorted(base_ref)}")
    if not base_now:
        fail("기본 질문 0개")

    # 6~9 — trait 응답 4종 대조(payload→backend→hint) + 판정 불변식.
    if n_trait:
        stmt80 = "실" * 80  # FE maxLength=80 경계 — 백엔드 수용 확인
        results = {
            resp: calibrate_feedback(c["birth"], _fe_payload(cal, resp, stmt80))
            for resp in ("denied", "mixed", "agreed", None)
        }
        decisions = {
            resp: (r.final_yongsin, r.final_heesin, r.final_gisin, r.final_gusin,
                   r.selected_model, tuple(sorted(r.model_scores.items())))
            for resp, r in results.items()
        }
        if len(set(decisions.values())) != 1:
            fail("trait 응답에 따라 용신 판정/점수 변화(불변식 위반)")
        for resp, r in results.items():
            expect_hint = resp in ("denied", "mixed")
            if bool(r.trait_llm_hints) != expect_hint:
                fail(
                    f"trait_response={resp}: 힌트 {len(r.trait_llm_hints)}건"
                    f"(기대 {int(expect_hint)})"
                )
            fb = r.trait_probe_feedback[0]
            if fb.scoring_effect != "none" or fb.review_status != "accumulate_only":
                fail(f"trait_response={resp}: 축적 플래그 오류")
            if resp is None and fb.user_feedback != "unclear":
                fail("미응답이 unclear로 처리되지 않음")
            if fb.user_statement != stmt80:
                fail("80자 진술 저장 불일치")


def main() -> int:
    pool = _scan_pool()
    buckets = _pick_buckets(pool)
    failures: list[str] = []
    total = 0
    print("=== QA-P0: calibration probe pre-live 20건 ===")
    for name, cases in buckets.items():
        for i, c in enumerate(cases, 1):
            total += 1
            tag = f"{name}{i}"
            b = c["birth"]
            _check_case(tag, c, failures)
            counts = _q_types(c["cal"])
            print(
                f"{tag}: {b.birth_date} {b.birth_time} {b.gender} | "
                f"교운거리={c['near']} trait={c['trait_targets'] or '-'} | probes: "
                f"tr={counts.get('transition_probe', 0)} "
                f"trait={counts.get('trait_probe', 0)}"
            )
    print(f"\n선별: {sum(len(v) for v in buckets.values())}건 "
          f"(A{len(buckets['A'])}/B{len(buckets['B'])}/C{len(buckets['C'])}/"
          f"D{len(buckets['D'])}/E{len(buckets['E'])}/F{len(buckets['F'])})")
    if failures:
        print(f"\n실패 {len(failures)}건:")
        for f in failures:
            print(" -", f)
        return 1
    print(f"\n전 {total}건 통과 — payload 정상·cap 위반 0·q1~q5 누락 0·"
          "role 변경 0·단정 표현 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
