"""일주별 오늘의 운세 — 3층 판정 모델(v2) 엔진 (docs/17 §22).

eligibility(required_signature) → evidence(channel×weight) → prior → ranking.

- 채널 신호는 (일주, 오늘 일진) 만으로 계산한다(개인 명식 불사용 — §10 제외 원칙 유지).
- expr_confidence 는 evidence 에 곱하지 않는다(§22-1 — 문구 톤 전용).
- 공망일은 合則不能空 을 따른다: 일지-일진 육합 0.4 감쇄 / 반합 0.6 / 충발 1.0 유지
  (SSOT: doc/v2_2/GONGMANG_HAP_SEMANTICS.md).
- 선발은 v1 `_select_slots` 를 재사용해 카드 불변식(3슬롯·2도메인·동의어 배제)을
  보존하고, 게이트로 good/caution 풀이 비면 최상위 비적격 후보를 감점 주입한다
  (§22-1 잠정 폴백 — 쿨다운 트랙에서 재검토).

라이브 배선은 별도 플래그(Phase 2)로만 켠다 — 본 모듈 import 자체는 v1 경로에 영향 없음.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date as DateType
from functools import lru_cache
from pathlib import Path
from typing import Any

from saju_engines import daily_ilju_fortune as v1
from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.daily_fortune import (
    DailyFortuneBoard,
    DayGanjiContext,
    content_version_for,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    PRIOR_VALUE,
    RELATION_CHANNELS,
    SIPSEONG_GROUPS,
    DailyEventCatalogV2,
    DailyEventModelV2,
    SignatureExpr,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import TWELVE_STAGE_KO_TO_KEY

_BACKEND = Path(__file__).resolve().parents[3]
_RELATIONS_PATH = _BACKEND / "dictionaries" / "relations.json"
_CATALOG_V2_PATH = _BACKEND / "dictionaries" / "daily_fortune" / "daily_event_catalog_v2.json"

#: 점수식 상수 (§22-1) — v1 과 동일한 soft-cap 계열을 유지한다.
LAMBDA = 0.7
SOFT_CAP_K = 2.2
OVERLAP_BONUS = 0.05
#: 게이트 미성립 후보를 슬롯 공백 방어로만 쓸 때의 감점 배수.
FALLBACK_PENALTY = 0.3
#: signature 리프 성립 문턱 — 관계 채널은 존재(>0), 그 외 ≥0.5(십성 중기·여기 차단).
SIGNATURE_THRESHOLD = 0.5

#: 12운성 → 기능 채널 값 (§22-2 표).
_STAGE_CHANNEL_VALUES: dict[str, dict[str, float]] = {
    "GWANDAE": {"activity_up": 0.7},
    "GEONROK": {"activity_up": 1.0},
    "JEWANG": {"activity_up": 1.0, "overdrive": 0.8},
    "SOE": {"stamina_down": 0.6},
    "BYEONG": {"stamina_down": 1.0, "pace_down": 0.6},
    "SA": {"pace_down": 1.0, "disengage": 0.8},
    "JEOL": {"disengage": 1.0},
    "MYO": {"closure": 1.0},
    "JANGSAENG": {"renewal": 1.0},
    "MOKYOK": {"renewal": 0.6},
    "TAE": {"renewal": 0.5},
    "YANG": {"renewal": 0.5},
}

_GEN = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_OVR = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


@lru_cache(maxsize=1)
def wonjin_pairs(relations_path: str = str(_RELATIONS_PATH)) -> frozenset[frozenset[str]]:
    """relations.json 의 원진 6쌍 — 글자 문자열 쌍 집합."""
    raw = json.loads(Path(relations_path).read_text(encoding="utf-8"))
    return frozenset(
        frozenset(item["participants"])
        for item in raw["items"]
        if item.get("type") == "wonjin"
    )


@lru_cache(maxsize=1)
def load_catalog_v2(path: str = str(_CATALOG_V2_PATH)) -> DailyEventCatalogV2:
    """v2 카탈로그 로드 + pydantic 검증 (48종)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return DailyEventCatalogV2.model_validate(raw)


