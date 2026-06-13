"""Event Scoring 보조 함수 (v2.2 Phase 7 하드 스위치 이후 — 헬퍼 전용).

구 사전 기반 EventScorer는 제거되고 점수 산출은 `event_engine_v2.EventEngineV2`(재설계 6계층 +
거버닝 스택)가 담당한다. 본 모듈에는 다운스트림이 공유하는 순수 헬퍼만 남긴다:
용신 오행→역할 매핑(favorability_map/_from_model), 세운 계층 필터(filter_year_candidates),
대운 교운기 영향도(daewoon_transition_weight). LLM은 이 계산에 관여하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

import math
from datetime import date

from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.yongsin import YongsinCandidateModel

# ── 교운기 영향도 모델 (사용자 실측: 교운일 중심 뾰족한 분포가 유효) ──
DAEWOON_TRANSITION_BETA = 1.0  # 일반화 정규분포 지수 — 1.0=라플라스형(첨도↑)
DAEWOON_TRANSITION_SCALE_DAYS = 365.0  # 영향 반경 스케일(일)
DAEWOON_TRANSITION_MIN_WEIGHT = 0.05  # 이 미만이면 교운 신호 미적용

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
