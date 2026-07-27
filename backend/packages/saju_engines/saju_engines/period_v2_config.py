"""총운 경로 V2 설정 — 플래그·버전 태그·운주 가중 (2026-07-27 데굴님 확정).

적용 범위(승인): **총운 경로 전체**(일운·월 총운·연 총운 + 토픽 M15)와 그 경로의
계층형 grounding·도메인 슬롯 점수. 사건 후보 생성·순위, 결혼/이직/재물 이벤트 엔진,
리포트, 기존 사전계산 결과, 다른 intent의 점수 체계는 **미적용**이다.

플래그 규약: 기존 beta 관례(`.env.beta`, import 시점 상수)를 따른다. 기본값은 전부
False라 파일이 없으면 기존 출력이 byte 단위로 보존되고 pytest의 OFF 기준 회귀가
오염되지 않는다. 운영 적용은 `.env.beta`에 값을 넣고 재기동한다(무중단 토글 아님).

생성 파이프라인(2026-07-27 데굴님 확정 — 재생성 철회): **LLM은 요청당 1회만 호출한다.**
엔진 사실은 canonical claim으로 미리 제공하고, 생성 후 의미 역전은 해당 문장만
결정론적으로 교체한다. 전체 구조가 불완전하면 추가 LLM 호출 대신 서버 템플릿으로
조립한다. 유료 Q&A 서비스에서 재생성을 기본 안전장치로 두면 사용자 비용과 서버 원가를
동시에 늘리는데, 이 문제는 창작이 아니라 엔진 확정값 반영으로 풀리는 문제다.
"""

from __future__ import annotations

import logging
import os


class ConfigurationError(RuntimeError):
    """플래그 조합이 무효일 때 기동을 차단하는 예외."""


def _env_flag(name: str) -> bool:
    """환경변수 → bool(미설정은 False)."""
    return os.environ.get(name, "false").strip().lower() in ("1", "true", "yes")


# ── 플래그 ────────────────────────────────────────────────────────────────
# P0 관계 의미 패치 — canonical claim 제공 + 생성 후 역전 문장의 결정론적 교체.
# 운영에서는 사실상 항상 켠다. 끄면 엔진 모순이 그대로 사용자에게 노출된다.
RELATION_SEMANTIC_PATCH_ENABLED: bool = _env_flag("SAJU_RELATION_SEMANTIC_PATCH_ENABLED")
# P1·P2 계층형 grounding — 상위 운 결합·층간 충·연월일 역할 요약.
PERIOD_HIERARCHY_ENABLED: bool = _env_flag("SAJU_PERIOD_HIERARCHY_ENABLED")
# P3 신호 polarity V2 — 부호를 운주 라벨이 아니라 관계 결과에서 도출.
PILLAR_POLARITY_V2_ENABLED: bool = _env_flag("SAJU_PILLAR_POLARITY_V2_ENABLED")
# 패치로도 복구가 안 될 때 엔진 데이터만으로 조립한 안전 템플릿을 쓴다(추가 LLM 호출 없음).
SAFE_TEMPLATE_FALLBACK_ENABLED: bool = _env_flag("SAJU_SAFE_TEMPLATE_FALLBACK_ENABLED")

# ── 버전 태그(계측·회귀 비교용) ─────────────────────────────────────────────
FORTUNE_LOGIC_VERSION = "period_hierarchy_v2"
RELATION_SEMANTICS_VERSION = "relation_semantics_v1"
PILLAR_ROLE_VERSION = "stem40_branch60_v1"
SIGNAL_POLARITY_VERSION = "interaction_owned_v1"

# ── 운주 천간·지지 가중 ────────────────────────────────────────────────────
# 전 층위 공통 초기값(데굴님 확정) — 월운만 0.35/0.65로 두는 예외는 두지 않는다.
# 이 값은 **점수에 쓰지 않는다**: 연·월·일 계층 요약, 같은 층위 내 정렬, LLM grounding
# 전용이다. 점수에 쓰면 신호 polarity와 용희기구한 정보가 이중 반영된다(데굴님 확정).
# 사용자 피드백으로는 0.40과 0.35를 변별할 수 없으므로 튜닝 파라미터가 아니라 다음
# 버전까지 고정된 정책값으로 취급한다.
PILLAR_ROLE_WEIGHT: dict[str, float] = {"stem": 0.40, "branch": 0.60}


def validate_flags() -> None:
    """플래그 조합 불변식 — 무효 조합이면 기동을 차단하고, 위험 조합은 경고한다.

    점수만 V2인데 설명은 V1 계층 구조를 쓰면 서술과 점수가 다시 어긋나므로,
    polarity V2는 계층형 grounding을 반드시 동반해야 한다.

    Raises:
        ConfigurationError: polarity V2가 계층형 grounding 없이 켜진 경우.
    """
    if PILLAR_POLARITY_V2_ENABLED and not PERIOD_HIERARCHY_ENABLED:
        raise ConfigurationError(
            "SAJU_PILLAR_POLARITY_V2_ENABLED는 SAJU_PERIOD_HIERARCHY_ENABLED를 "
            "함께 켜야 한다 — 점수만 V2이고 설명이 V1이면 서술과 점수가 어긋난다."
        )
    if RELATION_SEMANTIC_PATCH_ENABLED and not SAFE_TEMPLATE_FALLBACK_ENABLED:
        # 안전 템플릿은 비용 기능이 아니라 사실 오류를 막는 최종 안전장치다. 재호출
        # 비용도 없으므로 개별로 끌 실익이 없다(2026-07-27 데굴님 확정).
        raise ConfigurationError(
            "SAJU_RELATION_SEMANTIC_PATCH_ENABLED는 SAJU_SAFE_TEMPLATE_FALLBACK_ENABLED를 "
            "함께 켜야 한다 — 패치 실패 시 미교정 모순이 그대로 전달된다."
        )
    if PERIOD_HIERARCHY_ENABLED and not RELATION_SEMANTIC_PATCH_ENABLED:
        logging.getLogger(__name__).warning(
            "relation_semantic_patch_off — 계층형 grounding이 켜졌으나 관계 의미 패치가 "
            "꺼져 있다. 엔진 판정을 뒤집은 서술이 교정 없이 사용자에게 노출될 수 있다."
        )


def active_versions() -> dict[str, str | bool]:
    """이번 응답이 어떤 논리 버전으로 생성됐는지 — 계측 로그에 실린다."""
    return {
        "fortune_logic_version": FORTUNE_LOGIC_VERSION
        if PERIOD_HIERARCHY_ENABLED else "v1",
        "relation_semantics_version": RELATION_SEMANTICS_VERSION
        if RELATION_SEMANTIC_PATCH_ENABLED else "off",
        "pillar_role_version": PILLAR_ROLE_VERSION,
        "signal_polarity_version": SIGNAL_POLARITY_VERSION
        if PILLAR_POLARITY_V2_ENABLED else "legacy_pillar_label",
        "relation_semantic_patch_enabled": RELATION_SEMANTIC_PATCH_ENABLED,
        "period_hierarchy_enabled": PERIOD_HIERARCHY_ENABLED,
        "pillar_polarity_v2_enabled": PILLAR_POLARITY_V2_ENABLED,
        "safe_template_fallback_enabled": SAFE_TEMPLATE_FALLBACK_ENABLED,
        # LLM 재호출은 설계상 존재하지 않는다(요청당 1회 고정) — 계측 계약으로 못박는다.
        "llm_retry_policy": "none",
    }


validate_flags()