def _element_direction(src: str, dst: str) -> str:
    """오늘(src) 오행이 나(dst) 오행에 갖는 방향 채널명."""
    if src == dst:
        return "bihwa"
    if _GEN[src] == dst:
        return "saeng_a"
    if _OVR[src] == dst:
        return "geuk_a"
    if _OVR[dst] == src:
        return "a_geuk"
    return "a_saeng"


def day_channels(
    ilju_stem: Stem, ilju_branch: Branch, ctx: DayGanjiContext
) -> dict[str, float]:
    """(일주, 날짜)의 채널 신호 전체 (§22-2). 값 범위 0..1.

    Args:
        ilju_stem: 일주 천간(=일간).
        ilju_branch: 일주 지지(=일지).
        ctx: 오늘 일진·월운·세운 간지(§22-2 삼합 제3지 helpers 포함).

    Returns:
        채널명 → 신호값. 십성 채널은 표면성 등급(천간 1.0/본기 0.7/중기·여기 0.3).
    """
    ds, db = Stem(ctx.day_stem), Branch(ctx.day_branch)
    helpers = (Branch(ctx.month_branch), Branch(ctx.year_branch))
    ch: dict[str, float] = {}

    # 관계 — 연결/마찰 분리 (일지 ↔ 오늘 지지)
    hits = v1._branch_relations(db, ilju_branch, helpers)
    ch["yukhap"] = 1.0 if "six_combination" in hits else 0.0
    if "three_harmony_complete" in hits:
        ch["samhap"] = 1.0
    elif "half_harmony" in hits:
        ch["samhap"] = 0.6
    else:
        ch["samhap"] = 0.0
    ch["chung"] = 1.0 if "clash" in hits else 0.0
    if "punishment" in hits:
        full = v1._REL_STRENGTH["punishment_full"]
        ch["hyeong"] = min(1.0, hits["punishment"] / full) if full else 1.0
    else:
        ch["hyeong"] = 0.0
    ch["pa"] = 1.0 if "break" in hits else 0.0
    ch["hae"] = 1.0 if "harm" in hits else 0.0
    ch["wonjin"] = (
        1.0 if frozenset({str(db), str(ilju_branch)}) in wonjin_pairs() else 0.0
    )

    # 공망일 — 合則不能空 감쇄
    gm = 0.0
    if db in gongmang_branches(ilju_stem, ilju_branch):
        pair = frozenset({db, ilju_branch})
        if pair in v1.SIX_COMBINATIONS:
            gm = 0.4
        elif any(pair <= members for members, _e, _r in v1.THREE_HARMONY):
            gm = 0.6
        else:
            gm = 1.0
    ch["gongmang"] = gm

    # 12운성 기능 채널 (오늘 일진 천간의 내 일지 12운성)
    stage_key = str(TWELVE_STAGE_KO_TO_KEY.get(twelve_unseong(ds, ilju_branch), ""))
    stage_values = _STAGE_CHANNEL_VALUES.get(stage_key, {})
    for name in (
        "activity_up", "overdrive", "stamina_down", "pace_down",
        "disengage", "closure", "renewal",
    ):
        ch[name] = stage_values.get(name, 0.0)
    if ch["overdrive"] and STEM_ELEMENT[ds] == STEM_ELEMENT[ilju_stem]:
        ch["overdrive"] = min(1.0, ch["overdrive"] + 0.2)  # 비화 동반 과속 강화

    # 오행 5방향 — 지지쌍 0.6 + 천간쌍 0.4 합성
    for name in ("saeng_a", "a_saeng", "geuk_a", "a_geuk", "bihwa"):
        ch[name] = 0.0
    ch[_element_direction(
        BRANCH_ELEMENT[db].value, BRANCH_ELEMENT[ilju_branch].value
    )] += 0.6
    ch[_element_direction(
        STEM_ELEMENT[ds].value, STEM_ELEMENT[ilju_stem].value
    )] += 0.4

    # 십성 — 표면성 3등급 (§22-2): 천간 1.0 > 본기 0.7 > 중기·여기 0.3
    for name in ("비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인"):
        ch[name] = 0.0

    def _tg(target: Stem) -> str:
        if target == ilju_stem:
            return "비견"
        return v1.ten_god(ilju_stem, target).value

    ch[_tg(ds)] = max(ch[_tg(ds)], 1.0)
    hidden = [
        (Stem(hs), str(getattr(ht, "value", ht)))
        for hs, ht, _w in v1.hidden_stems_for(db)
    ]
    for hs, htype in hidden:
        grade = 0.7 if htype == "main" else 0.3
        ch[_tg(hs)] = max(ch[_tg(hs)], grade)

    # 오행 활성(간이 object hazard) — 金·火: 천간·본기 1.0 / 지장간만 0.5
    main_elem = BRANCH_ELEMENT[db].value
    for name, elem in (("metal", "金"), ("fire", "火")):
        value = 0.0
        if STEM_ELEMENT[ds].value == elem or main_elem == elem:
            value = 1.0
        elif any(STEM_ELEMENT[hs].value == elem for hs, _t in hidden):
            value = 0.5
        ch[name] = value
    return ch


