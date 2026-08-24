"""일주별 오늘의 운세 — 챠트리스(개인 명식 무관) 규칙 엔진.

docs/17_DAILY_ILJU_FORTUNE.md 규격. 60갑자 일주 × 오늘 일진·월운·세운만으로
사건별 양의 활성도를 계산해 하루치 보드(60건)를 산출한다. 순수 함수 —
사이드이펙트(캐시·LLM)는 서비스 계층이 담당한다.

핵심 규칙(검토 확정):
- 독립 원인 그룹 5종(DAY_STEM/DAY_BRANCH_RELATION/DAY_HIDDEN_STEMS/MONTH_CONTEXT/
  YEAR_CONTEXT), 그룹당 최강 신호 1개만 독립 원인으로 인정.
- 사건별 양의 활성도: evidence/contradiction 분리, net=max(0, e−λ·c),
  p = 5 + 90·positive_soft_cap(net). p≥85는 지지 그룹 ≥2일 때만, p≤10은
  강한 contradiction 있을 때만.
- 반복 방지: 영구 이력 없이 날짜 기반 결정론 seed + 당일 60건 내부 중복 감사.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from saju_manse_core.calendar.ganji_calendar import build_month
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    BRANCH_HARMS,
    BRANCH_KO,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    STEM_KO,
    THREE_HARMONY,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.daily_fortune import (
    DailyEventForecast,
    DailyFortuneBoard,
    DailyIljuFortune,
    DailyTop5,
    DayGanjiContext,
    LuckyPlace,
    content_version_for,
)
from saju_shared_types.enums import Branch, Stem

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries" / "daily_fortune"

# 신호 그룹 가중 (PRD §10 — 합계 0.95, 나머지 0.05는 중첩 보너스)
_GROUP_WEIGHTS: dict[str, float] = {
    "DAY_STEM": 0.25,
    "DAY_BRANCH_RELATION": 0.30,
    "DAY_HIDDEN_STEMS": 0.15,
    "MONTH_CONTEXT": 0.20,
    "YEAR_CONTEXT": 0.05,
}
_OVERLAP_BONUS = 0.05  # 독립 원인 그룹 ≥2 동방향 지지 시
_LAMBDA = 0.7  # contradiction 감쇄 계수
_SIGNAL_GAIN = 1.5  # 신호 진폭 이득 — 그룹 간 상대 비중(25/30/15/20/5)은 유지, 절대 크기만 확대
_SOFT_CAP_K = 2.2  # positive_soft_cap 기울기 (분포 튜닝 2026-07-23: 85+ 도달 가능·저점 확보)
_INDEPENDENT_THRESHOLD = 0.35  # |s_g| 가 이 값 이상일 때 독립 원인으로 인정
_STRONG_CONTRADICTION = 0.25  # p≤10 허용 기준
_WEEKDAY_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
_LOTTO_MAX_PER_DAY = 3
_LOTTO_MIN_MONEY_P = 85
_LOTTO_MAX_MONEY_RANK = 10
_PLACE_MAX_REPEAT = 6  # 당일 60건 내 같은 장소 최대 노출
_DUP_RETRY = 10  # 중복 감사 시 seed salt 재시도 상한
# '오늘의 연애' 별도 노출 게이트 — 대표 love 사건이 서로 다른 독립 원인 그룹 ≥3개의
# 지지를 받는 '강한 love 전용 신호'일 때만 한 줄을 만든다. 그 외 날은 총운 헤드라인이
# 이미 그날을 커버하므로 별도 항목을 노출하지 않는다(중복·군더더기 방지, 2026-07-25).
_LOVE_LINE_MIN_SUPPORT = 3

# 관계 종류별 감지 강도(성립 조건 세분화) — 사건별 방향·크기는 카탈로그 affinity 가 결정
_REL_STRENGTH = {
    "six_combination": 1.0,
    "half_harmony": 1.0,  # 반합은 카탈로그 affinity 자체가 낮음
    "three_harmony_complete": 1.0,
    "clash": 1.0,
    "punishment_full": 1.0,  # 子卯형·삼형 완성
    "punishment_partial": 0.6,  # 삼형 2지·자형
    "break": 1.0,
    "harm": 1.0,
}


@dataclass(frozen=True)
class DailyFortuneDicts:
    """사전 3종 묶음 — 깊은 스키마 검증은 test_daily_fortune_dicts 가 담당."""

    catalog: dict[str, Any]
    templates: dict[str, Any]
    places: dict[str, Any]


@lru_cache(maxsize=2)
def load_daily_dicts(dictionaries_dir: str | None = None) -> DailyFortuneDicts:
    """daily_fortune 사전 3종을 로드(캐시)한다.

    **컴파일 스냅샷 우선, 없으면 원본 폴백**(CLAUDE.md 원칙 5 — `structure_patterns` 와
    같은 규약). 스냅샷은 `DICT_VERSION` 별로 존재하므로, 사전을 고치고 버전을 올리지
    않으면 스냅샷 부재가 되어 회귀가 잡는다. 폴백을 남기는 이유는 사전만 있는 환경
    (테스트 fixture·신규 클론)에서 서비스가 멈추지 않게 하기 위함이다.

    Args:
        dictionaries_dir: 원본 디렉터리 지정(테스트용). 지정 시 스냅샷을 쓰지 않는다.
    """
    if dictionaries_dir is None:
        from saju_shared_types.daily_fortune import DICT_VERSION

        from .daily_fortune_snapshot import load_snapshot

        snapshot = load_snapshot(DICT_VERSION)
        if snapshot is not None:
            return DailyFortuneDicts(
                catalog=snapshot["catalog"],
                templates=snapshot["templates"],
                places=snapshot["places"],
            )
    base = Path(dictionaries_dir) if dictionaries_dir else _DICTS_DEFAULT
    def _read(name: str) -> dict[str, Any]:
        return json.loads((base / name).read_text(encoding="utf-8"))
    return DailyFortuneDicts(
        catalog=_read("daily_event_catalog.json"),
        templates=_read("daily_phrase_templates.json"),
        places=_read("daily_lucky_places.json"),
    )


@lru_cache(maxsize=4)
def load_daily_dicts_for(target_date: date) -> DailyFortuneDicts:
    """그 날짜의 계약에 맞는 사전을 로드한다 (OA-6a2 날짜 경계 활성화).

    같은 날 결과 불변성을 지키기 위해 **날짜가 계약을 고른다** — 재기동이나 캐시
    유실이 있어도 과거 날짜는 과거 계약으로 재생된다.

    Args:
        target_date: 운세 대상 날짜(KST).

    Returns:
        해당 계약의 사전 묶음. 스냅샷이 없으면 현재 사전으로 폴백한다.
    """
    from saju_shared_types.daily_fortune import active_dict_version

    from .daily_fortune_snapshot import load_snapshot

    snapshot = load_snapshot(active_dict_version(target_date))
    if snapshot is None:
        return load_daily_dicts()
    return DailyFortuneDicts(
        catalog=snapshot["catalog"], templates=snapshot["templates"],
        places=snapshot["places"],
    )


def _stable_hash(text: str) -> int:
    """프로세스 간 안정적인 64bit 해시 (Python hash() 금지 — 재현성)."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _pick(seq: list[str], seed: int) -> str:
    return seq[seed % len(seq)]


