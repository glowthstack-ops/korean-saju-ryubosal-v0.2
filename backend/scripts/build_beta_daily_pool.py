"""`beta-daily-pool.c10.v1` — 테스터 공개용 불변 snapshot 생성.

원장·CAS 없이도 테스터에게 지금의 완성 후보 풀을 제시할 수 있다. canonical bootstrap
으로 C10 을 안정 상태로 만든 뒤 공개 기간 30일을 선생성해 **불변 snapshot** 으로 고정
한다. 서버를 계속 켜 두며 history 를 쌓을 필요가 없고, 재기동해도 같은 snapshot 을
읽으면 결과가 유지된다.

    bootstrap   2026-01-31 ~ 2026-07-29   상태 계산 전용(비공개)
    public      2026-07-30 ~ 2026-08-28   테스터 공개(날짜별로만)

계약을 동결한다 — 승인 대기 패치를 섞지 않는다. 그래야 피드백이 정확히 C10 풀을
대상으로 한 것인지 알 수 있다.

    display policy  display-selection.p4-lc.c10.v1
    slot contract   현행 유지 (5종 slot 확장 없음)
    taxonomy        현행 · G0 비활성 · DICT_VERSION 현행 · family_talk 수정 없음

**선생성과 미래 노출은 다른 문제다.** snapshot 은 30일을 담지만, 조회는
`beta_daily_pool.load_day()` 가 KST 날짜로 막는다.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count  # noqa: E402
from saju_engines.daily_canonical_bootstrap import (  # noqa: E402
    BOOTSTRAP_CONTRACT_VERSION,
    C10_POLICY,
    canonical_history,
    generate_bootstrap,
    make_plan,
    verify_lookback_length,
)
from saju_engines.daily_selection_contracts import (  # noqa: E402
    DISPLAY_SELECTION_POLICY_C10_V1,
    HISTORY_CONTRACT_VERSION,
    engine_input_fingerprint,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    SelectionPolicy,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.daily_fortune import active_dict_version, content_version_for  # noqa: E402

POOL_VERSION = "beta-daily-pool.c10.v1"
ANCHOR = dt.date(2026, 7, 30)
PUBLIC_DAYS = 30
TAXONOMY_VERSION = "taxonomy.v1"

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7
_BAND_NAMES = {4: "s5", 3: "s4", 2: "s3", 1: "s2"}
_OUT = _BACKEND / "compiled" / f"{POOL_VERSION}.json"


def _sha(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def build() -> dict[str, Any]:
    """bootstrap → 공개 30일 선생성. 같은 입력이면 지문까지 동일해야 한다."""
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    plan = make_plan(ANCHOR)
    boot = generate_bootstrap(plan, family_of)
    verify_lookback_length(plan, boot)
    bootstrap_fp = _sha([
        f"{r.fortune_date.isoformat()}|{r.ilju}|{r.final_headline}" for r in boot
    ])

    headline_history: dict[str, list[str]] = {
        k: list(v) for k, v in canonical_history(boot).items()
    }
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    for r in sorted(boot, key=lambda x: (x.fortune_date, x.ilju)):
        if r.is_canonical_history:
            good_history[r.ilju].append(r.display_good_representative)

    days: list[dict[str, Any]] = []
    for i in range(PUBLIC_DAYS):
        day = ANCHOR + dt.timedelta(days=i)
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        card: dict[str, dict[str, Any]] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            rep = select_good_representative(
                goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=headline_history.get(ilju, []),
            )
            good, caution, support = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(good, support, caution, M._band(good, caution))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            card[ilju] = {
                "ilju": ilju,
                "raw_good_winner": rep.raw_good_winner,
                "display_good_representative": rep.display_good_representative,
                "display_good_probability": rep.display_good_probability,
                "display_good_band": _BAND_NAMES[
                    strength_band(rep.display_good_probability)
                ],
                "display_good_semantic_family": family_of.get(
                    rep.display_good_representative, ""
                ),
                "support_event": support.event_key,
                "caution_event": caution.event_key,
                "band": M._band(good, caution),
                "good_selection_reason": rep.good_selection_reason,
                "display_displacement_loss": rep.display_displacement_loss,
            }
            good_history[ilju].append(rep.display_good_representative)

        result = select_board(
            raw, cmap, headline_history, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        for ilju, sel in result.selections.items():
            card[ilju]["final_headline"] = sel.event_key
            card[ilju]["final_headline_semantic_family"] = family_of.get(sel.event_key, "")
            card[ilju]["final_headline_domain"] = sel.domain
            headline_history.setdefault(ilju, []).append(sel.event_key)
        days.append({
            "fortune_date": day.isoformat(),
            "active_dict_version": active_dict_version(day),
            "content_version": content_version_for(day),
            "authorized_domain_overrides": result.domain_cap_authorized_override,
            "domain_cap_hard_violation": result.domain_cap_hard_violation,
            "cards": [card[f"{s.value}{b.value}"]
                      for s, b in (ganzi_from_index(i) for i in range(60))],
        })

    pool_fp = _sha([
        f"{d['fortune_date']}|{c['ilju']}|{c['final_headline']}"
        f"|{c['display_good_representative']}|{c['support_event']}|{c['caution_event']}"
        for d in days for c in d["cards"]
    ])
    engine_fp = engine_input_fingerprint(
        fortune_date=ANCHOR,
        active_dict_version=active_dict_version(ANCHOR),
        content_version=content_version_for(ANCHOR),
        event_selection_contract=M.EVENT_SELECTION_COMPAT_SALT,
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
        taxonomy_version=TAXONOMY_VERSION,
        board_rebalance_version=M.SELECTOR_VERSION,
        history_lookback_days=LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    )
    return {
        "pool_version": POOL_VERSION,
        "anchor_date": ANCHOR.isoformat(),
        "public_start": ANCHOR.isoformat(),
        "public_end": (ANCHOR + dt.timedelta(days=PUBLIC_DAYS - 1)).isoformat(),
        "public_days": PUBLIC_DAYS,
        "bootstrap_contract_version": BOOTSTRAP_CONTRACT_VERSION,
        "bootstrap_start": plan.start_date.isoformat(),
        "bootstrap_end": plan.end_date.isoformat(),
        "bootstrap_warmup_days": plan.warmup_days,
        "history_lookback_days": plan.lookback_days,
        "history_contract_version": HISTORY_CONTRACT_VERSION,
        "display_selection_policy_version": DISPLAY_SELECTION_POLICY_C10_V1,
        "dict_version": active_dict_version(ANCHOR),
        "taxonomy_version": TAXONOMY_VERSION,
        "content_version": content_version_for(ANCHOR),
        "event_selection_contract": M.EVENT_SELECTION_COMPAT_SALT,
        "board_rebalance_version": M.SELECTOR_VERSION,
        "g0_enabled": False,
        "engine_input_fingerprint": engine_fp,
        "bootstrap_fingerprint": bootstrap_fp,
        "pool_result_fingerprint": pool_fp,
        "publishable_per_date_only": True,
        "days": days,
    }


if __name__ == "__main__":
    a = build()
    b = build()
    same = (
        a["pool_result_fingerprint"] == b["pool_result_fingerprint"]
        and a["bootstrap_fingerprint"] == b["bootstrap_fingerprint"]
    )
    if not same:
        print("[fail] 결정론 위반 — 지문이 다르다. 공개하지 않는다.")
        raise SystemExit(1)
    # `generated_at` 은 지문 계산 뒤에 찍는다(지문에 시각이 섞이면 재현이 깨진다).
    a["generated_at"] = dt.datetime.now(dt.UTC).isoformat()
    _OUT.write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", _OUT.name)
    print(f"  bootstrap {a['bootstrap_start']} ~ {a['bootstrap_end']} "
          f"(warm-up {a['bootstrap_warmup_days']} + lookback {a['history_lookback_days']})")
    print(f"  공개 {a['public_start']} ~ {a['public_end']} ({a['public_days']}일 · "
          f"{a['public_days'] * 60} 카드)")
    print(f"  bootstrap_fp {a['bootstrap_fingerprint'][:16]}… "
          f"pool_fp {a['pool_result_fingerprint'][:16]}…")
    print("  결정론 2회 생성 일치: True")
    fam = {c["final_headline_semantic_family"] for d in a["days"] for c in d["cards"]}
    dom = collections.Counter(c["final_headline_domain"] for d in a["days"] for c in d["cards"])
    print(f"  공개 기간 고유 family {len(fam)} · 도메인 {dict(dom.most_common())}")
    print(f"  authorized override 합계 "
          f"{sum(d['authorized_domain_overrides'] for d in a['days'])} · "
          f"hard violation {sum(d['domain_cap_hard_violation'] for d in a['days'])}")