def channel_value(ch: dict[str, float], name: str) -> float:
    """채널값 조회 — 십성 그룹 별칭은 구성원 최댓값."""
    if name in SIPSEONG_GROUPS:
        return max(ch.get(member, 0.0) for member in SIPSEONG_GROUPS[name])
    return ch.get(name, 0.0)


def signature_satisfied(ch: dict[str, float], expr: SignatureExpr) -> bool:
    """게이트식 평가 (§22-1). None = 무게이트(포용 사건).

    리프 성립 기준: 관계 채널은 존재(>0), 그 외 ≥ ``SIGNATURE_THRESHOLD``
    (십성 중기·여기 0.3 단독 출전 차단 — §22-2 표면성 규칙).
    """
    if expr is None:
        return True
    if isinstance(expr, str):
        if expr in SIPSEONG_GROUPS:
            return any(signature_satisfied(ch, m) for m in SIPSEONG_GROUPS[expr])
        value = ch.get(expr, 0.0)
        if expr in RELATION_CHANNELS:
            return value > 1e-9
        return value >= SIGNATURE_THRESHOLD
    op = expr[0]
    combine = any if op == "or" else all
    return combine(signature_satisfied(ch, sub) for sub in expr[1:])


@dataclass(frozen=True)
class ScoredEventV2:
    """사건 1개의 v2 채점 결과 — 게이트 성립 여부를 동반한다."""

    eligible: bool
    scored: v1._ScoredEvent


def score_event_v2(
    key: str, model: DailyEventModelV2, ch: dict[str, float]
) -> ScoredEventV2:
    """3층 채점 (§22-1) — expr_confidence 미적용.

    net = prior + Σ(w·s) − λ·Σ contradiction, activation = 1 − exp(−k·net).
    게이트 미성립 후보는 activation 에 ``FALLBACK_PENALTY`` 를 곱해 폴백 전용으로만
    쓰이게 한다.
    """
    eligible = signature_satisfied(ch, model.required_signature)
    evidence = PRIOR_VALUE[model.prior]
    contradiction = 0.0
    supporting = 0
    for name, weight in model.evidence.items():
        signal = channel_value(ch, name)
        if signal <= 0:
            continue
        if weight > 0:
            evidence += weight * signal
            if weight >= 0.3 and signal >= 0.35:
                supporting += 1
        else:
            contradiction += (-weight) * signal
    net = max(0.0, evidence - LAMBDA * contradiction)
    if supporting >= 2:
        net += OVERLAP_BONUS
    activation = 1.0 - math.exp(-SOFT_CAP_K * net)
    if not eligible:
        activation *= FALLBACK_PENALTY
    probability = max(5, min(95, round(5 + 90 * activation)))
    if probability >= 85 and supporting < 2:
        probability = 84  # §11 85+ 게이트 유지
    if probability <= 10 and contradiction < v1._STRONG_CONTRADICTION:
        probability = 11
    scored = v1._ScoredEvent(
        event_key=key,
        domain=model.domain,
        valence=model.valence,
        slots=tuple(model.slots),
        headline_slots=tuple(model.headline_slots or model.slots),
        synonym_group=model.synonym_group,
        activation=activation,
        probability=probability,
        supporting_groups=supporting,
        contradiction=contradiction,
    )
    return ScoredEventV2(eligible=eligible, scored=scored)