def build_day_context(d: date) -> DayGanjiContext:
    """특정 날짜의 일진·월운·세운 간지 컨텍스트(입춘·절기 반영)를 만든다."""
    month_data = build_month(d.year, d.month)
    day = next(x for x in month_data["days"] if x["date"] == d)
    return DayGanjiContext(
        the_date=d,
        day_stem=day["day_ganji"][0],
        day_branch=day["day_ganji"][1],
        month_stem=day["month_ganji"][0],
        month_branch=day["month_ganji"][1],
        year_stem=day["year_ganji"][0],
        year_branch=day["year_ganji"][1],
    )


def _branch_relations(
    a: Branch, b: Branch, helpers: tuple[Branch, ...]
) -> dict[str, float]:
    """두 지지(a=운, b=일지) 관계를 세분화 감지한다.

    삼합은 helpers(월지·세운지지)가 제3지를 채울 때만 완성으로 인정하고,
    형은 자형/子卯형/삼형(2지=부분)을 구분한다. 반환 키는 카탈로그
    relation_affinity 키와 일치한다.
    """
    hits: dict[str, float] = {}
    pair = frozenset({a, b})

    if len(pair) == 2 and pair in SIX_COMBINATIONS:
        hits["six_combination"] = _REL_STRENGTH["six_combination"]

    if len(pair) == 2:
        for members, _element, _royal in THREE_HARMONY:
            if pair <= members:
                third = next(iter(members - pair))
                if third in helpers:
                    hits["three_harmony_complete"] = _REL_STRENGTH["three_harmony_complete"]
                else:
                    hits["half_harmony"] = _REL_STRENGTH["half_harmony"]
                break

    if pair in BRANCH_CLASHES:
        hits["clash"] = _REL_STRENGTH["clash"]

    # 형 — 성립 조건 세분화
    if a == b and a in SELF_PUNISHMENT:
        hits["punishment"] = _REL_STRENGTH["punishment_partial"]  # 자형
    elif pair in PUNISHMENT_MUTUAL:
        hits["punishment"] = _REL_STRENGTH["punishment_full"]  # 子卯형
    else:
        for triple in PUNISHMENT_TRIPLES:
            if len(pair) == 2 and pair <= triple:
                third = next(iter(triple - pair))
                strength = (
                    _REL_STRENGTH["punishment_full"]
                    if third in helpers
                    else _REL_STRENGTH["punishment_partial"]
                )
                hits["punishment"] = max(hits.get("punishment", 0.0), strength)
                break

    if pair in BRANCH_BREAKS:
        hits["break"] = _REL_STRENGTH["break"]
    if pair in BRANCH_HARMS:
        hits["harm"] = _REL_STRENGTH["harm"]
    return hits


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _tg_aff(event: dict[str, Any], day_master: Stem, target: Stem) -> float:
    """일간(day_master=일주 천간) 기준 target 천간의 십성 affinity."""
    if day_master == target:
        return event["ten_god_affinity"].get("비견", 0.0)  # 동일 천간은 비견으로 간주
    return event["ten_god_affinity"].get(ten_god(day_master, target).value, 0.0)


def _rel_aff(event: dict[str, Any], hits: dict[str, float]) -> float:
    return _clamp(
        sum(w * event["relation_affinity"].get(kind, 0.0) for kind, w in hits.items())
    )


def _hidden_aff(event: dict[str, Any], day_master: Stem, branch: Branch) -> float:
    """지장간 가중평균 십성 affinity."""
    hidden = hidden_stems_for(branch)
    total = sum(w for _s, _t, w in hidden)
    if total <= 0:
        return 0.0
    return _clamp(
        sum(w * _tg_aff(event, day_master, s) for s, _t, w in hidden) / total
    )


def _group_signals(
    event: dict[str, Any], ilju_stem: Stem, ilju_branch: Branch, ctx: DayGanjiContext
) -> dict[str, float]:
    """독립 원인 그룹 5종 각각의 신호값 s_g ∈ [-1, 1]."""
    day_stem = Stem(ctx.day_stem)
    day_branch = Branch(ctx.day_branch)
    month_stem = Stem(ctx.month_stem)
    month_branch = Branch(ctx.month_branch)
    year_stem = Stem(ctx.year_stem)
    year_branch = Branch(ctx.year_branch)
    helpers = (month_branch, year_branch)

    day_rel = _branch_relations(day_branch, ilju_branch, helpers)
    month_rel = _branch_relations(month_branch, ilju_branch, (day_branch, year_branch))
    year_rel = _branch_relations(year_branch, ilju_branch, (day_branch, month_branch))

    month_ctx = _clamp(
        0.4 * _tg_aff(event, ilju_stem, month_stem)
        + 0.35 * _rel_aff(event, month_rel)
        + 0.25 * _hidden_aff(event, ilju_stem, month_branch)
    )
    year_ctx = _clamp(
        0.5 * _tg_aff(event, ilju_stem, year_stem)
        + 0.3 * _rel_aff(event, year_rel)
        + 0.2 * event["element_affinity"].get(BRANCH_ELEMENT[year_branch].value, 0.0)
    )
    return {
        "DAY_STEM": _tg_aff(event, ilju_stem, day_stem),
        "DAY_BRANCH_RELATION": _rel_aff(event, day_rel),
        "DAY_HIDDEN_STEMS": _hidden_aff(event, ilju_stem, day_branch),
        "MONTH_CONTEXT": month_ctx,
        "YEAR_CONTEXT": year_ctx,
    }


@dataclass(frozen=True)
class _ScoredEvent:
    """사건 1개의 점수 산출 결과(슬롯 선발·Top5 입력)."""

    event_key: str
    domain: str
    valence: str
    slots: tuple[str, ...]
    #: 헤드라인 자격 (OA-6a). `slots`(카드 안 배치 역할)와 **분리**한다 — 두 의미를 한
    #: 필드가 겸하면 "본문 보조 역할"이 곧 "헤드라인 영구 제외"가 되어, 정리·집중·휴식
    #: 같은 생활 장면이 구조적으로 노출되지 못한다(실측: 6종 1,800카드 중 헤드라인 0회).
    headline_slots: tuple[str, ...]
    synonym_group: str | None
    activation: float  # 0..1 (expr_confidence 반영)
    probability: int  # 5..95 (게이트 후처리 반영)
    supporting_groups: int
    contradiction: float


