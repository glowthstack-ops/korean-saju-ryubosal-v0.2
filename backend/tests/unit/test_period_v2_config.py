"""총운 V2 플래그·생성 파이프라인 계약 (2026-07-27 데굴님 확정).

핵심 계약: **LLM 재호출은 존재하지 않는다.** 관계 의미 역전은 재생성이 아니라
canonical claim 기반 결정론적 교체로 복구하고, 그래도 안 되면 서버 템플릿으로 조립한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from saju_engines import period_v2_config

_SERVICE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "saju_api"
    / "services" / "chat_service.py"
)


def test_flags_default_off() -> None:
    """`.env.beta` 부재 시 전부 off — 기존 출력이 byte 단위로 보존된다."""
    assert period_v2_config.RELATION_SEMANTIC_PATCH_ENABLED is False
    assert period_v2_config.PERIOD_HIERARCHY_ENABLED is False
    assert period_v2_config.PILLAR_POLARITY_V2_ENABLED is False
    assert period_v2_config.SAFE_TEMPLATE_FALLBACK_ENABLED is False


def test_retry_flag_does_not_exist() -> None:
    """재생성 플래그는 철회됐다 — 되살아나면 비용 정책 위반이다."""
    assert not hasattr(period_v2_config, "RELATION_AUDIT_RETRY_ENABLED")


def test_relation_patch_path_makes_no_llm_call() -> None:
    """관계 패치 경로에 LLM 호출이 없다(요청당 1회 고정)."""
    src = _SERVICE.read_text(encoding="utf-8")
    start = src.index("def _audit_relation_answer(")
    # 다음 최상위 정의(def/상수/주석)까지를 함수 본문으로 본다.
    body = src[start : src.index("\n#: shadow 저장소", start)]
    assert "generate_reading" not in body
    assert "patch_relation_claims" in body
    assert "build_safe_period_answer" in body


def test_polarity_v2_requires_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    """점수만 V2이고 설명이 V1이면 기동을 차단한다.

    모듈 reload는 다른 테스트가 잡고 있는 심볼 동일성을 깨므로 쓰지 않는다.
    """
    monkeypatch.setattr(period_v2_config, "PILLAR_POLARITY_V2_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "PERIOD_HIERARCHY_ENABLED", False)
    with pytest.raises(period_v2_config.ConfigurationError):
        period_v2_config.validate_flags()


def test_patch_requires_safe_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """안전 템플릿은 개별로 끌 수 없다 — 끄면 미교정 모순이 그대로 전달된다."""
    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "SAFE_TEMPLATE_FALLBACK_ENABLED", False)
    with pytest.raises(period_v2_config.ConfigurationError):
        period_v2_config.validate_flags()


def test_hierarchy_without_patch_only_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """패치가 꺼진 채 계층형만 켜면 기동은 되지만 경고를 남긴다.

    앱이 로깅을 재구성하면 caplog(루트 전파)가 비어 있을 수 있어, 해당 로거에
    핸들러를 직접 붙여 전파 설정과 무관하게 확인한다.
    """
    monkeypatch.setattr(period_v2_config, "PERIOD_HIERARCHY_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", False)

    logger = logging.getLogger(period_v2_config.__name__)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        period_v2_config.validate_flags()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)

    assert any("relation_semantic_patch_off" in r.getMessage() for r in records)


def test_active_versions_declares_no_retry() -> None:
    """계측에 재시도 정책이 'none'으로 못박힌다."""
    assert period_v2_config.active_versions()["llm_retry_policy"] == "none"


def test_pillar_role_weight_is_uniform_40_60() -> None:
    """전 층위 공통 0.40/0.60 — 월운 예외를 두지 않는다."""
    assert period_v2_config.PILLAR_ROLE_WEIGHT == {"stem": 0.40, "branch": 0.60}
