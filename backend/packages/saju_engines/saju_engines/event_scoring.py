"""Event Scoring 보조 함수 (v2.2 Phase 7 하드 스위치 이후 — 헬퍼 전용).

구 사전 기반 EventScorer는 제거되고 점수 산출은 `event_engine_v2.EventEngineV2`(재설계 6계층 +
거버닝 스택)가 담당한다. 본 모듈에는 다운스트림이 공유하는 순수 헬퍼만 남긴다:
용신 오행→역할 매핑(favorability_map/_from_model), 세운 계층 필터(filter_year_candidates),
대운 교운기 영향도(daewoon_transition_weight). LLM은 이 계산에 관여하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

import math
from datetime import date

from saju_shared_types.constants import CONTROLS, GENERATES
from saju_shared_types.enums import Element
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.yongsin import YongsinCandidateModel

# ── 교운기 영향도 모델 (사용자 실측: 교운일 중심 뾰족한 분포가 유효) ──
DAEWOON_TRANSITION_BETA = 1.0  # 일반화 정규분포 지수 — 1.0=라플라스형(첨도↑)
DAEWOON_TRANSITION_SCALE_DAYS = 365.0  # 영향 반경 스케일(일)
DAEWOON_TRANSITION_MIN_WEIGHT = 0.05  # 이 미만이면 교운 신호 미적용
# 교운 가중 배율 강도(α) — 전환성 이벤트 raw에 (1 + α·weight)를 곱한다. 구 EventScorer의
# daewoonTransition 신호 가중이 21키 재설계(EventEngineV2)에서 누락된 회귀를 복원한 것
# (2026-06-23 사용자 확정). α↑ = 교운일 근접 달의 변별이 강해진다.
DAEWOON_TRANSITION_BOOST_ALPHA = 1.0

# 전환성 이벤트 — 대운 교체(교운)의 비자발적·환경적 '새 국면 진입'에 민감한 사건군.
# 교운일 근접 시에만 교운 가중을 받는다. 진행형(승진·사업확장)·재물·계약·갈등·건강·창작 등
# 대운 전환과 무관한 키는 제외한다(2026-06-23 사용자 확정 집합).
TRANSITIONAL_EVENT_KEYS: frozenset[EventKeyV2] = frozenset({
    EventKeyV2.CAREER_CHANGE,
    EventKeyV2.JOB_GAIN,
    EventKeyV2.BUSINESS_START,
    EventKeyV2.RELOCATION,
    EventKeyV2.NEW_RELATIONSHIP,
    EventKeyV2.MARRIAGE_SIGNAL,
    EventKeyV2.RELATIONSHIP_CHANGE,
    EventKeyV2.CHILDBIRTH,
    EventKeyV2.EDUCATION_ADMISSION,
})

# 계층 필터(docs/02): 세운은 score>=70 또는 상위 5건만 다음 단계로.
YEAR_SCORE_THRESHOLD = 70
YEAR_TOP_N = 5

_FAV_ROLES = (
    ("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
    ("gusin", "구신"), ("hansin", "한신"),
)


def daewoon_transition_weight(
    target: date,
    jiao_dates: list[date],
    *,
    beta: float = DAEWOON_TRANSITION_BETA,
    scale_days: float = DAEWOON_TRANSITION_SCALE_DAYS,
) -> float:
    """교운일 중심의 첨도 높은 정규분포형 영향도(0~1).

    가장 가까운 교운일과의 일수 차 d에 대해 ``exp(-(d/scale)^beta)``.
    beta=2면 표준 정규형, beta<2면 더 뾰족(leptokurtic) — 기본 1.0.
    """
    if not jiao_dates:
        return 0.0
    nearest = min(abs((target - jd).days) for jd in jiao_dates)
    return math.exp(-((nearest / scale_days) ** beta))


def daewoon_transition_boost(
    raw: float,
    target: date,
    jiao_dates: list[date],
    event_key: EventKeyV2,
    *,
    alpha: float = DAEWOON_TRANSITION_BOOST_ALPHA,
) -> tuple[float, float]:
    """전환성 이벤트 raw 점수에 교운일 근접 곱셈 배율을 적용한다(구 엔진 가중 복원).

    event_key가 전환성 이벤트(TRANSITIONAL_EVENT_KEYS)이고 가장 가까운 교운일과의 근접도
    weight(daewoon_transition_weight)가 MIN_WEIGHT 이상이면 ``raw × (1 + alpha·weight)``를,
    그 외에는 raw를 그대로 반환한다. 사건 종류·극성은 바꾸지 않고 점수(발생 강도)만 보정한다.

    Returns:
        (보정된 raw, 적용된 weight). 미적용 시 (raw, 0.0).
    """
    if event_key not in TRANSITIONAL_EVENT_KEYS or not jiao_dates:
        return raw, 0.0
    weight = daewoon_transition_weight(target, jiao_dates)
    if weight < DAEWOON_TRANSITION_MIN_WEIGHT:
        return raw, 0.0
    return raw * (1.0 + alpha * weight), weight


def favorability_map(result: ManseV2Result) -> dict[str, str]:
    """용신 분석 final → 오행(한자) → 역할(용신/희신/기신/구신/한신) 매핑."""
    if result.yongsin_analysis is None:
        return {}
    final = result.yongsin_analysis.final
    out: dict[str, str] = {}
    for key, ko in _FAV_ROLES:
        element = final.get(key)
        if isinstance(element, str) and element:
            out[element] = ko
    return out


# ── 사용자 확정 용신 → 용희기구한 5역할 도출(생극 순환, candidates._classify_roles와 동일 규칙) ──
# 사용자가 용신 확정 질문으로 용신을 바꾸면 희·기·구·한도 그 용신 기준으로 함께 재도출해야
# 같은 오행이 두 역할에 중복되지 않는다(2026-06-23 사용자 지적). 엔진 최초 도출값(확정 전 후보
# 상태 = yongsin_analysis.final)은 호출부가 비파괴로 보존하며, 여기서는 확정값의 override만 만든다.
_ELEMENT_ALIASES: dict[str, str] = {
    "木": "木", "火": "火", "土": "土", "金": "金", "水": "水",
    "목": "木", "화": "火", "토": "土", "금": "金", "수": "水",
    "wood": "木", "fire": "火", "earth": "土", "metal": "金", "water": "水",
}


def normalize_element(value: str | None) -> str | None:
    """확정 용신 입력(한자/한글/영문)을 한자 오행(木火土金水)으로 정규화. 미상이면 None."""
    if not value:
        return None
    v = value.strip()
    return _ELEMENT_ALIASES.get(v) or _ELEMENT_ALIASES.get(v.lower())


def classify_yongsin_roles(yongsin: str) -> dict[str, str]:
    """확정 용신(한자 오행) → 용희기구한 5역할 오행 1:1 배정(생극 순환 — 중복 없음).

    기신=극용신, 희신=생용신, 구신=생기신, 한신=용신이 생하는 오행. 통관·종격 같은 특수
    배정은 다루지 않는다(사용자 확정은 표준 억부식 생극 분할로 본다).
    """
    y = Element(yongsin)
    gisin = next(x for x in Element if CONTROLS[x] == y)        # 극용신
    heesin = next(x for x in Element if GENERATES[x] == y)      # 생용신
    gusin = next(x for x in Element if GENERATES[x] == gisin)   # 생기신
    hansin = GENERATES[y]                                       # 용신이 생
    return {
        "yongsin": str(y), "heesin": str(heesin), "gisin": str(gisin),
        "gusin": str(gusin), "hansin": str(hansin),
    }


def confirmed_favorability_override(yongsin: str) -> dict[str, str]:
    """확정 용신 → {오행(한자): 역할(한글)} fav_override (favorability_map과 동일 포맷)."""
    roles = classify_yongsin_roles(yongsin)
    return {roles[key]: ko for key, ko in _FAV_ROLES if roles.get(key)}


def confirmed_yongsin_note(result: ManseV2Result, confirmed_element: str) -> str:
    """확정 용신 적용 안내 — 확정 5역할을 풀이 기준으로, 엔진 최초 도출은 기본값으로 병기.

    확정 용신이 엔진 도출 용신과 같으면 빈 문자열(변경 없음).
    """
    base_map = favorability_map(result)  # {오행: 역할(한글)} — 엔진 최초 도출(확정 전 후보)
    base_by_role = {ko: el for el, ko in base_map.items()}
    if base_by_role.get("용신") == confirmed_element:
        return ""
    confirmed = classify_yongsin_roles(confirmed_element)
    conf_fmt = "·".join(f"{ko} {confirmed.get(key, '?')}" for key, ko in _FAV_ROLES)
    base_fmt = "·".join(f"{ko} {base_by_role.get(ko, '?')}" for _key, ko in _FAV_ROLES)
    return (
        f"[용신 — 사용자 확정 적용] 이 풀이는 확정 용신 '{confirmed_element}'를 기준으로 한다: "
        f"{conf_fmt}. (엔진 최초 도출(확정 전 후보)은 {base_fmt} — 기본값·되돌림 기준이며, "
        f"원국 블록의 용신 표기보다 이 확정 용신을 우선해 길흉을 판단할 것.)"
    )


def favorability_map_from_model(model: YongsinCandidateModel) -> dict[str, str]:
    """후보 모델의 용희기구한 배정 → 오행→역할 매핑(용신 검증의 모델별 이벤트 재계산용).

    favorability_map과 동일 라벨 체계. 모델이 일부 역할을 비워 두면 그 역할은 매핑에서 제외된다.
    """
    out: dict[str, str] = {}
    for key, ko in _FAV_ROLES:
        element = getattr(model, key, None)
        if isinstance(element, str) and element:
            out[element] = ko
    return out


def filter_year_candidates(candidates: list[EventCandidate]) -> list[EventCandidate]:
    """계층 필터(docs/02): 세운 후보는 score≥70 또는 연도 무관 Top5만 통과.

    월운/일운/대운 후보는 그대로 통과한다(월운 노출 제한은 오케스트레이터 담당).
    """
    years = [c for c in candidates if _is_year_period(c.period)]
    kept_ids = {id(c) for c in years if c.score >= YEAR_SCORE_THRESHOLD}
    kept_ids |= {id(c) for c in sorted(years, key=lambda c: -c.score)[:YEAR_TOP_N]}
    return [c for c in candidates if not _is_year_period(c.period) or id(c) in kept_ids]


def _is_year_period(period: str) -> bool:
    """'2026' 형태(세운 라벨)인지 판별."""
    return len(period) == 4 and period.isdigit()