def _positive_soft_cap(net: float) -> float:
    """양의 net evidence 를 0..1 로 포화시키는 단조 함수."""
    return 1.0 - math.exp(-_SOFT_CAP_K * max(0.0, net))


def _score_event(
    key: str, event: dict[str, Any], ilju_stem: Stem, ilju_branch: Branch,
    ctx: DayGanjiContext,
) -> _ScoredEvent:
    """사건별 양의 활성도 산식(검토 확정) — evidence/contradiction 분리."""
    signals = _group_signals(event, ilju_stem, ilju_branch, ctx)
    evidence = float(event["base_weight"])
    contradiction = 0.0
    supporting = 0
    for group, s in signals.items():
        w = _GROUP_WEIGHTS[group] * _SIGNAL_GAIN
        if s > 0:
            evidence += w * s
            if s >= _INDEPENDENT_THRESHOLD:
                supporting += 1
        elif s < 0:
            contradiction += w * (-s)

    net = max(0.0, evidence - _LAMBDA * contradiction)
    if supporting >= 2:
        net += _OVERLAP_BONUS
    activation = float(event["expr_confidence"]) * _positive_soft_cap(net)
    p = round(5 + 90 * activation)
    p = max(5, min(95, p))
    if p >= 85 and supporting < 2:
        p = 84  # 85%+ 게이트: 서로 다른 독립 원인 그룹 ≥2 지지 필요
    if p <= 10 and contradiction < _STRONG_CONTRADICTION:
        p = 11  # 근거 부재 ≠ 강한 부정 — 극저점은 강한 반대 신호가 있을 때만
    return _ScoredEvent(
        event_key=key,
        domain=event["domain"],
        valence=event["valence"],
        slots=tuple(event["slots"]),
        # 미지정 사건은 기존 `slots`로 폴백한다(하위 호환 — 사전 일괄 수정 불필요).
        headline_slots=tuple(event.get("headline_slots") or event["slots"]),
        synonym_group=event.get("synonym_group"),
        activation=activation,
        probability=p,
        supporting_groups=supporting,
        contradiction=contradiction,
    )


#: 후보 동점 해소 계약 v2 (OA-6d2, **shadow 전용** — 라이브는 v1 동결).
EVENT_SELECTION_CONTRACT_V2 = "event-selection.v2-candidate-hash"


def event_merit_key(scored: _ScoredEvent) -> tuple[int]:
    """사건의 **실질 순위**를 정하는 비-seed 항목 (OA-6d2 확정).

    실사 결과 현행 `_rank_key`가 seed 앞에서 비교하는 것은 `probability` 하나뿐이다.
    `activation`은 probability 산출의 입력일 뿐 독립 순위 항목이 아니다 — 이를 순위에
    넣는 것은 결함 수정이 아니라 **새 사건 선택 정책**이므로 별도 슬라이스로 분리한다.

    probability는 정수(5~95)라 float 비교·epsilon 처리가 필요 없다.

    Args:
        scored: 점수 산출된 사건.

    Returns:
        merit 키. 이 값이 같으면 동점이고, 그때만 tie-break이 개입할 수 있다.
    """
    return (scored.probability,)


def _tiebreak_v1(scored: _ScoredEvent, seed_base: str) -> int:
    """v1 동점 해소값 — `% 9973` 축약 포함(동결). 최종 안정 키가 없다."""
    return _stable_hash(f"{seed_base}|{scored.event_key}") % 9973


def _tiebreak_v2(scored: _ScoredEvent, target_date: date, ilju: str) -> int:
    """v2 동점 해소값 — 축약 없는 전체 해시. 후보 정체성으로만 정해진다."""
    return _stable_hash(
        "|".join((target_date.isoformat(), ilju, scored.event_key,
                  EVENT_SELECTION_CONTRACT_V2))
    )


def _rank_key(scored: _ScoredEvent, seed_base: str) -> tuple[float, int]:
    """내림차순 정렬 키 — 동률은 결정론 seed 로 해소(v1 동결, 라이브 경로)."""
    return (-scored.probability, _tiebreak_v1(scored, seed_base))


def _rank_key_v2(
    scored: _ScoredEvent, target_date: date, ilju: str
) -> tuple[float, int, str]:
    """v2 정렬 키 — merit → 전체 해시 → `event_key` 최종 안정 키.

    v1의 두 결함을 함께 고친다:
      1. `% 9973` 축약 → 49개 사건에서 실측 8건의 해시 충돌
      2. 최종 안정 키 부재 → 충돌 시 `sorted` 안정성 때문에 **입력 배열 순서**가 승자를
         정한다(무관한 사건 추가·JSON 정렬 변경에 결과가 흔들린다)
    """
    return (-scored.probability, _tiebreak_v2(scored, target_date, ilju), scored.event_key)


def select_event_v2(
    candidates: list[_ScoredEvent], *, target_date: date, ilju: str
) -> _ScoredEvent:
    """최고 merit 동치류 안에서만 승자를 고른다 (OA-6d2).

    최상위 동점군을 먼저 분리해 두면 **낮은 probability 후보가 해시값과 무관하게 절대
    선택되지 않는다는 사실이 코드 구조로 보장**된다.

    Args:
        candidates: 후보 목록(비어 있으면 안 된다).
        target_date: 대상 날짜.
        ilju: 일주 간지.

    Returns:
        승자 후보.

    Raises:
        ValueError: 후보가 비었을 때.
    """
    if not candidates:
        raise ValueError("candidates must not be empty")
    best = max(event_merit_key(c) for c in candidates)
    top_group = [c for c in candidates if event_merit_key(c) == best]
    return min(
        top_group,
        key=lambda c: (_tiebreak_v2(c, target_date, ilju), c.event_key),
    )


