#!/usr/bin/env python3
"""DW-HWA — 대운 합화 배경 보정의 설계 위치 감수 (측정 전용, production 불변).

선행 감사(WC-SCORE)에서 `wealth_change` 단일 fixture 로 강한 인과가 나왔다.

    현행              loss 6/8
    daewoon_hwa 제거   loss 3/8   대표 교체 3건

그러나 `_apply_daewoon_hwa_background` 는 `event_key` 가 아니라 `c.quality`(길/흉군)로
분기한다. 재물 하나만 보고 설계 위치를 정하면 다른 도메인에서 반대 방향이 나와도 모른다.
그래서 **명식 4종 × 도메인 3종** 으로 넓힌다.

감수 질문:

    A  발생·대표 순위를 조절해야 하는가
    B  같은 사건의 체감 품질만 조절해야 하는가
    C  설명용 장기 배경으로만 써야 하는가

핵심은 P2-PROV-2a 가 이미 경고한 지점이다 — 이 배경은 특정 사건의 발생 지지를 뜻하지
않는데(분기가 quality 군이다), 현재 구현은 랭킹 이전에 점수를 곱해 **대표 선정까지**
바꾼다. event-family 점유가 크게 흔들린다면 quality 보정이 occurrence selection 을
간접 지배한다는 증거가 된다.

시나리오(점수 계수만 교체, 다른 계산·선정 계약은 전부 동일):

    A CURRENT          ±3%  현행
    B REMOVED          0%
    C NARRATIVE_ONLY   점수 미반영 — 수치는 B 와 동일하므로 재계산하지 않는다
    D ATTENUATED       ±1%  축소 shadow

D 를 여러 비율로 탐색하지 않는다. 그러면 설계 감수가 튜닝 실험으로 변한다.

범위 제한: 이 결과는 **설계 감수 근거이지 전체 명식에 대한 일반화 통계가 아니다.**
명식 4종은 조건을 만족하도록 의도적으로 선별됐다(144명식 스캔).

측정 중 이 스크립트 자신의 결함 두 건을 고쳤다. 둘 다 **결과를 그럴듯하게 만들면서
틀리게** 하는 종류다.

    임의 짝짓기   진입 후보의 상대를 같은 시점에서 못 찾으면 탈락 목록의 첫 번째로
                 폴백했다. 경쟁한 적 없는 둘의 근거를 비교한 것이라 초판 집계
                 (A우세 9 / B우세 6)는 폐기했다. 실제 맞대결은 5건뿐이다.
    접두어 오기   `STAGE_`·`PATTERN_` 등 존재하지 않는 접두를 넣어 manifestation/
                 stage 가 통째로 빠졌다(실제 표기는 `stage:`). 전체 reason code 의
                 26% 만 세고 있었다. 미분류 카운터를 넣어 0건까지 맞췄다.

────────────────────────────────────────────────────────────────────────────
실측 (2026-07-31, 명식 4종 × 도메인 3종)

    음성 대조      NO_HWA: A==B 점수 전건 동일 · 전 도메인 변화 0  → 측정 유효

    대표가 바뀐 셀             12개 중 8개
    대표 교체 총               17건
      시점 자체가 Top-K 이탈   12건 (71%)
      같은 시점 내 경쟁 패배    5건 (29%)
    후보 동일 + quality 만 변경  0건        ← 축 3 의 결정적 관측
    순위 이동 최대             20위
    family 고유 수 합계        A=19  B=17
    맞대결 5건의 근거 비교     B우세 3 / A우세 2 · 근거 수 차이(A−B) 평균 −1.4
    D(±1%) 가 B(제거)와 동일   12셀 중 10셀   ← 비선형: 1%와 3% 사이에서 뒤집힌다

부수 관측: 합화 성립 자체가 드물고, 보강(용·희) 대운은 압력보다 훨씬 희소했다
(144명식 중 boon 지배 2건).

판정

    DAEWOON_HWA_RANK_EFFECT_CONFIRMED
    DAEWOON_HWA_PERIOD_SELECTION_EFFECT_CONFIRMED
    DAEWOON_HWA_EVENT_FAMILY_EFFECT_OBSERVED
    DAEWOON_HWA_OCCURRENCE_ALIGNMENT_NOT_DEMONSTRATED
    DAEWOON_HWA_RANKING_EFFECT_NOT_JUSTIFIED_ON_AUDITED_FIXTURES
    DAEWOON_HWA_SHOULD_BE_POST_SELECTION_QUALITY_MODIFIER
    PRODUCTION_UNCHANGED

`POST_SELECTION_QUALITY_MODIFIER` 는 canonical `EventQuality` 를 다시 바꾸라는 뜻이
**아니다.** quality 는 `YongiQualityEngine` 이 정하며, 그것을 대운 배경으로 뒤집으면
같은 순환이 남는다. 목표는 occurrence score·rank·대표 시점에서 영향을 0 으로 두고,
대표 선정 **이후** 의 experience/severity/서사 강도에만 배경을 반영하는 것이다.

±1% 추가 튜닝은 하지 않는다. 10/12 셀에서 제거와 같고 나머지는 근사 동점 순위만
흔들었으므로, 랭킹 계수로서 안정적인 유효 구간을 찾는 문제 자체를 중단한다.
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402
from saju_engines import event_engine_v2 as E  # noqa: E402
from saju_shared_types.event_taxonomy_v2 import EVENT_FAMILY  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

#: 144명식 스캔으로 선별. 각 명식이 어느 조건을 대표하는지 명시한다.
CHARTS: tuple[dict[str, Any], ...] = (
    {"id": "BOON", "note": "化神 용·희 지배(보강 대운)",
     "date": date(1986, 9, 13), "time": "15:20", "gender": "male"},
    {"id": "PRESSURE", "note": "化神 기·구 지배(압력 대운)",
     "date": date(1979, 12, 27), "time": "21:40", "gender": "female"},
    {"id": "NO_HWA", "note": "합화 불성립 — 음성 대조(보정이 걸리지 않아야 한다)",
     "date": date(2001, 8, 29), "time": "06:05", "gender": "female"},
    {"id": "MIXED", "note": "보강·압력 대운 공존 + 길흉 균형",
     "date": date(1981, 6, 22), "time": "10:10", "gender": "female"},
)

#: 감수 대상 도메인 → event family. `daewoon_hwa` 는 family 를 보지 않으므로,
#: family 점유가 흔들리면 그것은 quality 보정의 **간접** 효과다.
DOMAINS: dict[str, frozenset[str]] = {
    "wealth": frozenset({"wealth_change", "windfall"}),
    "career": frozenset({
        "career_transition", "employment", "advancement", "entrepreneurship",
    }),
    "relation": frozenset({
        "marriage_signal", "new_relationship", "relationship_change",
    }),
}

FAMILY_OF: dict[str, str] = {k: str(v) for k, v in EVENT_FAMILY.items()}
GOOD_Q = frozenset({"opportunity", "achievement", "resolution"})
BAD_Q = frozenset({"loss", "pressure", "conflict"})

#: 시나리오 → `_DAEWOON_HWA_BG` 계수. C 는 B 와 수치가 같아 재계산하지 않는다.
SCENARIOS: tuple[tuple[str, float], ...] = (
    ("A_CURRENT", 0.03),
    ("B_REMOVED", 0.0),
    ("D_ATTENUATED", 0.01),
)

TOP_K = 8

#: 독립 occurrence 근거 접두 — 지시된 5종을 실제 네임스페이스에 맞춰 분류한다.
#:
#: 초판은 `STAGE_`·`PATTERN_` 처럼 존재하지 않는 접두를 넣어 manifestation/stage 가
#: 통째로 빠졌고(실제 표기는 `stage:`), 전체 코드의 26% 만 세고 있었다. 근거 카운트가
#: 임의 부분집합이면 정합 축 자체가 성립하지 않는다.
_OCCURRENCE_PREFIXES: tuple[str, ...] = (
    "REL_",                                     # ① 관계 발동(합충형파해)
    "stage:", "MT1_STAGE_",                     # ② manifestation / stage
    "COMBO_", "TRI_", "SPEC_", "FLOW_", "MIXED_",   # ③ 구조 패턴
    "SINGLE_", "EXAM_", "MARRIAGEFLOW_", "WEALTHACT_",  # ④ 도메인 detector
    "JOBCHANGE_", "MARRIAGE_", "MT1_", "MT2_", "MT3_",
    "CAREER_", "SPOUSE_",
    "VOID_", "DAEWOON_TRANSITION_",             # ⑤ 기간 고유 신호
)

#: occurrence 근거가 **아닌** 것 — 세면 축이 오염된다.
#:
#:   DAEWOON_HWA   감사 대상 자신(스스로를 근거로 세면 순환)
#:   YONGGI/HANSIN/HWA/制  길흉 품질 축 — 사건이 일어난다는 근거가 아니다
#:   REPEAT/SRC/DIFFUSE    중복 감쇠 — 근거가 아니라 근거의 할인
#:   GATE/CONFLICT         억제·선호 충돌
_NON_OCCURRENCE_PREFIXES: tuple[str, ...] = (
    "DAEWOON_HWA", "YONGGI_", "HANSIN_", "HWA_", "制_",
    "REPEAT_", "SRC_", "DIFFUSE_", "GATE_", "CONFLICT_",
)


def _rank_key(c: Any) -> tuple[float, float, float]:
    """production `_CANDIDATE_RANK_KEY` 와 동일 — life_fit > personal_match > score."""
    return (-c.life_fit, -c.personal_match, -c.score)


def _representatives(cands: list[Any], limit: int = TOP_K) -> list[Any]:
    """동일 기간 그룹화 + 동일 대표 선정 계약(production 과 같다)."""
    groups: dict[str, Any] = {}
    for c in sorted(cands, key=_rank_key):
        groups.setdefault(c.period, c)
    return list(groups.values())[:limit]


def _occurrence_evidence(c: Any) -> list[str]:
    """독립 occurrence 근거 코드(품질 축·감쇠·감사 대상 자신은 제외)."""
    return [
        r for r in c.reason_codes
        if r.startswith(_OCCURRENCE_PREFIXES)
        and not r.startswith(_NON_OCCURRENCE_PREFIXES)
    ]


def _unclassified_codes(cands: list[Any]) -> collections.Counter:
    """어느 쪽에도 분류되지 않은 reason code. **0 이 아니면 축이 미완이다.**

    조용히 빠지면 근거 카운트가 임의 부분집합이 되고, 그 위에서 낸 정합 판정은
    측정이 아니라 우연이다. 그래서 세어서 드러낸다.
    """
    out: collections.Counter = collections.Counter()
    for c in cands:
        for r in c.reason_codes:
            if not r.startswith(_OCCURRENCE_PREFIXES) and not r.startswith(
                _NON_OCCURRENCE_PREFIXES
            ):
                out[r] += 1
    return out


def _quality_axis(c: Any) -> str:
    q = c.quality.value if c.quality else "none"
    return "good" if q in GOOD_Q else "bad" if q in BAD_Q else "other"


def _score_chart(chart: dict[str, Any], bg: float) -> list[Any]:
    """한 명식을 주어진 배경 계수로 채점한다. 계수 외 모든 계산은 동일하다."""
    original = E._DAEWOON_HWA_BG
    E._DAEWOON_HWA_BG = bg
    try:
        birth = R.BirthInput(
            calendar_type="solar", birth_date=chart["date"], birth_time=chart["time"],
            birth_place_name="서울", gender=chart["gender"],
        )
        spec = ReportSpec(
            product_code="RPT_FOCUS",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
        )
        data = R._ReportData(birth, spec, date(2026, 7, 30))
        return list(data.scorer.score(data.result))
    finally:
        E._DAEWOON_HWA_BG = original


def _domain_pool(cands: list[Any], families: frozenset[str]) -> list[Any]:
    return [c for c in cands if FAMILY_OF.get(str(c.event_key), "") in families]


def _identity(c: Any) -> tuple[str, str]:
    """후보 동일성 — 같은 시점·같은 사건이면 같은 후보로 본다."""
    return (c.period, str(c.event_key))


def _rank_positions(pool: list[Any]) -> dict[tuple[str, str], int]:
    """대표 후보의 전체 순위(순위 이동 거리 측정용)."""
    return {
        _identity(c): i
        for i, c in enumerate(sorted(pool, key=_rank_key))
    }


def _measure_domain(
    base_pool: list[Any], alt_pool: list[Any]
) -> dict[str, Any]:
    """축 1~3 을 한 도메인에서 측정한다. 규범 판정은 넣지 않는다."""
    base_rep, alt_rep = _representatives(base_pool), _representatives(alt_pool)
    base_ids = [_identity(c) for c in base_rep]
    alt_ids = [_identity(c) for c in alt_rep]
    base_pos, alt_pos = _rank_positions(base_pool), _rank_positions(alt_pool)

    # ── 축 1: 대표 순위 영향 ──────────────────────────────────────────
    dropped = [i for i in base_ids if i not in alt_ids]
    added = [i for i in alt_ids if i not in base_ids]
    base_periods, alt_periods = {p for p, _ in base_ids}, {p for p, _ in alt_ids}
    moves = [
        abs(alt_pos[i] - base_pos[i])
        for i in base_ids if i in alt_pos and i in base_pos
    ]
    # 탈락 사유 — 그룹에서 밀렸는가(같은 시점의 다른 사건이 대표가 됨), 아니면
    # 시점 자체가 Top-K 밖으로 나갔는가. 둘은 의미가 다르다.
    dropped_reason: collections.Counter = collections.Counter()
    for period, _key in dropped:
        if period in alt_periods:
            dropped_reason["LOST_WITHIN_PERIOD"] += 1
        else:
            dropped_reason["PERIOD_LEFT_TOPK"] += 1

    def q_share(reps: list[Any]) -> dict[str, int]:
        return dict(collections.Counter(_quality_axis(c) for c in reps))

    # ── 축 2: 사건 종류 영향 ──────────────────────────────────────────
    def fam_share(reps: list[Any]) -> dict[str, int]:
        return dict(collections.Counter(
            FAMILY_OF.get(str(c.event_key), "?") for c in reps
        ))

    def key_repeat(reps: list[Any]) -> int:
        cnt = collections.Counter(str(c.event_key) for c in reps)
        return max(cnt.values()) if cnt else 0

    # ── 축 3: 후보는 그대로인데 quality 만 바뀌는가 ────────────────────
    base_q = {_identity(c): _quality_axis(c) for c in base_rep}
    alt_q = {_identity(c): _quality_axis(c) for c in alt_rep}
    quality_only = [i for i in base_ids if i in alt_q and base_q[i] != alt_q[i]]

    # ── 독립 occurrence 근거 정합 ─────────────────────────────────────
    alt_by_id = {_identity(c): c for c in alt_rep}
    base_by_id = {_identity(c): c for c in base_rep}
    alignment: list[dict[str, Any]] = []
    for i in added:
        entrant = alt_by_id[i]
        # **같은 시점에서 맞붙은 경우에만** 짝을 짓는다. 시점이 다른 후보를 임의로
        # 짝지으면 경쟁하지 않은 둘의 근거를 비교하게 되고, 정합 집계 전체가 무의미해진다.
        # 상대가 없으면 그 시점 자체가 Top-K 에 새로 들어온 것이며 맞대결이 아니다.
        ousted = next((base_by_id[b] for b in dropped if b[0] == i[0]), None)
        alignment.append({
            "comparison": "HEAD_TO_HEAD" if ousted is not None else "PERIOD_ENTRY",
            "entrant": {
                "period": i[0], "event": i[1],
                "quality": entrant.quality.value if entrant.quality else None,
                "score": entrant.score,
                "occurrence_evidence": len(_occurrence_evidence(entrant)),
            },
            "ousted": None if ousted is None else {
                "period": ousted.period, "event": str(ousted.event_key),
                "quality": ousted.quality.value if ousted.quality else None,
                "score": ousted.score,
                "occurrence_evidence": len(_occurrence_evidence(ousted)),
            },
        })

    return {
        "rank_effect": {
            "representatives_changed": len(dropped),
            # 진입·이탈 시점을 합쳐 반으로 나누면 둘이 비대칭일 때 값이 왜곡된다.
            "period_entered": len(alt_periods - base_periods),
            "period_left": len(base_periods - alt_periods),
            "rank_move_max": max(moves) if moves else 0,
            "rank_move_mean": round(sum(moves) / len(moves), 2) if moves else 0.0,
            "dropped_reason": dict(dropped_reason),
            "quality_share_base": q_share(base_rep),
            "quality_share_alt": q_share(alt_rep),
        },
        "family_effect": {
            "unique_families_base": len(fam_share(base_rep)),
            "unique_families_alt": len(fam_share(alt_rep)),
            "family_share_base": fam_share(base_rep),
            "family_share_alt": fam_share(alt_rep),
            "max_key_repeat_base": key_repeat(base_rep),
            "max_key_repeat_alt": key_repeat(alt_rep),
            "period_diversity_base": len(base_periods),
            "period_diversity_alt": len(alt_periods),
        },
        "quality_only_changes": len(quality_only),
        "occurrence_alignment": alignment,
        "pool_size": len(base_pool),
    }


def run() -> dict[str, Any]:
    """명식 4종 × 도메인 3종 × 시나리오 3종을 측정한다."""
    print("DAEWOON_HWA_CROSS_DOMAIN_AUDIT_STARTED")
    print(f"명식 {len(CHARTS)}종 × 도메인 {len(DOMAINS)}종 × 시나리오 "
          f"{len(SCENARIOS)}종(C 는 B 와 수치 동일 — 재계산 없음)\n")

    report: dict[str, Any] = {"charts": {}, "scope_limit": (
        "설계 감수 근거이며 전체 명식 일반화 통계가 아니다. 명식 4종은 조건을 "
        "만족하도록 144명식 스캔에서 의도적으로 선별됐다."
    )}

    for chart in CHARTS:
        cid = chart["id"]
        scored = {name: _score_chart(chart, bg) for name, bg in SCENARIOS}
        # 음성 대조 검증 — 합화가 없으면 시나리오 간 점수가 완전히 같아야 한다.
        a_scores = {(_identity(c)): c.score for c in scored["A_CURRENT"]}
        b_scores = {(_identity(c)): c.score for c in scored["B_REMOVED"]}
        identical = a_scores == b_scores

        entry: dict[str, Any] = {
            "note": chart["note"],
            "birth": f"{chart['date']} {chart['time']} {chart['gender']}",
            "a_equals_b": identical,
            "domains": {},
        }
        unclassified = _unclassified_codes(scored["A_CURRENT"])
        entry["unclassified_reason_codes"] = dict(unclassified.most_common(10))
        print(f"── {cid}  {chart['note']}")
        print(f"   {entry['birth']}   A==B(점수 전건 동일): {identical}   "
              f"미분류 코드: {sum(unclassified.values())}종류 {len(unclassified)}")

        for dname, families in DOMAINS.items():
            base_pool = _domain_pool(scored["A_CURRENT"], families)
            dom: dict[str, Any] = {}
            for alt_name in ("B_REMOVED", "D_ATTENUATED"):
                alt_pool = _domain_pool(scored[alt_name], families)
                dom[alt_name] = _measure_domain(base_pool, alt_pool)
            entry["domains"][dname] = dom

            b, d = dom["B_REMOVED"], dom["D_ATTENUATED"]
            print(f"   {dname:<9} pool={b['pool_size']:>4}  "
                  f"대표교체 B={b['rank_effect']['representatives_changed']} "
                  f"D={d['rank_effect']['representatives_changed']}  "
                  f"family수 A={b['family_effect']['unique_families_base']} "
                  f"B={b['family_effect']['unique_families_alt']} "
                  f"D={d['family_effect']['unique_families_alt']}  "
                  f"quality만변경 B={b['quality_only_changes']}")
            print(f"   {'':<9} quality점유 A={b['rank_effect']['quality_share_base']} "
                  f"B={b['rank_effect']['quality_share_alt']} "
                  f"D={d['rank_effect']['quality_share_alt']}")
        report["charts"][cid] = entry
        print()

    print("RANK_EFFECT_MEASURED")
    print("EVENT_FAMILY_EFFECT_MEASURED")
    print("QUALITY_SHARE_EFFECT_MEASURED")
    print("OCCURRENCE_EVIDENCE_ALIGNMENT_MEASURED")
    print("DESIGN_JUDGMENT_PENDING")
    print("PRODUCTION_UNCHANGED")
    return report


if __name__ == "__main__":
    out = run()
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if dest is not None:
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n상세 기록: {dest}")
