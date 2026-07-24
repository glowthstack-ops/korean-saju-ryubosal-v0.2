"""사례 22 — candidate-linked legacy 3종 실측 (C1 2027 丁未: P0-A S2 시나리오 재사용).

event_adjusted_legacy_strength = 실제 legacy 산식(likely ×1.2 포함) cap 이전 합.
legacy_delta = cap 적용 후 실제 기여(contributions['relation']). MT4는 shadow —
actual 값에 혼입하지 않는다(별도 필드 소관). SAMPLES.md에 추가 기록.
"""
from __future__ import annotations

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
from saju_engines.relation_palace_engine import RelationPalaceEngine
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import LuckLayer, Pillar4
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT = Path(__file__).resolve().parent / "SAMPLES.md"
REL_KEYS = {"relationship_change", "marriage_signal", "new_relationship"}


class _Noop:
    def apply(self, candidates, activations, **kwargs):
        return candidates


def main() -> None:
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="서울", gender="female", reference_date=date(2026, 7, 24)))
    base_eng = EventEngineV2(_DICTS, **marriage_engine_flags())
    ctrl_eng = EventEngineV2(_DICTS, **marriage_engine_flags())
    ctrl_eng._relpalace = _Noop()  # type: ignore[assignment]

    base = base_eng.score_years(chart, [2027])
    ctrl = ctrl_eng.score_years(chart, [2027])

    def rank_of(cands, key):
        ordered = sorted(cands, key=lambda c: -c.score)
        for i, c in enumerate(ordered, 1):
            if str(c.event_key) == key:
                return i, c
        return None, None

    # 활성 재현(엔진 내부와 동일 — P0-A 하네스 방식) — 2027 세운 丁未.
    idx = _StackIndex(chart)
    pil = idx.sewoon_by_year[2027]
    hits_raw = base_eng._relation_hits(chart, GanjiLevel.YEAR, pil)
    acts = (_activations(hits_raw, LuckLayer.SEWOON)
            + _bokeum_activations(chart, pil, LuckLayer.SEWOON))
    day_acts = [a for a in acts if a.palace is Pillar4.DAY]

    # legacy 산식 재현(likely ×1.2 포함, cap 이전) — marriage_signal 기준.
    rp = RelationPalaceEngine(_DICTS)
    rel_palace_events: dict[tuple[str, str], set[str]] = {}
    for r in rp._rel_to_palace:
        rel_palace_events.setdefault(
            (r["relation"], r["target_palace"]), set()).update(r["likely_events"])

    def precap(event_key: str) -> float:
        total = 0.0
        for a in acts:
            pinfo = rp._palace[a.palace.value]
            in_domain = event_key in pinfo["event_domains"]
            likely = event_key in rel_palace_events.get(
                (a.kind.value, a.palace.value), set())
            if not (in_domain or likely):
                continue
            b = rp._rel_bonus[a.kind.value] * float(pinfo["activation_weight"])
            b *= rp._layer_w.get(f"{a.layer.value}_to_natal", 1.0)
            b *= rp._palace_mult[a.palace.value][a.position]
            if likely:
                b *= 1.2
            total += b
        return total

    lines = ["", "## 사례 22 — candidate-linked (C1 여성 1985-03-15, 2027 丁未 세운)", "",
             "| 이벤트 | legacy score(ctrl→base) | conf | rank(ctrl→base) | "
             "event_adjusted(pre-cap) | legacy_delta | capped |",
             "|---|---|---|---|--:|--:|---|"]
    for key in sorted(REL_KEYS):
        rb, cb = rank_of(base, key)
        rc, cc = rank_of(ctrl, key)
        if cb is None:
            lines.append(f"| {key} | 후보 없음(candidate_absent) | — | — | — | — | — |")
            continue
        pre = precap(key)
        capped = pre > 22.0
        lines.append(
            f"| {key} | {cc.score if cc else '—'}→{cb.score} | {cb.confidence_level.value} "
            f"| {rc}→{rb} | {round(pre, 1)} | {min(round(pre, 1), 22.0)} | {capped} |")

    # 같은 활성의 어댑터 벡터(EXACT 주입 — 운 지지 未) 병기.
    hits = [SpousePalaceHit(
        kind=a.kind, palace=a.palace, layer=a.layer.value, position=a.position,
        hap_subtype=a.hap_subtype, element=a.element,
        transit_component="branch", transit_participant="未",
    ) for a in day_acts]
    vec = build_spouse_palace_vector(hits, _DICTS, period_key="2027")
    lines += ["",
              f"어댑터 벡터(동일 활성·EXACT): activation={vec.vector.activation.value}"
              f"({vec.vector.activation.band}) / stability net={vec.vector.stability.value}"
              f"(sup {vec.stability_support}/prs {vec.stability_pressure}) / "
              f"separation={vec.vector.separation_pressure.value}"
              f"({vec.vector.separation_pressure.band}) / evidence {vec.evidence_count}·"
              f"root {vec.root_trigger_count} — base 합={vec.base_activation_total}"
              f"(이벤트 무관 — 위 pre-cap과 의미 분리)",
              "",
              "shadow 전후 legacy score/confidence/rank: **완전 동일**(벡터는 별도 산출 —"
              " 엔진 미개입).", ""]
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("case22 appended")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