@dataclass(frozen=True)
class SlotSelectionV2:
    """v2 슬롯 선발 결과 + 감사 필드."""

    good: v1._ScoredEvent
    caution: v1._ScoredEvent
    support: v1._ScoredEvent
    eligible_keys: frozenset[str]
    fallback_used: bool


def build_pool_v2(
    catalog: DailyEventCatalogV2, ch: dict[str, float]
) -> tuple[list[v1._ScoredEvent], frozenset[str], bool]:
    """(일주, 날짜)의 선발 후보 풀 — 게이트 통과 사건 + 슬롯 공백 폴백.

    good/caution 풀이 비면 최상위 비적격 후보 1개를 감점 상태로 주입한다
    (§22-1 잠정 폴백 — 카드 3슬롯 계약 유지). 선발과 보드 빌드가 같은 풀을
    쓰도록 여기 한 곳에서만 구성한다.

    Returns:
        (후보 풀, 게이트 통과 event_key 집합, 폴백 사용 여부).
    """
    results = [
        score_event_v2(key, model, ch) for key, model in catalog.events.items()
    ]
    pool = [r.scored for r in results if r.eligible]
    eligible_keys = frozenset(r.scored.event_key for r in results if r.eligible)
    fallback_used = False

    def _fits(scored: v1._ScoredEvent, valence: str) -> bool:
        if scored.valence != valence:
            return False
        return valence != "good" or "good" in scored.slots

    for valence in ("good", "caution"):
        if not any(_fits(scored, valence) for scored in pool):
            candidates = sorted(
                (
                    r.scored
                    for r in results
                    if not r.eligible and _fits(r.scored, valence)
                ),
                key=lambda s: (-s.activation, s.event_key),  # 동점 결정론
            )
            if candidates:
                pool.append(candidates[0])
                fallback_used = True
    return pool, eligible_keys, fallback_used


def select_slots_v2(
    catalog: DailyEventCatalogV2,
    ch: dict[str, float],
    seed_base: str,
) -> SlotSelectionV2:
    """게이트 통과 후보만으로 v1 선발 불변식 하에 3슬롯을 뽑는다."""
    pool, eligible_keys, fallback_used = build_pool_v2(catalog, ch)
    good, caution, support = v1._select_slots(pool, seed_base)
    return SlotSelectionV2(
        good=good, caution=caution, support=support,
        eligible_keys=eligible_keys, fallback_used=fallback_used,
    )


#: 제외 확정 사건 (docs/17 §22-0 — 외부 사실 주어).
EXCLUDED_FROM_V1: frozenset[str] = frozenset({"weather_water_safety_caution"})


def validate_against_v1(
    catalog: DailyEventCatalogV2, v1_catalog: dict[str, Any]
) -> list[str]:
    """v1 카탈로그와의 정합 검사 — 위반 메시지 목록(비면 통과).

    v2 는 §22-3 표의 48종만 담는다: v1 전체에서 제외 사건을 뺀 집합과 key 가 정확히
    일치해야 하고, 사건 정체성(label/domain/valence)은 v1 과 갈라질 수 없다.
    """
    errors: list[str] = []
    raw_events = v1_catalog["events"]
    if isinstance(raw_events, dict):
        v1_events: dict[str, dict[str, Any]] = dict(raw_events)
    else:
        v1_events = {
            e["key"]: {k: v for k, v in e.items() if k != "key"} for e in raw_events
        }
    expected = set(v1_events) - EXCLUDED_FROM_V1
    actual = set(catalog.events)
    for key in sorted(expected - actual):
        errors.append(f"v2 누락: {key}")
    for key in sorted(actual - expected):
        errors.append(f"v2 초과(§22-3 밖): {key}")
    for key in sorted(actual & expected):
        src, dst = v1_events[key], catalog.events[key]
        for field in ("label", "domain", "valence"):
            if src[field] != getattr(dst, field):
                errors.append(
                    f"{key}.{field} 불일치: v1={src[field]!r} v2={getattr(dst, field)!r}"
                )
    return errors


