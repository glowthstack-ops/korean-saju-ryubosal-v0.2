"""직장 이력 leave-one-out 적중 측정 — EMPLOYMENT_HISTORY_CALIBRATION.md §3-3.

원장의 `employment_history` 입사(job_gain) 행 가운데 취업 통계 성격(정규·파견)만 골라, 한 건을 빼고
나머지로 개인 시그니처를 만든 뒤 그 절기년 12개월 후보를 LifeFitRanker 로 정렬해 실제 입사월이
job_gain 후보 Top-3 안에 드는 비율을 센다. 세 모드를 같은 절차로 비교한다.
- engine: 개인 시그니처 없음(엔진만)
- base:   시그니처 + 글자 가중 0(현재 운영값 — 근거 코드만)
- glyph:  시그니처 + 사전 glyph_weight(플래그 ON 상태와 동일)
- glyph_cap: glyph + 반복 가중 상한(--repeat-cap, 기본 0.6) — 현재 운영값
- dw_glyph:  glyph_cap + 대운 두 칸을 자리 가중에 추가(측정용 가중)
- dw_cond:   glyph_cap + 대운이 다른 과거 행의 유사도 ×0.5(판도가 바뀌면 덜 옮긴다)
- struct:    glyph_cap + 운 구조 태그 유사도 가중 0.25(역할·원국 대비 위치·구조 계열)
- dw_struct: dw_cond + struct
- dw_cond_job / dw_struct_job: 위 두 변형에서 '다른 대운 ×0.5'를 취업(job_gain) 키에만 건다 —
  모든 키에 걸면 과거 행이 적은 다른 사건이 깎여 취업이 1순위인 달이 넓게 늘어나기 때문이다.
대운·구조 변형은 2026-11-18 역할별 재분석(§7)의 측정용이다. 지문 확장은 측정 안에서만 켜고
(GlyphContext extended), 원장 행도 메모리에서 다시 찍는다 — DB·운영 사전은 바꾸지 않는다.
판정은 하지 않는다 — 수치만 내고 ON/OFF 는 데굴님이 정한다(점수 규칙은 실사례 적중률로
ON/OFF). 우연 기준선 = 3/12 = 25%.

오탐은 두 가지로 낸다(2026-11-18 데굴님 "재직 기간 중이라면 추가 취업이 발생하지 않아도 사용자
의지가 없었으니 오탐이라고 볼 수 없다 — 그런 시기가 왔다 갔을 뿐").
- 종전: 설문 not_happened(job_gain) 해의 12달 전부(재직 중인 달 포함) — 비교용으로만 남긴다.
- 재직 상태 구분: 이력의 입사~퇴사 구간으로 달을 나눠 ①재직 중(평가 제외) ②공백 중 입사 직전
  창(입사 달의 전월·전전월 — 적중 쪽) ③그 밖의 공백 달(오탐 후보)로 센다. 오탐률 분모는 ③뿐이다.
- 구직 달 변별(2026-11-18 데굴님 "구직중이었어. 취업이 안되었을 뿐"): 공백 달 전체가 구직 달로
  확인됐으므로 ②와 ③을 같은 저울에 올린다. ②는 그 창이 가리키는 입사 행을 **빼고** 다시 센다
  (전체 시그니처로 세면 그 입사 행의 글자가 직전 달에 그대로 겹쳐 적중이 부풀려진다). ③에는
  입사 행이 없으므로 전체 시그니처 그대로가 운영과 같은 조건이다.

사용법:
    python scripts/measure_employment_history_loo.py --subject <subject_id> \\
        [--json 경로] [--md 경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에 회사명(label)이 사용자 제공 그대로 찍힌다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from saju_api.services.manse_service import calculate
from saju_engines.employment_history import EMPLOYMENT_STAT_NATURES, reference_date_for_label
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.glyph_context import GlyphContext
from saju_engines.life_event_store import LifeEventStore
from saju_engines.life_fit_ranker import LifeFitRanker
from saju_engines.personal_calibration import _GLYPH_CFG
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import LifeEventOutcome, LifeEventRow, LifeEventSource

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_TOP_N = 3
_MODES = (
    "engine", "base", "glyph", "glyph_cap", "dw_glyph", "dw_cond", "struct", "dw_struct",
    "dw_cond_job", "dw_struct_job",
)
#: 확장 지문(대운 글자·구조 태그)을 쓰는 변형.
_EXT_MODES = frozenset({
    "dw_glyph", "dw_cond", "struct", "dw_struct", "dw_cond_job", "dw_struct_job",
})
#: 다른 대운 배수를 취업 키에만 거는 변형 — 근거가 측정된 키(입사 이력)로 한정한다.
_JOB_ONLY_MODES = frozenset({"dw_cond_job", "dw_struct_job"})
_JOB_KEYS = ["job_gain"]
_DW_POSITION_WEIGHTS = {
    "wolwoon_branch": 0.3, "wolwoon_stem": 0.15, "sewoon_branch": 0.15, "sewoon_stem": 0.15,
    "daewoon_branch": 0.15, "daewoon_stem": 0.1,
}
_OTHER_DAEWOON_FACTOR = 0.5
_STRUCTURE_WEIGHT = 0.25


def _variant_cfg(mode: str) -> dict[str, Any] | None:
    """변형별 글자 설정 덮어쓰기(None=운영 사전 그대로)."""
    if mode not in _EXT_MODES:
        return None
    cfg: dict[str, Any] = dict(_GLYPH_CFG)
    if mode == "dw_glyph":
        cfg["position_weights"] = _DW_POSITION_WEIGHTS
    if mode in ("dw_cond", "dw_struct") or mode in _JOB_ONLY_MODES:
        cfg["other_daewoon_factor"] = _OTHER_DAEWOON_FACTOR
    if mode in _JOB_ONLY_MODES:
        cfg["other_daewoon_event_keys"] = _JOB_KEYS
    if mode in ("struct", "dw_struct", "dw_struct_job"):
        cfg["structure_weight"] = _STRUCTURE_WEIGHT
    return cfg


class _ExtendedStamper:
    """확장 지문(대운·구조)용 컨텍스트 캐시 — 라벨의 기준일별 만세력 1회 계산."""

    def __init__(self, birth: Any) -> None:
        self._birth = birth
        self._ctx: dict[date, GlyphContext] = {}

    def ctx_for(self, ref: date) -> GlyphContext:
        """기준일의 확장 컨텍스트(캐시)."""
        if ref not in self._ctx:
            chart = calculate(self._birth.model_copy(update={"reference_date": ref}))
            self._ctx[ref] = GlyphContext.from_result(chart, extended=True)
        return self._ctx[ref]

    def restamp(self, rows: list[LifeEventRow]) -> list[LifeEventRow]:
        """원장 행 지문을 확장 차원으로 다시 찍은 복사본(메모리 전용)."""
        out: list[LifeEventRow] = []
        for r in rows:
            try:
                ref = (
                    reference_date_for_label(r.period) if len(r.period) >= 7
                    else date(int(r.period[:4]), 7, 1)
                )
            except ValueError:
                out.append(r)
                continue
            fp = self.ctx_for(ref).with_glyphs(r.signal_fingerprint, r.period)
            out.append(r.model_copy(update={"signal_fingerprint": fp}))
        return out


def _load_env() -> None:
    """루트 .env → 환경 변수(이미 설정된 키는 유지)."""
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


@dataclass
class HeldOut:
    """한 건을 뺀 측정 결과."""

    period: str
    label: str
    rank: dict[str, int | None]   # 모드별 실제 월의 순위(1부터, 없으면 None)
    top3: dict[str, list[str]]    # 모드별 Top-3 기간


def _rank_of(ranked: list, period: str) -> tuple[int | None, list[str]]:
    jobs = [c for c in ranked if str(c.event_key) == "job_gain"]
    periods = [c.period for c in jobs]
    rank = periods.index(period) + 1 if period in periods else None
    return rank, periods[:_TOP_N]


def measure(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, repeat_cap: float = 0.6,
) -> list[HeldOut]:
    """정규·파견 입사 행 leave-one-out — 모드별 순위·Top-3."""
    entries = [
        r for r in signature
        if r.event_key == "job_gain" and r.source is LifeEventSource.EMPLOYMENT_HISTORY
        and r.outcome is LifeEventOutcome.CONFIRMED
        and r.attrs.nature in EMPLOYMENT_STAT_NATURES and len(r.period) >= 7
    ]
    out: list[HeldOut] = []
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    stamper = _ExtendedStamper(birth)
    ext_signature = stamper.restamp(signature)
    for held in entries:
        rest = [r for r in signature if r.event_row_id != held.event_row_id]
        ext_rest = [r for r in ext_signature if r.event_row_id != held.event_row_id]
        ref = reference_date_for_label(held.period)
        chart = calculate(birth.model_copy(update={"reference_date": ref}))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        ranks: dict[str, int | None] = {}
        tops: dict[str, list[str]] = {}
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            elif mode in _EXT_MODES:
                ranked = LifeFitRanker().rank(
                    cands, signature=ext_rest, glyph_context=stamper.ctx_for(ref),
                    glyph_weight=glyph_w, repeat_cap=repeat_cap, glyph_cfg=_variant_cfg(mode),
                )
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=rest, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            ranks[mode], tops[mode] = _rank_of(ranked, held.period)
        out.append(HeldOut(
            period=held.period, label=held.attrs.label or "", rank=ranks, top3=tops,
        ))
    return out


@dataclass
class FalsePositiveYear:
    """사건이 없던 해(캘리브레이션 not_happened) — 모드별 job_gain 이 월 Top-1 인 달 수."""

    year: int
    top1_months: dict[str, int]


def measure_false_positive(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, repeat_cap: float = 0.6,
) -> list[FalsePositiveYear]:
    """not_happened(job_gain, 연 단위) 해의 12개월에서 job_gain 이 그 달 Top-1 후보인 달 수.

    무상한 반복 가중이 '사건 없는 달'에도 job_gain 을 1위로 올리는 편향(오탐)을 잰다. 시그니처는
    운영과 같은 전체(그 해 not_happened 행 포함 — 운영도 그 행을 보므로).
    """
    years = sorted({
        int(r.period) for r in signature
        if r.event_key == "job_gain" and r.outcome is LifeEventOutcome.NOT_HAPPENED
        and len(r.period) == 4
    })
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    out: list[FalsePositiveYear] = []
    stamper = _ExtendedStamper(birth)
    ext_signature = stamper.restamp(signature)
    for y in years:
        chart = calculate(birth.model_copy(update={"reference_date": date(y, 7, 1)}))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        counts: dict[str, int] = {}
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            elif mode in _EXT_MODES:
                ranked = LifeFitRanker().rank(
                    cands, signature=ext_signature, glyph_context=stamper.ctx_for(date(y, 7, 1)),
                    glyph_weight=glyph_w, repeat_cap=repeat_cap, glyph_cfg=_variant_cfg(mode),
                )
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=signature, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            top_by_period: dict[str, str] = {}
            for c in ranked:
                top_by_period.setdefault(c.period, str(c.event_key))
            counts[mode] = sum(1 for k in top_by_period.values() if k == "job_gain")
        out.append(FalsePositiveYear(year=y, top1_months=counts))
    return out


def render_fp_md(rows: list[FalsePositiveYear]) -> str:
    """오탐 표 — 모드별 (job_gain Top-1 달 수 / 12×해 수)."""
    if not rows:
        return "오탐 측정: not_happened(job_gain) 연도 없음."
    total = 12 * len(rows)
    lines = [f"오탐(사건 없던 해 {len(rows)}년 × 12달 = {total}달 중 job_gain Top-1 달 수)",
             "| 모드 | Top-1 달 수 | 비율 |", "|---|---|---|"]
    for mode in _MODES:
        n = sum(r.top1_months[mode] for r in rows)
        lines.append(f"| {mode} | {n} | {round(n / total, 3)} |")
    lines.append("")
    lines.append("| 해 | " + " | ".join(_MODES) + " |")
    lines.append("|---|" + "---|" * len(_MODES))
    for r in rows:
        lines.append(f"| {r.year} | " + " | ".join(str(r.top1_months[m]) for m in _MODES) + " |")
    return "\n".join(lines)


#: 입사 직전 창(달) — 입사 달의 전월·전전월은 '기회가 온 달'로 적중 쪽에 둔다(§1 리드타임 1~2개월).
_LEAD_MONTHS = 2
STATUS_EMPLOYED = "employed"        # 재직·복무 중 — 평가 제외(시기가 왔다 갔을 뿐)
STATUS_PRE_ENTRY = "gap_pre_entry"  # 공백 중 입사 직전 창 — 적중 쪽
STATUS_GAP = "gap_other"            # 그 밖의 공백 달 — 오탐 후보
_STATUS_KO = {
    STATUS_EMPLOYED: "재직 중(평가 제외)", STATUS_PRE_ENTRY: "공백·입사 직전 창(적중 쪽)",
    STATUS_GAP: "공백·그 밖(오탐 후보)",
}


def _label_index(label: str) -> int:
    """'YYYY-MM' 절기월 라벨 → 연속 달 번호."""
    return int(label[:4]) * 12 + int(label[5:7]) - 1


def _index_label(index: int) -> str:
    """연속 달 번호 → 'YYYY-MM'."""
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def employment_intervals(
    signature: list[LifeEventRow], until: str,
) -> list[tuple[int, int, bool]]:
    """이력의 직장 묶음별 (입사 달, 퇴사 달, 취업 통계 성격 여부) — 달 번호, 양끝 포함.

    묶음 키는 `attrs.employment_group`(없으면 행마다 따로). 퇴사 행이 없는 묶음은 `until`(측정
    끝 달)까지 재직으로 본다. 군 복무·인턴 구간도 '자리가 차 있던 달'이라 구간에 넣되, 입사 직전
    창은 취업 통계 성격(정규·파견) 입사에만 붙인다.
    """
    groups: dict[str, dict[str, Any]] = {}
    for r in signature:
        if r.source is not LifeEventSource.EMPLOYMENT_HISTORY or len(r.period) < 7:
            continue
        if r.outcome is not LifeEventOutcome.CONFIRMED:
            continue
        key = r.attrs.employment_group or r.event_row_id
        g = groups.setdefault(key, {"start": None, "end": None, "stat": False})
        idx = _label_index(r.period)
        if r.event_key == "job_gain":
            g["start"] = idx if g["start"] is None else min(g["start"], idx)
            g["stat"] = g["stat"] or r.attrs.nature in EMPLOYMENT_STAT_NATURES
        elif r.event_key == "resignation":
            g["end"] = idx if g["end"] is None else max(g["end"], idx)
    out: list[tuple[int, int, bool]] = []
    for g in groups.values():
        if g["start"] is None:
            continue
        end = g["end"] if g["end"] is not None else _label_index(until)
        out.append((g["start"], max(end, g["start"]), bool(g["stat"])))
    return sorted(out)


def month_status(intervals: list[tuple[int, int, bool]], until: str) -> dict[str, str]:
    """첫 입사 달 ~ `until` 의 달별 상태(재직 중 / 입사 직전 창 / 그 밖의 공백)."""
    if not intervals:
        return {}
    employed = {i for start, end, _ in intervals for i in range(start, end + 1)}
    pre_entry = {
        start - k for start, _, stat in intervals if stat for k in range(1, _LEAD_MONTHS + 1)
    }
    status: dict[str, str] = {}
    for i in range(intervals[0][0], _label_index(until) + 1):
        if i in employed:
            status[_index_label(i)] = STATUS_EMPLOYED
        elif i in pre_entry:
            status[_index_label(i)] = STATUS_PRE_ENTRY
        else:
            status[_index_label(i)] = STATUS_GAP
    return status


@dataclass
class StatusSignal:
    """재직 상태별 — 달 수와 모드별 job_gain Top-1 달 수."""

    status: str
    months: int
    top1_months: dict[str, int]
    periods: dict[str, list[str]]   # 모드별 Top-1 이었던 달(공백 달만 채운다)


def measure_signal_by_status(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, *, until: str,
    repeat_cap: float = 0.6,
) -> list[StatusSignal]:
    """재직 상태로 나눈 job_gain Top-1 달 수 — 오탐 분모를 '그 밖의 공백 달'로 좁힌다.

    재직 중인 달에 신호가 서도 사용자는 구직하지 않았으므로 맞음·틀림을 가릴 수 없다(평가 제외).
    시그니처는 운영과 같은 전체다(종전 오탐 측정과 같은 조건).
    """
    status = month_status(employment_intervals(signature, until), until)
    if not status:
        return []
    years = sorted({int(p[:4]) for p in status} | {int(p[:4]) - 1 for p in status})
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    stamper = _ExtendedStamper(birth)
    ext_signature = stamper.restamp(signature)
    top1: dict[str, set[str]] = {m: set() for m in _MODES}
    for y in years:
        ref = date(y, 7, 1)
        chart = calculate(birth.model_copy(update={"reference_date": ref}))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            elif mode in _EXT_MODES:
                ranked = LifeFitRanker().rank(
                    cands, signature=ext_signature, glyph_context=stamper.ctx_for(ref),
                    glyph_weight=glyph_w, repeat_cap=repeat_cap, glyph_cfg=_variant_cfg(mode),
                )
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=signature, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            top_by_period: dict[str, str] = {}
            for c in ranked:
                top_by_period.setdefault(c.period, str(c.event_key))
            top1[mode] |= {p for p, k in top_by_period.items() if k == "job_gain"}
    out: list[StatusSignal] = []
    for st in (STATUS_EMPLOYED, STATUS_PRE_ENTRY, STATUS_GAP):
        months = sorted(p for p, s in status.items() if s == st)
        hits = {m: sorted(set(months) & top1[m]) for m in _MODES}
        out.append(StatusSignal(
            status=st, months=len(months), top1_months={m: len(v) for m, v in hits.items()},
            periods=hits if st != STATUS_EMPLOYED else {},
        ))
    return out


def measure_pre_entry_loo(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, *, until: str,
    repeat_cap: float = 0.6,
) -> dict[str, list[str]]:
    """입사 직전 창(공백 달)의 job_gain Top-1 달 — 그 창이 가리키는 입사 행을 뺀 시그니처로 센다.

    `measure_signal_by_status` 의 입사 직전 창 줄은 전체 시그니처라 입사 행 자신의 세운 글자가
    전월·전전월에 겹친다(표본 내 측정). 여기서는 달마다 그 달이 '직전'인 입사 행(1~2달 뒤 입사)을
    모두 빼고 정렬해, 구직 달 안에서 입사 직전 달과 그 밖의 달을 같은 조건으로 견준다.

    Returns:
        모드별 Top-1 이었던 입사 직전 달 목록(정렬).
    """
    status = month_status(employment_intervals(signature, until), until)
    pre_months = sorted(p for p, st in status.items() if st == STATUS_PRE_ENTRY)
    entries = [
        r for r in signature
        if r.event_key == "job_gain" and r.source is LifeEventSource.EMPLOYMENT_HISTORY
        and r.outcome is LifeEventOutcome.CONFIRMED
        and r.attrs.nature in EMPLOYMENT_STAT_NATURES and len(r.period) >= 7
    ]
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    stamper = _ExtendedStamper(birth)
    ext_signature = stamper.restamp(signature)
    hits: dict[str, list[str]] = {m: [] for m in _MODES}
    for month in pre_months:
        idx = _label_index(month)
        held = {
            r.event_row_id for r in entries
            if 1 <= _label_index(r.period) - idx <= _LEAD_MONTHS
        }
        rest = [r for r in signature if r.event_row_id not in held]
        ext_rest = [r for r in ext_signature if r.event_row_id not in held]
        ref = reference_date_for_label(month)
        chart = calculate(birth.model_copy(update={"reference_date": ref}))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            elif mode in _EXT_MODES:
                ranked = LifeFitRanker().rank(
                    cands, signature=ext_rest, glyph_context=stamper.ctx_for(ref),
                    glyph_weight=glyph_w, repeat_cap=repeat_cap, glyph_cfg=_variant_cfg(mode),
                )
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=rest, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            top = next((str(c.event_key) for c in ranked if c.period == month), None)
            if top == "job_gain":
                hits[mode].append(month)
    return hits


def render_seeking_md(rows: list[StatusSignal], pre_loo: dict[str, list[str]]) -> str:
    """구직 달 변별 표 — 입사 직전 달(입사 행 제외 측정)과 그 밖의 공백 달의 Top-1 비율."""
    by = {r.status: r for r in rows}
    pre, gap = by.get(STATUS_PRE_ENTRY), by.get(STATUS_GAP)
    if pre is None or gap is None or not pre.months or not gap.months:
        return "구직 달 변별: 공백 달 없음."
    lines = [
        f"구직 달 변별 — 입사 직전 {pre.months}달(그 입사 행을 뺀 측정) 대 그 밖의 공백 "
        f"{gap.months}달",
        "| 모드 | 입사 직전 Top-1 | 비율 | 그 밖 Top-1 | 비율 | 배수 |",
        "|---|---|---|---|---|---|",
    ]
    for m in _MODES:
        a, b = len(pre_loo.get(m, [])), gap.top1_months[m]
        ra, rb = a / pre.months, b / gap.months
        lift = f"{ra / rb:.2f}" if rb else "-"
        lines.append(f"| {m} | {a} | {ra:.3f} | {b} | {rb:.3f} | {lift} |")
    lines.append("")
    lines.append("배수 1.0 = 구직 달 안에서 입사 직전과 그 밖을 가리지 못함.")
    return "\n".join(lines)


def render_status_md(rows: list[StatusSignal]) -> str:
    """재직 상태별 표 — 오탐률은 '그 밖의 공백 달' 줄만 읽는다."""
    if not rows:
        return "재직 상태 구분 측정: 이력 구간 없음."
    lines = [
        "재직 상태별 job_gain Top-1 달 수(달 수 대비) — 재직 중인 달은 평가에서 뺀다",
        "| 상태 | 달 수 | " + " | ".join(_MODES) + " |", "|---|---|" + "---|" * len(_MODES),
    ]
    for r in rows:
        cells = [
            f"{r.top1_months[m]} ({round(r.top1_months[m] / r.months, 3) if r.months else 0.0})"
            for m in _MODES
        ]
        lines.append(f"| {_STATUS_KO[r.status]} | {r.months} | " + " | ".join(cells) + " |")
    for r in rows:
        if r.status == STATUS_GAP:
            lines.append("")
            lines.append("오탐 후보 달(공백·그 밖) — 모드별 Top-1 이었던 달")
            for m in _MODES:
                lines.append(f"- {m}: {', '.join(r.periods.get(m, [])) or '없음'}")
    return "\n".join(lines)


def summarize(rows: list[HeldOut]) -> dict[str, dict[str, float | int]]:
    """모드별 Top-3 적중 수·비율·평균 순위."""
    summary: dict[str, dict[str, float | int]] = {}
    n = len(rows)
    for mode in _MODES:
        ranked = [rk for r in rows if (rk := r.rank[mode]) is not None]
        hits = sum(1 for rk in ranked if rk <= _TOP_N)
        summary[mode] = {
            "n": n, "top3_hits": hits, "top3_rate": round(hits / n, 3) if n else 0.0,
            "mean_rank": round(sum(ranked) / len(ranked), 2) if ranked else 0.0,
            "unranked": n - len(ranked),
        }
    return summary


def render_md(rows: list[HeldOut], summary: dict[str, dict[str, float | int]]) -> str:
    """사람이 읽는 표."""
    lines = [
        "| 모드 | n | Top-3 적중 | 비율 | 평균 순위 | 후보 없음 |", "|---|---|---|---|---|---|",
    ]
    for mode, s in summary.items():
        lines.append(f"| {mode} | {s['n']} | {s['top3_hits']} | {s['top3_rate']} | "
                     f"{s['mean_rank']} | {s['unranked']} |")
    lines += [
        "", "| 입사월 | 회사 | " + " | ".join(_MODES) + " | glyph_cap Top-3 |",
        "|---|---|" + "---|" * (len(_MODES) + 1),
    ]
    for r in rows:
        lines.append(f"| {r.period} | {r.label} | "
                     + " | ".join(str(r.rank[m]) for m in _MODES)
                     + f" | {', '.join(r.top3['glyph_cap'])} |")
    lines.append("")
    lines.append("우연 기준선 Top-3 = 25%. 판정은 데굴님(점수 규칙은 실사례 적중률로 ON/OFF).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--repeat-cap", type=float, default=0.6)
    ap.add_argument(
        "--until", default=None,
        help="재직 상태 구분 측정의 끝 달 'YYYY-MM'(기본: 이력의 마지막 입사·퇴사 달)",
    )
    args = ap.parse_args(argv)
    _load_env()
    record = SubjectStore().get(args.subject)
    if record is None:
        print(f"대상 없음: {args.subject}", file=sys.stderr)
        return 2
    signature = LifeEventStore().subject_signature(record.owner_id, args.subject)
    engine = EventEngineV2(_BACKEND / "dictionaries")
    rows = measure(record.birth, signature, engine, repeat_cap=args.repeat_cap)
    summary = summarize(rows)
    fp_rows = measure_false_positive(record.birth, signature, engine, repeat_cap=args.repeat_cap)
    last = max(
        (r.period for r in signature
         if r.source is LifeEventSource.EMPLOYMENT_HISTORY and len(r.period) >= 7),
        default="",
    )
    until = args.until or last
    status_rows = (
        measure_signal_by_status(
            record.birth, signature, engine, until=until, repeat_cap=args.repeat_cap,
        ) if until else []
    )
    pre_loo = (
        measure_pre_entry_loo(
            record.birth, signature, engine, until=until, repeat_cap=args.repeat_cap,
        ) if until else {}
    )
    md = (render_md(rows, summary) + "\n\n" + render_fp_md(fp_rows)
          + "\n\n" + render_status_md(status_rows)
          + "\n\n" + render_seeking_md(status_rows, pre_loo))
    print(md)
    if args.json:
        args.json.write_text(json.dumps(
            {"summary": summary, "rows": [asdict(r) for r in rows],
             "false_positive": [asdict(r) for r in fp_rows],
             "signal_by_status": [asdict(r) for r in status_rows],
             "pre_entry_loo": pre_loo}, ensure_ascii=False, indent=2,
        ), encoding="utf-8")
    if args.md:
        args.md.write_text(md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