def _select_slots(
    scored: list[_ScoredEvent], seed_base: str, rank: Any = None,
    good_override: str | None = None,
) -> tuple[_ScoredEvent, _ScoredEvent, _ScoredEvent]:
    """슬롯 선발 + 완화 사다리 — 불변식: 항상 3개, 최소 2 domain,
    event_key 중복 금지, 동의어 그룹 동시 노출 금지.

    Args:
        rank: 정렬 키 함수. None이면 v1(라이브 동결). shadow 비교에서만 v2를 넘긴다.
        good_override: good 슬롯의 **표시 대표**로 세울 event_key(OA-6f2 P4).
            원판정을 덮어쓰는 것이 아니라, 이미 good 자격이 있고 같은 valence 인
            후보 중 표시할 장면을 고르는 것이다 — 점수·순위는 그대로다. 후보 목록에
            없거나 good 자격이 없으면 무시하고 원시 1위를 쓴다. support·caution 은
            **바뀐 good 을 기준으로 다시 선발**되므로 도메인·동의어 불변식이 유지된다.
            **shadow 전용** — 라이브는 None 이라 거동이 바뀌지 않는다.
    """
    key = rank or (lambda s: _rank_key(s, seed_base))
    ordered = sorted(scored, key=key)

    goods = [s for s in ordered if s.valence == "good" and "good" in s.slots]
    cautions = [s for s in ordered if s.valence == "caution"]
    good = goods[0]
    if good_override is not None:
        good = next((s for s in goods if s.event_key == good_override), good)

    def _ok(cand: _ScoredEvent, taken: list[_ScoredEvent], distinct_domain: bool) -> bool:
        if any(cand.event_key == t.event_key for t in taken):
            return False
        if cand.synonym_group and any(cand.synonym_group == t.synonym_group for t in taken):
            return False
        if distinct_domain and any(cand.domain == t.domain for t in taken):
            return False
        return True

    caution = next((c for c in cautions if _ok(c, [good], True)), None)
    if caution is None:  # 완화: domain 중복 허용
        caution = next((c for c in cautions if _ok(c, [good], False)), cautions[0])

    supports = [s for s in ordered if "support" in s.slots]
    taken = [good, caution]
    support = next((s for s in supports if _ok(s, taken, True)), None)
    if support is None:  # 완화 1: domain 중복 허용(최소 2 domain 은 good/caution 이 보장)
        support = next((s for s in supports if _ok(s, taken, False)), None)
    if support is None:  # 완화 2: 차순위 good 을 보조로
        support = next(s for s in goods if _ok(s, taken, False))
    # 최소 2개 domain 불변식 확인 — good/caution 이 동일 domain 으로 완화된 경우 보조는 다른 domain
    if good.domain == caution.domain and support.domain == good.domain:
        alt = next(
            (s for s in supports + goods if _ok(s, taken, False) and s.domain != good.domain),
            None,
        )
        if alt is not None:
            support = alt
    return good, caution, support


#: 같은 날 보드에서 한 도메인이 차지할 수 있는 good 헤드라인 상한(OA-6b).
#: **균등화가 아니다** — 유효한 대안이 있을 때만 독점을 완화한다.
_DOMAIN_HEADLINE_CAP = 0.30

#: 선택기 버전 — 결정론적 동점 처리의 마지막 tie-break 성분.
SELECTOR_VERSION = "oa6b_board_domain_cap_v1"


def _headline_candidates(
    good: _ScoredEvent, support: _ScoredEvent, caution: _ScoredEvent, band: str
) -> list[_ScoredEvent]:
    """이 카드에서 헤드라인이 될 수 있는 사건 — 점수 순.

    카드에 실제로 표시되는 3개 사건 안에서만 고른다. 표시되지 않는 사건을 헤드라인으로
    쓰면 "본문에 없는 이야기가 제목에 나오는" 불일치가 생긴다.

    `support` 슬롯 사건도 `headline_slots`에 `good`이 있으면 후보다(OA-6a). 슬롯 선발이
    보조를 가급적 다른 domain에서 뽑으므로, 이 목록은 대개 서로 다른 domain 2개가 된다 —
    보드 캡의 실질적 대안이 여기서 나온다.

    Args:
        good: good 슬롯 사건.
        support: 보조 슬롯 사건.
        caution: 주의 슬롯 사건.
        band: 점수 밴드.

    Returns:
        후보 목록(점수 내림차순). `s1`(최악 밴드)은 기존대로 주의 사건 단독.
    """
    if band == "s1":
        return [caution]   # 위험 우선 — 이번 슬라이스에서 caution 경로는 건드리지 않는다
    seen: set[str] = set()
    out: list[_ScoredEvent] = []
    for cand in (good, support):
        if cand.valence != "good" or "good" not in cand.headline_slots:
            continue
        if cand.event_key in seen:
            continue
        seen.add(cand.event_key)
        out.append(cand)
    if not out:
        out = [good]  # 자격 후보가 하나도 없으면 기존 동작 유지
    return sorted(out, key=lambda s: (-s.probability, s.event_key))


@dataclass(frozen=True)
class HeadlineDecision:
    """헤드라인 1건의 원시 선택과 최종 선택 — 감사 전용 기록(OA-7a)."""

    ilju: str
    band: str
    raw_event_key: str
    raw_domain: str
    raw_score: int
    selected_event_key: str
    selected_domain: str
    selected_score: int
    eligible_good_count: int
    eligible_cross_domain_count: int
    selection_reason: str = "raw_top"
    slot_source: str = "headline_slots"

    @property
    def displacement_cost(self) -> int:
        """교체로 잃은 점수 — 낮을수록 해석 적합성 희생이 적다."""
        return self.raw_score - self.selected_score


