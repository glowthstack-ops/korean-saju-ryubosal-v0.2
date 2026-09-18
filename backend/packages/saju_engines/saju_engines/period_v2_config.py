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
# 부정 방향 국소 캡(P0.5b) — 같은 카테고리에서 대운·세운의 부정 지지가 없으면
# 월·일운 부정만으로 '불리 우세'에 진입하지 못하게 한다. 판정 로직은 검증을 마쳤고
# 남은 검증 대상은 LLM 표현 계약이라, 플래그로 분리해 문장 확인 후 켠다.
LOCAL_ADVERSE_ONLY_ENABLED: bool = _env_flag("SAJU_LOCAL_ADVERSE_ONLY_ENABLED")
# 패치로도 복구가 안 될 때 엔진 데이터만으로 조립한 안전 템플릿을 쓴다(추가 LLM 호출 없음).
SAFE_TEMPLATE_FALLBACK_ENABLED: bool = _env_flag("SAJU_SAFE_TEMPLATE_FALLBACK_ENABLED")
# P2 사건 범위 게이트 — minor-only 후보의 주요 사건 Top-N 제외 + 후보별 층위 grounding 노출.
# P2-1에서 candidate_source_layers를 채우면 grounding이 곧바로 살아나 프롬프트가 바뀌므로,
# "산출"과 "노출"을 이 플래그로 분리한다(P2-1은 동작 불변이어야 한다).
EVENT_LOCAL_TRIGGER_GATE_ENABLED: bool = _env_flag("SAJU_EVENT_LOCAL_TRIGGER_GATE_ENABLED")
# P2-3b dual-run — 같은 요청·같은 후보 집합을 reducer 직전에서 legacy·scoped 두 번
# 선택해 후보 ID로 비교한다. **사용자에게는 legacy 결과만 반환**하며 scoped는 감사
# 전용이다. 계측 비용(선별 1회 추가)이 있어 기본 OFF이고 측정 환경에서만 켠다.
EVENT_PROCESS_DUAL_RUN_ENABLED: bool = _env_flag("SAJU_EVENT_PROCESS_DUAL_RUN_ENABLED")
# P0 월 커버리지 감사(2026-09-18 데굴님 지시, 전문가 반박 사례) — 기반 최고 달 누락·
# 비후보 달 결정 권고를 LLM 재호출 없이 엔진 확정 문장 삽입으로 보정한다. 점수·판정 불변.
MONTH_COVERAGE_AUDIT_ENABLED: bool = _env_flag("SAJU_MONTH_COVERAGE_AUDIT_ENABLED")
# P1 합 완화(2026-09-18 데굴님 지시 — 전문가 취지 "기신 억제 + 관운 강화", "지병 완화") —
# 운 흉신 글자가 합거로 묶이면 결과 유불리(favorability)를 한 단계 완화하고, 합 결과 오행이
# 관이면 관 계열 사건에 관운 강화 보정을 더한다. 점수·순위·사건 종류 불변. 월 등급 쪽은
# saju_manse_analysis.luck.luck_cycles가 같은 환경변수를 따로 읽는다(패키지 의존 방향).
HAP_MITIGATION_ENABLED: bool = _env_flag("SAJU_HAP_MITIGATION_ENABLED")
# CALIBRATE: 관운 강화 favorability 가산(데굴님 승인 제안값, shadow 실측 후 조정).
HAP_OFFICER_BOOST: float = 0.3
# 관계 용어 층위 정리 v2(2026-09-18 데굴님 승인, 전문가 참고 기준) — 서술·표기 전용, 점수·판정 불변:
# 구조 패턴 4단 서술(작용→영역→양상→성립 조건), 쟁합의 십성 라벨, 합처봉충 표기, 세운병림 표지.
RELATION_TERMS_V2_ENABLED: bool = _env_flag("SAJU_RELATION_TERMS_V2_ENABLED")
# CALIBRATE: 용희신 합거 손상(길신 묶임) favorability 감점·월 등급 감점(HAP_MITIGATION 플래그 공유).
HAP_HARM_PENALTY: float = 0.3
# CALIBRATE(2026-09-18 데굴님 승인, HAP_MITIGATION 플래그 공유 — 배경 감점, favorability만):
# 運破格(운 십성이 격의 상신을 손상 + 원국 구응 없음)·기신 성국(운 지지로 완성된 국의 오행이
# 기·구신).
GEOK_BREAK_PENALTY: float = 0.2
GISIN_LOCAL_PENALTY: float = 0.2
# 사건 어휘 층(2026-09-18 데굴님 승인, 전문가 참고 기준 B1·B2·B6) — 서술·표기·감사 전용, 점수 불변:
# 후보별 '공통 사건 유형' 결정론 분류, 사건 서술 계약(경쟁≠탈락≠손실·기회≠성취≠유지·체감→관찰 가능
# 사건 번역·발생→진행→결과→후속), 손실 확정어 감사.
EVENT_LEXICON_ENABLED: bool = _env_flag("SAJU_EVENT_LEXICON_ENABLED")
# 구조 배경 보강(A2, 2026-09-18 승인) — 충근·개두절각·통관 부재·구응 손상·특수격 역행. 판정 층.
STRUCTURE_BACKGROUND_ENABLED: bool = _env_flag("SAJU_STRUCTURE_BACKGROUND_ENABLED")
# CALIBRATE(A2): 충근(용·희신 유일 뿌리 충) 감점 / 개두·절각(운 기둥)·통관 부재 감점.
STRUCTURE_ROOT_PENALTY: float = 0.2
STRUCTURE_PILLAR_PENALTY: float = 0.1
# 기회·호전 사전(P1, 2026-09-18 승인) — 위험 사전의 긍정 대칭 층. 경량 엔진 판정을 후보 서술에
# '호전·기회 신호' 줄로 노출한다. 점수·순위 불변, 성사 확정 금지. 기본 OFF.
OPPORTUNITY_ENABLED: bool = _env_flag("SAJU_OPPORTUNITY_ENABLED")
OPPORTUNITY_MIN_SCORE: float = 0.5  # CALIBRATE: 노출 문턱(base + 트리거 합 − 감쇠)

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
        "local_adverse_only_enabled": LOCAL_ADVERSE_ONLY_ENABLED,
        "event_local_trigger_gate_enabled": EVENT_LOCAL_TRIGGER_GATE_ENABLED,
        "event_process_dual_run_enabled": EVENT_PROCESS_DUAL_RUN_ENABLED,
        "month_coverage_audit_enabled": MONTH_COVERAGE_AUDIT_ENABLED,
        "hap_mitigation_enabled": HAP_MITIGATION_ENABLED,
        "relation_terms_v2_enabled": RELATION_TERMS_V2_ENABLED,
        "event_lexicon_enabled": EVENT_LEXICON_ENABLED,
        "structure_background_enabled": STRUCTURE_BACKGROUND_ENABLED,
        "opportunity_enabled": OPPORTUNITY_ENABLED,
        # LLM 재호출은 설계상 존재하지 않는다(요청당 1회 고정) — 계측 계약으로 못박는다.
        "llm_retry_policy": "none",
    }


validate_flags()
