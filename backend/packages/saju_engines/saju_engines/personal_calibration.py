"""personal_calibration — 개인 과거 사건 시그니처로 후보를 보정한다(LIFE_EVENT_INFERENCE.md §4).

같은 신호 지문의 과거 확정 사건과 유사하면 personal_match↑(past_event_match), 반복 확정 테마는
가중(repeated_life_theme), 과거에 '안 일어남'으로 확인된 유형은 감점(failed_prediction_penalty),
반복 확정/예정인데 후보에 없는 사건은 시드(missing-event seed — 예: relocation 누락 보완).
본 계층은 개인(subject 본인) 시그니처만 다룬다. 코호트는 활성 게이트 통과 후 별도(§4.4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    Pillar4,
    TwelveStage,
)
from saju_shared_types.life_event import LifeEventOutcome, LifeEventRow, SignalFingerprint

from . import period_v2_config as _cfg
from .glyph_context import GlyphContext

_OCCURRED = {LifeEventOutcome.CONFIRMED, LifeEventOutcome.PLANNED}
# 글자 지문 가중·lift 기준(reviewed:false — EMPLOYMENT_HISTORY_CALIBRATION.md §3-2).
_GLYPH_CFG_PATH = (
    Path(__file__).resolve().parents[3] / "dictionaries" / "event_engine"
    / "personal_glyph_weights.json"
)
_GLYPH_CFG: dict[str, Any] = json.loads(_GLYPH_CFG_PATH.read_text(encoding="utf-8"))
#: 취업 통계(글자 lift)에 넣는 성격 — None(캘리브레이션 회상)·정규·파견. 군복무·인턴·전환 제외.
_STAT_NATURES: frozenset[str | None] = frozenset({None, "regular", "dispatch"})
PERSONAL_GLYPH_REPEAT = "PERSONAL_GLYPH_REPEAT"  # 서술 전용 근거 코드(점수 무관)
# 시드 가능한 키 = 채점 taxonomy(EventKeyV2). 원장 전용 키(LEDGER_ONLY_EVENT_KEYS)는 제외.
_SEEDABLE_KEYS = frozenset(k.value for k in EventKeyV2)


def candidate_fingerprint(
    c: EventCandidateV2, ctx: GlyphContext | None = None,
) -> SignalFingerprint:
    """후보의 신호 지문(십성그룹·궁성·관계·12운성) — 개인·코호트 매칭 단위.

    `ctx`를 주면 글자 차원(세운·월운 네 글자 + 원국 재현)도 채운다(P1). 없으면 기존 지문 그대로.
    """
    groups = sorted({TEN_GOD_GROUP[g].value for g in c.source_ten_gods if g in TEN_GOD_GROUP})
    relation: str | None = None
    for code in c.reason_codes:
        if code.startswith("REL_"):
            parts = code.split("_")
            if len(parts) >= 2:
                relation = parts[1]
                break
    fp = SignalFingerprint(
        ten_god_groups=groups,
        palace=c.palace.value if c.palace else None,
        relation=relation,
        twelve_stage=c.twelve_stage.value if c.twelve_stage else None,
    )
    return ctx.with_glyphs(fp, c.period) if ctx is not None else fp


def glyph_similarity(a: SignalFingerprint, b: SignalFingerprint) -> float:
    """글자 지문 유사도 0~1 — 자리별 가중 일치(양쪽에 있는 자리만) + 원국 재현 공통 보너스."""
    if not a.glyphs or not b.glyphs:
        return 0.0
    weights: dict[str, float] = _GLYPH_CFG["position_weights"]
    total = 0.0
    hit = 0.0
    for pos, w in weights.items():
        if pos in a.glyphs and pos in b.glyphs:
            total += w
            if a.glyphs[pos] == b.glyphs[pos]:
                hit += w
    if total <= 0:
        return 0.0
    sim = hit / total
    if set(a.natal_echo) & set(b.natal_echo):
        sim += float(_GLYPH_CFG.get("natal_echo_bonus", 0.0))
    return min(1.0, sim)


def default_glyph_weight() -> float:
    """플래그 ON 이면 사전의 glyph_weight, OFF 면 0(점수 불변 — 근거 코드만)."""
    return float(_GLYPH_CFG["glyph_weight"]) if _cfg.PERSONAL_GLYPH_SCORE_ENABLED else 0.0


def fingerprint_similarity(
    a: SignalFingerprint, b: SignalFingerprint, glyph_weight: float = 0.0,
) -> float:
    """두 신호 지문의 유사도 0~1 (십성그룹 Jaccard 0.4 + 궁성·관계·12운성 일치).

    `glyph_weight`>0 이고 양쪽에 글자가 있으면 (1-w)·기본 + w·글자 유사도. 0이면 기존 식과 동일.
    """
    sa, sb = set(a.ten_god_groups), set(b.ten_god_groups)
    jac = len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0
    palace = 1.0 if a.palace and a.palace == b.palace else 0.0
    relation = 1.0 if a.relation and a.relation == b.relation else 0.0
    stage = 1.0 if a.twelve_stage and a.twelve_stage == b.twelve_stage else 0.0
    base = 0.4 * jac + 0.3 * palace + 0.2 * relation + 0.1 * stage
    if glyph_weight > 0 and a.glyphs and b.glyphs:
        return (1 - glyph_weight) * base + glyph_weight * glyph_similarity(a, b)
    return base


def glyph_lift(
    cfp: SignalFingerprint, rows: list[LifeEventRow], position: str = "wolwoon_branch",
) -> tuple[float, int, int] | None:
    """개인 기저율 lift = (같은 글자 사건 비율) / (그 글자 달의 기대 비율 1/12 또는 1/10).

    rows 는 같은 사건 키의 확정 행(취업 통계 성격만). 글자 있는 행이 min_rows 미만이면 None.
    반환 (lift, 일치 수, 글자 있는 행 수).
    """
    g = cfp.glyphs.get(position)
    if not g:
        return None
    with_glyph = [r for r in rows if position in r.signal_fingerprint.glyphs]
    cfg = _GLYPH_CFG["lift"]
    if len(with_glyph) < int(cfg["min_rows"]):
        return None
    hits = sum(1 for r in with_glyph if r.signal_fingerprint.glyphs.get(position) == g)
    kind = "stem" if position.endswith("_stem") else "branch"
    expected = float(cfg["expected_share"][kind])
    return (hits / len(with_glyph)) / expected, hits, len(with_glyph)


def _is_stat_row(r: LifeEventRow) -> bool:
    return r.attrs.nature in _STAT_NATURES


# 개인 시그니처가 점수에 주는 최대 가감(상한) — 기저 명리 계산을 뒤집지 않는 보정폭.
_PERSONAL_SCORE_CAP = 8
# 확신도 티어 순서(강한 매칭/불일치 시 ±1티어만 이동).
_CONF_ORDER = [
    ConfidenceLevel.THEME_ONLY,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    ConfidenceLevel.EVENT_CANDIDATE,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT,
]


def _shift_confidence(level: ConfidenceLevel, steps: int) -> ConfidenceLevel:
    """확신도 티어를 steps(±)만큼 이동(범위 클램프)."""
    i = _CONF_ORDER.index(level)
    return _CONF_ORDER[max(0, min(len(_CONF_ORDER) - 1, i + steps))]


def apply_personal_match(
    candidates: list[EventCandidateV2],
    signature: list[LifeEventRow],
    ctx: GlyphContext | None = None,
    glyph_weight: float | None = None,
) -> list[EventCandidateV2]:
    """후보별 personal_match를 개인 시그니처로 산출하고, 그 강도를 점수·확신도에 상한 내 반영한다.

    현실 신호 캘리브레이션(사용자 확인 과거 사건)이 정렬만 바꾸지 않고 **계산(점수·확신도)** 을
    보정해 풀이 정확도를 높인다(사용자 확정 2026-07-02, 풀이 프롬프트 낭독이 아님). 점수 보정폭은
    ±``_PERSONAL_SCORE_CAP``(기저 명리 계산을 뒤집지 않음), 확신도는 강한 매칭/불일치 시 ±1티어만
    이동한다. 사건 타입·정렬축(lei_rank_key)은 불변.

    P1(글자 차원): `ctx`가 있으면 후보 지문에 글자를 채우고, 같은 키의 취업 통계 행에서 월지 글자
    lift 가 기준을 넘으면 근거 코드 ``PERSONAL_GLYPH_REPEAT``를 붙인다(서술 전용). 점수에는
    `glyph_weight`(None=플래그 기준, 기본 0)만큼만 들어간다.
    """
    if not signature:
        return candidates
    w = default_glyph_weight() if glyph_weight is None else glyph_weight
    occurred: dict[str, list[LifeEventRow]] = {}
    failed: dict[str, list[LifeEventRow]] = {}
    for r in signature:
        (occurred if r.outcome in _OCCURRED else failed).setdefault(r.event_key, []).append(r)
    lift_cfg = _GLYPH_CFG["lift"]
    out: list[EventCandidateV2] = []
    for c in candidates:
        ek = str(c.event_key)
        cfp = candidate_fingerprint(c, ctx)
        oc = occurred.get(ek, [])
        fl = failed.get(ek, []) if failed.get(ek) is not None else []
        match = max(
            (fingerprint_similarity(cfp, r.signal_fingerprint, w) for r in oc), default=0.0,
        )
        repeat = 0.2 * max(0, len({r.period for r in oc}) - 1)  # 반복 확정 테마 가중
        fail = max(
            (fingerprint_similarity(cfp, r.signal_fingerprint, w) for r in fl), default=0.0
        ) * 0.5
        pm = round((match + repeat - fail) * 100, 1)
        # 글자 반복 근거(서술 전용) — 같은 키·취업 통계 성격 행의 월지 lift.
        glyph_codes: list[str] = []
        lift = glyph_lift(cfp, [r for r in oc if _is_stat_row(r)]) if cfp.glyphs else None
        if (
            lift is not None
            and lift[1] >= int(lift_cfg["min_hits"])
            and lift[0] >= float(lift_cfg["min_lift"])
        ):
            # 접미 '글자:일치/표본' — 서술은 수치만(회사·사례 지목 없음, 2026-10-22 데굴님 결정).
            glyph_codes.append(
                f"{PERSONAL_GLYPH_REPEAT}:{cfp.glyphs['wolwoon_branch']}:{lift[1]}/{lift[2]}"
            )
        if pm == 0.0:
            if glyph_codes:
                out.append(c.model_copy(update={"reason_codes": [*c.reason_codes, *glyph_codes]}))
            else:
                out.append(c)
            continue
        # 점수 보정(상한 클램프) + 강한 매칭·불일치 시 확신도 ±1티어.
        boost = round(max(-100.0, min(100.0, pm)) / 100 * _PERSONAL_SCORE_CAP)
        new_score = max(0, min(100, c.score + boost))
        conf = c.confidence_level
        if pm >= 50:
            conf = _shift_confidence(conf, 1)
        elif pm <= -50:
            conf = _shift_confidence(conf, -1)
        reasons = [*c.reason_codes, "PERSONAL_MATCH" if pm > 0 else "PERSONAL_FAIL", *glyph_codes]
        out.append(c.model_copy(update={
            "personal_match": pm, "reason_codes": reasons,
            "score": new_score, "confidence_level": conf,
        }))
    return out


def seed_missing_events(
    candidates: list[EventCandidateV2], signature: list[LifeEventRow], periods: list[str]
) -> list[EventCandidateV2]:
    """반복 확정/예정 테마인데 후보에 없는 사건을 시드한다(사주 신호 약해도 현실·과거가 렌하면).

    예: relocation이 2025·2026 확정/예정인데 그 시점 후보에 없으면 relocation을 personal_match와
    함께 후보로 추가한다(점수=0, 강도는 personal_match·life_fit가 부여).
    """
    occurred: dict[str, list[LifeEventRow]] = {}
    for r in signature:
        if r.outcome in _OCCURRED:
            occurred.setdefault(r.event_key, []).append(r)
    # 반복(연도 2개+) 또는 예정(planned)인 테마만 시드 대상.
    themes = {
        ek: rows for ek, rows in occurred.items()
        if len({r.period for r in rows}) >= 2
        or any(r.outcome is LifeEventOutcome.PLANNED for r in rows)
    }
    if not themes:
        return candidates
    present = {(str(c.event_key), c.period) for c in candidates}
    seeds: list[EventCandidateV2] = []
    for period in periods:
        for ek, rows in themes.items():
            if (ek, period) in present or ek not in _SEEDABLE_KEYS:
                continue  # 원장 전용 키(resignation 등)는 후보로 시드하지 않는다
            rep = rows[0]
            repeats = max(0, len({r.period for r in rows}) - 1)
            seeds.append(EventCandidateV2(
                event_key=EventKeyV2(ek),
                period=period,
                score=0,  # 사주 잠재 없음 — 강도는 personal_match/life_fit
                confidence_level=ConfidenceLevel.EVENT_CANDIDATE,
                palace=_pillar(rep.signal_fingerprint.palace),
                twelve_stage=_stage(rep.signal_fingerprint.twelve_stage),
                reason_codes=["PERSONAL_SEED"],
                personal_match=round((0.6 + 0.2 * repeats) * 100, 1),
            ))
    return [*candidates, *seeds]


def _pillar(v: str | None) -> Pillar4 | None:
    try:
        return Pillar4(v) if v else None
    except ValueError:
        return None


def _stage(v: str | None) -> TwelveStage | None:
    try:
        return TwelveStage(v) if v else None
    except ValueError:
        return None