def _rebalance_headlines(
    decisions: dict[str, list[_ScoredEvent]], order: list[str], cap: float
) -> tuple[dict[str, _ScoredEvent], dict[str, str], int]:
    """보드 60건을 한 번에 보고 도메인 독점을 완화한다 (OA-6b).

    일주를 순서대로 훑으며 상한에 도달하면 이후를 막는 방식은 쓰지 않는다 — 갑자·을축처럼
    처리 순서가 빠른 일주가 좋은 후보를 선점하는 **일주 순서 편향**이 생긴다. 그래서
    전체 원시 선택을 먼저 확정한 뒤, **대체 비용이 가장 낮은 카드부터** 교체한다.

    유효한 대안이 없으면 상한을 넘겨도 그대로 둔다(조건부 제약). 다양성을 위해 근거가
    약한 사건을 억지로 올리지 않는다.

    Args:
        decisions: 일주 → 헤드라인 후보 목록(점수 순).
        order: 일주 처리 순서(결정론 고정용).
        cap: 도메인 점유 상한 비율.

    Returns:
        `(일주 → 최종 사건, 일주 → 교체 사유, 미해결 초과 건수)`.
    """
    selected = {ilju: cands[0] for ilju, cands in decisions.items()}
    reasons: dict[str, str] = {}
    limit = max(1, int(len(order) * cap))
    moved: set[str] = set()   # 한 번 옮긴 카드는 다시 옮기지 않는다(왕복 방지)
    guard = 0
    while guard < len(order):
        guard += 1
        counts: dict[str, int] = {}
        for ilju in order:
            dom = selected[ilju].domain
            counts[dom] = counts.get(dom, 0) + 1
        over = [(n - limit, dom) for dom, n in counts.items() if n > limit]
        if not over:
            break
        # 가장 많이 초과한 도메인부터(동수는 이름순 — 결정론).
        _, domain = max(over, key=lambda t: (t[0], t[1]))
        moves: list[tuple[int, str, str, _ScoredEvent]] = []
        for ilju in order:
            cur = selected[ilju]
            if cur.domain != domain or ilju in moved:
                continue
            # 목적지에 여유가 있는 후보만 — 옮긴 도메인이 다시 초과하면 두 도메인
            # 사이를 왕복하다 guard 에 걸려 "옮길 수 있는데 방치"가 된다.
            alt = next(
                (
                    c for c in decisions[ilju]
                    if c.domain != domain and counts.get(c.domain, 0) + 1 <= limit
                ),
                None,
            )
            if alt is None:
                continue
            # 점수 손실 → 일주 → event_key → selector_version 순 결정론 정렬.
            moves.append((cur.probability - alt.probability, ilju, alt.event_key, alt))
        if not moves:
            break   # 유효 대안 없음 — 초과를 허용하고 사유를 남긴다
        _, ilju, _, alt = min(moves, key=lambda m: (m[0], m[1], m[2], SELECTOR_VERSION))
        selected[ilju] = alt
        reasons[ilju] = "board_domain_cap"
        moved.add(ilju)
    counts_final: dict[str, int] = {}
    for ilju in order:
        dom = selected[ilju].domain
        counts_final[dom] = counts_final.get(dom, 0) + 1
    unresolved = sum(max(0, n - limit) for n in counts_final.values())
    return selected, reasons, unresolved


def _band(good: _ScoredEvent, caution: _ScoredEvent) -> str:
    """점수-문장 강도 연동 밴드 (PRD §11)."""
    if caution.probability - good.probability >= 15:
        return "s1"  # 주의 우세
    p = good.probability
    if p >= 85:
        return "s5"
    if p >= 70:
        return "s4"
    if p >= 55:
        return "s3"
    return "s2"


# ── 선택 계약 네임스페이스 (OA-6d1) ────────────────────────────────────────
#
# 선택 seed와 캐시 버전을 분리한다. 예전에는 `CONTENT_VERSION`(= DICT_VERSION 포함)이
# seed에 들어가 있어서 **문구 오타 하나만 고쳐도 사용자 3.7%의 오늘 사건이 바뀌었다**
# (실측). 표현을 고칠수록 사건이 흔들리는 구조라 서사 축을 넓힐수록 악화된다.
#
#     선택 seed    어떤 동점 후보를 고르는가   ← 선택 계약이 바뀔 때만 변경
#     캐시 키      현재 사전으로 만든 결과인가  ← DICT_VERSION 유지(무효화용)
#
#: 후보 동점 선택 계약. **기존 라이브 결과를 그대로 동결한다** — 값이 과거 콘텐츠
#: 버전 문자열인 것은 호환을 위한 것이며, 앞으로 DICT_VERSION 이 올라가도 바뀌지 않는다.
EVENT_SELECTION_CONTRACT = "event-selection.v1-legacy-frozen"
EVENT_SELECTION_COMPAT_SALT = "engine.v1|dict.v1.9|polish.v1"
#: 보드 재배정 계약 — 라이브. domain cap만 본다.
BOARD_REBALANCE_VERSION = "board-rebalance.v1-domain-only"
#: 보드 재배정 계약 — shadow. domain·event cap을 **동시에** 만족시킨다(OA-6c).
#: 라이브 상수를 그대로 v2로 바꾸면 캐시·감사 로그에서 두 경로의 의미가 섞인다.
BOARD_REBALANCE_SHADOW_VERSION = "board-rebalance.v2-domain-event-cap"
#: 서사 모드·family 선택 계약. 라이브 이력이 없어 처음부터 후보별 안정 해시를 쓴다.
NARRATIVE_SEED_VERSION = "narrative.v1"
#: 서사 회전 계약 (OA-8b) — 캐시 키와 같은 출처를 쓴다.
from saju_shared_types.daily_fortune import (  # noqa: E402
    NARRATIVE_ROTATION_VERSION,
)

#: 7일 회피를 날짜 서수만으로 보장하려면 후보가 8개 이상이어야 한다.
_ROTATION_MIN_RING = 8
#: 하위 호환 별칭(구 이름).
NARRATIVE_SCHEMA_VERSION = NARRATIVE_SEED_VERSION


def narrative_cycle(
    dicts: DailyFortuneDicts, event_key: str
) -> list[tuple[str, str]]:
    """사건의 `(mode, family)` 후보를 **안정 순서**로 편다 (OA-8b 회전 축).

    같은 mode의 family들이 인접하도록 mode → family 순으로 정렬한다. 회전이 한 칸씩
    움직이면 먼저 같은 mode 안에서 family가 바뀌고, 그 mode를 소진한 뒤 다음 mode로
    넘어간다 — "family 우선, mode 나중"이라는 계약이 순서 자체로 표현된다.

    정렬은 배열 순서가 아니라 정체성 해시로 한다(JSON 정렬 변경에 흔들리지 않게).
    """
    modes = (dicts.catalog["events"].get(event_key) or {}).get("narrative_modes")
    if not modes:
        return []

    def h(*parts: str) -> int:
        return _stable_hash("|".join((event_key, *parts, NARRATIVE_SEED_VERSION)))

    out: list[tuple[str, str]] = []
    for m in sorted(modes, key=lambda m: (h(str(m["mode"])), str(m["mode"]))):
        mode = str(m["mode"])
        fams = sorted(
            (str(f) for f in (m.get("template_families") or ())),
            key=lambda f: (h(mode, f), f),
        )
        out.extend((mode, f) for f in fams) if fams else out.append((mode, ""))
    return out


