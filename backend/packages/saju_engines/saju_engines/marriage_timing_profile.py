"""연애·결혼 시기(MT) feature 프로파일 — EventEngineV2 플래그 일괄 제어 (v2.2, 2026-06-30).

MT1~MT4는 EventEngineV2 생성자 플래그로 켜고 끈다. 각 호출부에서 플래그를 개별로 넘기면 일관성이
깨지므로, 프로파일로 묶어 한 곳에서 관리한다(Marriage Production Readiness v1).

- `default`: 전부 OFF — 기존 동작 불변(운영 안전 기본값·rollback 타깃).
- `production_candidate`: MT1·MT2·MT3 ON, MT4 shadow(점수 무변경·진단만), MT5 OFF.

**활성 프로파일 전환은 표현 가드(marriage_output_guard)·단계 payload가 완비된 뒤 별도로** 한다.
그때까지 `ACTIVE_MARRIAGE_PROFILE='default'`로 두어 답변 출력은 byte 불변이다. MT5(family_formation
21키)·MT6(static prior)는 EventEngineV2 플래그가 아니라 별도 모듈이라 본 프로파일에 포함하지 않는다.
"""

from __future__ import annotations

from typing import Any

# EventEngineV2 생성자 kwargs 묶음(값이 bool·str 혼합 — **unpack 위해 Any).
MARRIAGE_TIMING_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "enable_mt1_awareness": False,
        "enable_mt2_emergence": False,
        "enable_mt3_directional": False,
        "enable_mt4_subtype": "off",
    },
    "production_candidate": {
        "enable_mt1_awareness": True,
        "enable_mt2_emergence": True,
        "enable_mt3_directional": True,
        "enable_mt4_subtype": "shadow",
    },
}

# 답변 surface(report/chat) 활성 프로파일. 가드·단계 payload·텔레메트리 완비 후 상용 전환
# (2026-06-30 사용자 승인). rollback은 'default'로 1줄 복귀. MT4 apply·MT5는 계속 보류.
ACTIVE_MARRIAGE_PROFILE = "production_candidate"

# MT5/MT6 메모(EventEngineV2 플래그 아님 — 별도 단계에서 배선).
MARRIAGE_PROFILE_AUX: dict[str, dict[str, bool]] = {
    "default": {"mt5_family_formation": False, "mt6_age_prior": False},
    "production_candidate": {"mt5_family_formation": False, "mt6_age_prior": True},
}


def marriage_engine_flags(profile: str | None = None) -> dict[str, Any]:
    """프로파일명 → EventEngineV2 생성자 kwargs(미지정 시 활성 프로파일, 미지 프로파일은 default).

    Args:
        profile: 프로파일명('default'/'production_candidate'). None이면 ACTIVE_MARRIAGE_PROFILE.

    Returns:
        EventEngineV2(**flags)로 넘길 kwargs 사본(호출부가 변형해도 원본 불변).
    """
    name = profile or ACTIVE_MARRIAGE_PROFILE
    return dict(MARRIAGE_TIMING_PROFILES.get(name, MARRIAGE_TIMING_PROFILES["default"]))


def active_marriage_aux(profile: str | None = None) -> dict[str, bool]:
    """활성(또는 지정) 프로파일의 MT5/MT6 aux 플래그(호출 시점 ACTIVE 반영 — 런타임 전환 전파)."""
    name = profile or ACTIVE_MARRIAGE_PROFILE
    return dict(MARRIAGE_PROFILE_AUX.get(name, MARRIAGE_PROFILE_AUX["default"]))


def active_mt_features(profile: str | None = None) -> list[str]:
    """활성 프로파일에서 켜진 MT 기능 라벨(텔레메트리용). 빈 목록이면 전부 OFF(default)."""
    f = marriage_engine_flags(profile)
    aux = active_marriage_aux(profile)
    out: list[str] = []
    if f.get("enable_mt1_awareness"):
        out.append("MT1")
    if f.get("enable_mt2_emergence"):
        out.append("MT2")
    if f.get("enable_mt3_directional"):
        out.append("MT3")
    mt4 = f.get("enable_mt4_subtype")
    if mt4 and mt4 != "off":
        out.append(f"MT4_{mt4}")
    if aux.get("mt6_age_prior"):
        out.append("MT6")
    return out