def unsatisfiable_signatures(
    catalog: DailyEventCatalogV2, year: int = 2026
) -> list[str]:
    """게이트 성립 가능성 정적 검증 (§22-4).

    고정 연도의 전 일자 × 60일주에서 한 번도 성립하지 않는 signature 를 찾는다.
    eligible=0 은 "저노출"이 아니라 즉시 결함이다 — v1 초판의 낙상(충∧파/해,
    지지쌍 1개로는 성립 0회) 사례를 컴파일 단계에서 차단한다.

    Args:
        catalog: v2 카탈로그.
        year: 검사 연도(입춘·절기 경계 반영을 위해 실제 달력 사용).

    Returns:
        전 조합에서 성립 0회인 event_key 목록(비면 통과).
    """
    import datetime as _dt

    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    remaining = {
        key: model.required_signature
        for key, model in catalog.events.items()
        if model.required_signature is not None
    }
    iljus = [ganzi_from_index(i) for i in range(60)]
    day = _dt.date(year, 1, 1)
    end = _dt.date(year, 12, 31)
    while day <= end and remaining:
        ctx = v1.build_day_context(day)
        for stem, branch in iljus:
            if not remaining:
                break
            ch = day_channels(stem, branch, ctx)
            for key in [k for k, sig in remaining.items() if signature_satisfied(ch, sig)]:
                del remaining[key]
        day += _dt.timedelta(days=1)
    return sorted(remaining)


# ── 라이브 배선 (Phase 2) — 플래그 기본 OFF, C10 동결 중엔 beta registry 가 우선 ──

#: v2 채점 경로 활성화 — `.env.beta` 로만 켠다(import 시점 상수, pytest 는 OFF 기준).
#: ON 이어도 beta pool registry 활성 기간에는 registry 가 선행하므로 사용자 출력은
#: 풀 계약을 따른다 — 동결과 충돌하지 않는다.
DAILY_FORTUNE_MODEL_V2_ENABLED = os.getenv("SAJU_DAILY_FORTUNE_MODEL_V2") == "1"


def content_version_v2_for(target_date: DateType) -> str:
    """v2 경로의 캐시 namespace — v1 키와 반드시 갈라진다(캐시 오염 방지).

    플래그를 켜고 끌 때 같은 날짜의 v1 보드가 v2 로(또는 반대로) 서빙되면 안 된다 —
    namespace 분리가 그 유일한 방어다.
    """
    return f"{content_version_for(target_date)}|{MODEL_V2_VERSION}"


def active_content_version(target_date: DateType) -> str:
    """플래그 상태를 반영한 캐시 namespace — 보드 생성·조회·교정이 같은 키를 쓴다.

    조회(get_board)와 LLM 교정(polish)이 서로 다른 키를 보면 교정이 유령 보드에
    붙는다 — 파생 지점을 이 함수 하나로 좁힌다.
    """
    if DAILY_FORTUNE_MODEL_V2_ENABLED:
        return content_version_v2_for(target_date)
    return content_version_for(target_date)


def compute_board_v2(
    ctx: DayGanjiContext,
    dicts: v1.DailyFortuneDicts,
    catalog: DailyEventCatalogV2 | None = None,
) -> DailyFortuneBoard:
    """3층 판정 모델로 60일주 보드를 산출한다(결정론).

    채점·게이트·폴백만 v2 로 바꾸고, 선발 불변식·헤드라인 재배정·문구 렌더·중복
    감사는 v1 `compute_board` 파이프라인을 `scored_rows` 주입으로 재사용한다.
    문구·서사 사전은 여전히 v1(dicts)이 SSOT 다.

    Args:
        ctx: 오늘 일진·월운·세운 간지.
        dicts: v1 사전 3종(문구 렌더용 — 카탈로그 서사 포함).
        catalog: v2 채점 카탈로그(기본: 컴파일 스냅샷 원본 로드).

    Returns:
        `content_version` 이 v2 namespace 로 표시된 보드.
    """
    cat = catalog or load_catalog_v2()
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    scored_rows: dict[str, list[v1._ScoredEvent]] = {}
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ch = day_channels(stem, branch, ctx)
        pool, _eligible, _fallback = build_pool_v2(cat, ch)
        scored_rows[f"{stem.value}{branch.value}"] = pool
    board = v1.compute_board(ctx, dicts, scored_rows=scored_rows)
    return board.model_copy(
        update={"content_version": content_version_v2_for(ctx.the_date)}
    )