def resolve_narrative(
    dicts: DailyFortuneDicts, event_key: str, seed_base: str,
    day_ordinal: int | None = None, rotation_key: str = "",
    expression_scope: str = "general",
) -> tuple[str, str]:
    """이 카드가 쓸 서사 모드와 템플릿 family를 결정론적으로 고른다 (OA-8a·8b).

    같은 사건이라도 "무엇이 일어나는가"만 반복하지 않고 **어떤 서사 기능으로 말할지**를
    돌린다 — 사건을 늘려도 문장 재사용률이 80%에서 거의 내려가지 않았고, 원인이 사건
    수가 아니라 사건당 표현 공간이었기 때문이다.

    **OA-8b 회전**: `day_ordinal`을 주면 날짜마다 후보를 한 칸씩 밀어 고른다. 같은 일주가
    같은 사건을 연달아 받아도 family가 달라진다. 과거 이력을 조회하지 않는 이유는 그것이
    7일치 보드 재계산(약 7배 비용)을 요구하고, 휘발성 불변식(과거 본문 미저장)과도
    충돌하기 때문이다. 순환은 이력 조회 없이 같은 목적을 달성한다:

        연속 등장  → 다음 칸 → 반드시 다른 family(후보가 2개 이상이면)
        재등장 주기 → 후보 수만큼 순환 후에야 같은 family 재사용

    출발점은 일주·사건별 안정 해시라 모든 일주가 같은 날 같은 family를 쓰지 않는다.

    Args:
        dicts: 사전 묶음.
        event_key: 확정된 사건 키(이 함수가 바꾸지 않는다).
        seed_base: 날짜·일주·선택 계약이 섞인 결정론 seed 기반 문자열(회전 미사용 시).
        day_ordinal: 날짜 서수. None이면 회전 없이 OA-8a 방식으로 고른다.
        rotation_key: **날짜가 들어가지 않는** 회전 출발점(일주). 날짜가 섞이면 출발점이
            매일 달라져 순환이 무작위 재추첨으로 무너진다.
        expression_scope: 표현 범위(`general`·`romantic`). 범위별로 순환군을 나눈다.

    Returns:
        `(mode, family)`. 서사 축이 없는 사건은 `("", "")` — 기존 평면 템플릿을 쓴다.
    """
    cycle = narrative_cycle(dicts, event_key)
    if not cycle:
        return "", ""
    if day_ordinal is None:
        offset = _stable_hash(
            "|".join((seed_base, event_key, NARRATIVE_ROTATION_VERSION))
        )
        return cycle[offset % len(cycle)]
    # 표현 범위별로 순환군을 나눈다 — 일반 관계형 이력이 연애형 선택을 왜곡하면 안 된다.
    offset = _stable_hash(
        "|".join(
            (rotation_key, event_key, expression_scope, NARRATIVE_ROTATION_VERSION)
        )
    )
    return cycle[(day_ordinal + offset) % len(cycle)]


def rotation_ring_status(dicts: DailyFortuneDicts, event_key: str) -> str:
    """이 사건이 7일 회피를 날짜 서수만으로 보장할 수 있는가.

    후보가 `_ROTATION_MIN_RING` 미만이면 hard guarantee 가 불가능하다 — 숨기지 않고
    사유를 남긴다(사전에서 family 를 줄이면 여기서 드러난다).

    Returns:
        보장 가능하면 빈 문자열, 아니면 `insufficient_eligible_families`.
    """
    ring = narrative_cycle(dicts, event_key)
    if not ring:
        return ""   # 서사 축이 없는 사건은 회전 대상이 아니다
    return "" if len(ring) >= _ROTATION_MIN_RING else "insufficient_eligible_families"


def _headline(
    dicts: DailyFortuneDicts,
    event_key: str,
    band: str,
    seed_base: str,
    salt: int,
    romance_scope: bool = False,
    rotation_key: str = "",
    day_ordinal: int | None = None,
) -> str:
    """오늘의 한마디 — fragment + action (+ result) 조합, 결정론 seed.

    당일 중복 감사에서 salt 가 커질수록 범용(generic) 풀을 합쳐 조합 공간을
    넓힌다(같은 사건을 공유하는 일주가 많아도 완전 중복이 나지 않도록).

    서사 family가 있으면 그 family의 문장 풀을 쓴다(OA-8a) — 사건은 그대로 두고
    장면·행동·결과만 다른 서사 기능으로 바꾼다.

    Args:
        romance_scope: 연애 전용 신호가 **강할 때만** True. 관계 계열 사건의 기본
            표현은 일반 관계(대화·접점)이고, 연애 맥락은 이 게이트를 통과한 카드에서만
            쓴다 — 상대의 존재·행동·마음을 전제하지 않기 위해서다.
    """
    generic_kind = "caution" if band == "s1" else "good"
    generic = dicts.templates["generic"][generic_kind]
    tpl = dicts.templates["events"].get(event_key) or generic
    _mode, family = resolve_narrative(
        dicts, event_key, seed_base,
        day_ordinal=day_ordinal, rotation_key=rotation_key,
        expression_scope="romantic" if romance_scope else "general",
    )
    if family:
        fam = (tpl.get("families") or {}).get(family)
        if fam:
            # 연애 변형은 게이트를 통과한 카드에만. 없으면 일반 관계형을 그대로 쓴다.
            tpl = fam.get("romantic") or fam if romance_scope else fam
    fragments = list(tpl["fragments"])
    actions = list(tpl["actions"])
    results = list(tpl["results"])
    if salt >= 3:  # 중복 지속 시 행동 풀 확장
        actions += generic["actions"]
        results += generic["results"]
    if salt >= 6:  # 그래도 중복이면 사건 풀까지 확장
        fragments += generic["fragments"]
    s = _stable_hash(f"{seed_base}|headline|{salt}")
    parts = [_pick(fragments, s), _pick(actions, s // 7)]
    if band in ("s5", "s4", "s1") or salt >= 3:
        parts.append(_pick(results, s // 31))
    return " ".join(parts)


def _love_pick(scored: list[_ScoredEvent]) -> tuple[_ScoredEvent | None, str]:
    """오늘의 연애 대표 신호 선택 + 강한 신호 게이트 — (pick, band).

    good이 우세(good.activation ≥ caution.activation − 0.1)하면 good 사건, caution만
    뚜렷하면 caution 사건을 대표로 고른다. 대표가 서로 다른 독립 원인 그룹
    ≥`_LOVE_LINE_MIN_SUPPORT`개의 지지를 받지 못하면 (None, "s3") — 강한 love 전용
    신호가 아니므로 별도 노출·Top5 우선 대상이 아니다. `_love_line`(문장)과 love Top5
    우선 정렬이 동일 판정을 쓰도록 한 곳에 둔다(로직 드리프트 방지).
    """
    goods = sorted((s for s in scored if s.domain == "love" and s.valence == "good"),
                   key=lambda s: s.activation, reverse=True)
    cautions = sorted(
        (s for s in scored if s.domain == "love" and s.valence == "caution"),
        key=lambda s: s.activation, reverse=True)
    best_good = goods[0] if goods else None
    best_caution = cautions[0] if cautions else None
    # 대표 신호 선택 — caution이 뚜렷이 우세할 때만 caution, 아니면 good 우선.
    pick = None
    band = "s3"
    if best_good and (not best_caution
                      or best_good.activation >= best_caution.activation - 0.1):
        pick, band = best_good, ("s4" if best_good.activation >= 0.5 else "s3")
    elif best_caution and best_caution.activation >= 0.25:
        pick, band = best_caution, "s1"
    # 강한 신호 게이트: 독립 원인 그룹 지지가 부족하면 대표 신호 없음으로 본다.
    if pick is None or pick.supporting_groups < _LOVE_LINE_MIN_SUPPORT:
        return None, "s3"
    return pick, band


def _has_good_love_signal(scored: list[_ScoredEvent]) -> bool:
    """게이트를 통과한 good 오늘의 연애 신호가 있는지 — love Top5 우선 정렬용."""
    pick, _ = _love_pick(scored)
    return pick is not None and pick.valence == "good"


def _love_line(
    dicts: DailyFortuneDicts, scored: list[_ScoredEvent], seed_base: str
) -> str | None:
    """일일 연애운 한 줄(확장·beta) — 강한 love 전용 신호가 있을 때만 노출.

    대표 신호 선택·게이트는 `_love_pick`에 위임한다. 게이트 미통과면 총운 헤드라인이
    이미 그날을 커버하므로 별도 '오늘의 연애' 줄을 만들지 않는다(None). 발생≠확정 —
    '오늘의 연애 흐름'만 서술한다.
    """
    pick, band = _love_pick(scored)
    if pick is None:
        return None
    # 기존 문장 조합 machinery 재사용(스타일·중복 회피 동일). love seed로 분리.
    return _headline(dicts, pick.event_key, band, seed_base + "|love", 0)


def _lucky_place(
    dicts: DailyFortuneDicts, domain: str, seed_base: str, salt: int
) -> LuckyPlace:
    """행운의 장소 선택 — domain="__any__" 면 전체 풀(과다 노출 시 확장용)."""
    places = dicts.places["places"]
    if domain == "__any__":
        candidates = list(places)
    else:
        candidates = [k for k, v in places.items() if domain in v["domains"]] or list(places)
    s = _stable_hash(f"{seed_base}|place|{salt}")
    key = candidates[s % len(candidates)]
    phrase_tpl = _pick(dicts.templates["place_phrases"], s // 13)
    name = places[key]["name"]
    return LuckyPlace(place_key=key, name=name, phrase=phrase_tpl.format(place=name))


def _domain_score(scored: list[_ScoredEvent], domain: str) -> float:
    """Top5 정규화 점수 — 사건 개수 비의존(대표 사건 기준), 빈 후보=0."""
    goods = sorted(
        (s.activation for s in scored if s.domain == domain and s.valence == "good"),
        reverse=True,
    )
    cautions = [s.activation for s in scored if s.domain == domain and s.valence == "caution"]
    top = goods[0] if goods else 0.0
    second = goods[1] if len(goods) > 1 else 0.0
    worst = max(cautions) if cautions else 0.0
    return top + 0.3 * second - 0.5 * worst


def _lotto_slot_open(d: date, ilju_index: int) -> bool:
    """이력 저장 없는 일주별 로또 쿨다운 — date-ordinal 슬롯(주 1회 이하)."""
    return (d.toordinal() + ilju_index) % 7 == 0


def compute_board(
    ctx: DayGanjiContext, dicts: DailyFortuneDicts,
    selection_override: Mapping[str, Mapping[str, str]] | None = None,
    scored_rows: Mapping[str, list[_ScoredEvent]] | None = None,
) -> DailyFortuneBoard:
    """60일주 전체 보드를 산출한다(결정론 — 동일 입력이면 동일 출력).

    1패스: 일주별 사건 점수·도메인 점수 → Top5·금전 순위 확정.
    2패스: 로또 게이트·문장 조합·당일 중복 감사.

    Args:
        selection_override: 일주 → {"good","support","caution","final_headline"}.
            주어지면 **슬롯 선발과 보드 재배정을 건너뛰고** 그 선택을 그대로 쓴다
            (`_select_slots`·`_headline_candidates`·`_rebalance_headlines` 미호출).
            베타 pool snapshot 을 선택의 SSOT 로 쓰는 렌더링 경로 전용이며,
            None 이면 라이브 거동이 바이트 단위로 동일하다.
        scored_rows: 일주(한자 2자) → 채점 결과 목록. 주어지면 v1 `_score_event`
            패스를 건너뛰고 이 후보 풀을 그대로 쓴다 — 3층 판정 모델(v2,
            `daily_fortune_v2.compute_board_v2`)이 선발·렌더 파이프라인을 재사용하는
            주입 지점. None 이면 라이브 거동이 바이트 단위로 동일하다.
    """
    d = ctx.the_date
    per_ilju: list[dict[str, Any]] = []
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ilju = f"{stem.value}{branch.value}"
        if scored_rows is not None:
            scored = list(scored_rows[ilju])
        else:
            scored = [
                _score_event(key, ev, stem, branch, ctx)
                for key, ev in dicts.catalog["events"].items()
            ]
        per_ilju.append({
            "index": idx,
            "stem": stem,
            "branch": branch,
            "ilju": ilju,
            "scored": scored,
        })

    # Top5 (금전/연애/좋은소식) + 금전 순위
    def _ranked(domain: str) -> list[dict[str, Any]]:
        return sorted(
            per_ilju,
            key=lambda row: (
                -_domain_score(row["scored"], domain),
                _stable_hash(f"{d.isoformat()}|{domain}|{row['ilju']}") % 9973,
            ),
        )

    # 연애 Top5는 '오늘의 연애'(good) 게이트 통과 일주를 우선 배치한다(docs/17 §49).
    # good love_line 이 뜨는데 동반 caution 감점으로 Top5 밖으로 밀리는 불일치를 제거 —
    # 그 안·뒤 순서는 종전 domain_score 그대로. domain_score 공식·타 도메인 Top5·로또
    # 순위는 불변(love 랭킹만 재정렬).
    def _love_ranked() -> list[dict[str, Any]]:
        return sorted(
            per_ilju,
            key=lambda row: (
                0 if _has_good_love_signal(row["scored"]) else 1,
                -_domain_score(row["scored"], "love"),
                _stable_hash(f"{d.isoformat()}|love|{row['ilju']}") % 9973,
            ),
        )

    money_ranked = _ranked("money")
    top5 = DailyTop5(
        money=[row["ilju"] for row in money_ranked[:5]],
        love=[row["ilju"] for row in _love_ranked()[:5]],
        news=[row["ilju"] for row in _ranked("news")[:5]],
    )

    # 로또 적격 — 순위 기준 결정론 선택, 당일 최대 3개 (PRD §12)
    lotto_iljus: set[str] = set()
    for row in money_ranked[:_LOTTO_MAX_MONEY_RANK]:
        if len(lotto_iljus) >= _LOTTO_MAX_PER_DAY:
            break
        money_goods = [
            s for s in row["scored"]
            if s.domain == "money" and s.valence == "good"
        ]
        money_cautions = [
            s.activation for s in row["scored"]
            if s.domain == "money" and s.valence == "caution"
        ]
        best_p = max((s.probability for s in money_goods), default=0)
        weak_loss = max(money_cautions, default=0.0) < 0.35
        if (
            best_p >= _LOTTO_MIN_MONEY_P
            and weak_loss
            and _lotto_slot_open(d, row["index"])
        ):
            lotto_iljus.add(row["ilju"])

    # 2패스 — 슬롯 선발(전 일주) → 보드 단위 도메인 캡 → 문장 생성
    # 순서가 중요하다: 60건 후보를 모두 확정한 뒤에 재배정해야 일주 순서 편향이 없다.
    slot_rows: dict[str, tuple[_ScoredEvent, _ScoredEvent, _ScoredEvent, str]] = {}
    candidates: dict[str, list[_ScoredEvent]] = {}
    order: list[str] = []
    for row in per_ilju:
        ilju = row["ilju"]
        # 선택 seed 는 콘텐츠 버전과 분리한다(OA-6d1) — 문구 수정이 사건을 흔들지 않게.
        seed_base = f"{d.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        if selection_override is not None:
            by_key = {s.event_key: s for s in row["scored"]}
            pick = selection_override[ilju]
            good = by_key[pick["good"]]
            support = by_key[pick["support"]]
            caution = by_key[pick["caution"]]
            band = pick.get("band") or _band(good, caution)
            slot_rows[ilju] = (good, caution, support, band)
            candidates[ilju] = [by_key[pick["final_headline"]]]
        else:
            good, caution, support = _select_slots(row["scored"], seed_base)
            band = _band(good, caution)
            slot_rows[ilju] = (good, caution, support, band)
            candidates[ilju] = _headline_candidates(good, support, caution, band)
        order.append(ilju)

    if selection_override is not None:
        # 보드 재배정을 실행하지 않는다 — snapshot 이 이미 최종 헤드라인을 정했다.
        headline_pick = {k: v[0] for k, v in candidates.items()}
        cap_reasons: dict[str, str] = {}
        cap_unresolved = 0
    else:
        headline_pick, cap_reasons, cap_unresolved = _rebalance_headlines(
            candidates, order, _DOMAIN_HEADLINE_CAP
        )
    headline_audit: list[HeadlineDecision] = []

    fortunes: list[DailyIljuFortune] = []
    used_headlines: set[str] = set()
    place_counts: dict[str, int] = {}
    for row in per_ilju:
        ilju = row["ilju"]
        # 선택 seed 는 콘텐츠 버전과 분리한다(OA-6d1) — 문구 수정이 사건을 흔들지 않게.
        seed_base = f"{d.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        good, caution, support, band = slot_rows[ilju]
        raw_event = candidates[ilju][0]
        headline_event = headline_pick[ilju]
        cross = {c.domain for c in candidates[ilju]} - {raw_event.domain}
        headline_audit.append(
            HeadlineDecision(
                ilju=ilju, band=band,
                raw_event_key=raw_event.event_key, raw_domain=raw_event.domain,
                raw_score=raw_event.probability,
                selected_event_key=headline_event.event_key,
                selected_domain=headline_event.domain,
                selected_score=headline_event.probability,
                eligible_good_count=len(candidates[ilju]),
                eligible_cross_domain_count=len(cross),
                selection_reason=cap_reasons.get(ilju, "raw_top"),
            )
        )

        # 연애 표현 게이트 — 기존 '오늘의 연애' 신호(독립 원인 그룹 ≥3)를 재사용한다.
        # 새 점수를 만들지 않고 **표현 범위만** 좁힌다.
        romance_scope = _has_good_love_signal(row["scored"])
        headline = ""
        for salt in range(_DUP_RETRY):  # 당일 60건 내 완전 중복 회피
            headline = _headline(
                dicts, headline_event.event_key, band, seed_base, salt,
                romance_scope=romance_scope,
                # OA-8b 회전 — 날짜 서수로 후보를 한 칸씩 민다(일주가 출발점).
                rotation_key=ilju, day_ordinal=d.toordinal(),
            )
            if headline not in used_headlines:
                break
        used_headlines.add(headline)

        place: LuckyPlace | None = None  # 같은 장소 과다 노출 방지 — 상한 도달 시 전체 풀 확장
        for salt in range(_DUP_RETRY):
            domain_arg = headline_event.domain if salt < 5 else "__any__"
            cand = _lucky_place(dicts, domain_arg, seed_base, salt)
            if place_counts.get(cand.place_key, 0) < _PLACE_MAX_REPEAT:
                place = cand
                break
        if place is None:  # 모든 후보가 상한이면 마지막 후보 사용(60건 내 도달 불가 방어선)
            place = cand
        place_counts[place.place_key] = place_counts.get(place.place_key, 0) + 1

        catalog_events = dicts.catalog["events"]
        events = [
            DailyEventForecast(
                slot=slot_name,
                event_key=s.event_key,
                domain=s.domain,
                probability=s.probability,
                phrase=catalog_events[s.event_key]["label"],
            )
            for slot_name, s in (("good", good), ("caution", caution), ("support", support))
        ]
        lotto = None
        if ilju in lotto_iljus:
            lotto = _pick(
                dicts.templates["lotto_phrases"],
                _stable_hash(f"{seed_base}|lotto"),
            )
        love_line = _love_line(dicts, row["scored"], seed_base)
        fortunes.append(
            DailyIljuFortune(
                ilju=ilju,
                ilju_ko=f"{STEM_KO[row['stem']]}{BRANCH_KO[row['branch']]}",
                day_stem_ko=STEM_KO[row["stem"]],
                headline=headline,
                headline_event_key=headline_event.event_key,
                events=events,
                lucky_place=place,
                lotto_phrase=lotto,
                love_line=love_line,
            )
        )

    board = DailyFortuneBoard(
        fortune_date=d,
        weekday=d.weekday(),
        weekday_ko=_WEEKDAY_KO[d.weekday()],
        # 보드가 실제로 쓴 계약을 찍는다 — 전역 상수를 찍으면 과거 날짜 보드가
        # 새 계약으로 만들어진 것처럼 보인다(OA-6a2).
        content_version=content_version_for(d),
        polish_status="RAW",
        top5=top5,
        fortunes=fortunes,
    )
    # 감사 기록은 응답 모델을 바꾸지 않는다 — 캐시·API 계약 불변(OA-7a).
    object.__setattr__(board, "_headline_audit", tuple(headline_audit))
    object.__setattr__(board, "_cap_unresolved", cap_unresolved)
    return board
