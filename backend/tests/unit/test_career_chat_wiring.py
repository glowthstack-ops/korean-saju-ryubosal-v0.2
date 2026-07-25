"""P4-1 chat 배선 통합 회귀 — CAREER_TRANSITION_SYSTEM §12.

flag 불변·LLM 호출 횟수·소유권·범위 격리를 실제 `chat_service` 훅으로 검증한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from saju_api.services import chat_service
from saju_engines import career_chat_consumer
from saju_shared_types.career_transition import CareerQueryResolution, CareerTransitionKind

_SERVICE = Path(chat_service.__file__)


# ── flag 불변 ──────────────────────────────────────────────────────────────


def test_flags_default_off() -> None:
    """두 flag 기본 OFF — 배선이 있어도 기존 응답이 바뀌지 않는다."""
    assert career_chat_consumer.CAREER_TRANSITION_CHAT_ENABLED is False
    assert career_chat_consumer.CAREER_TRANSITION_CHAT_BETA_EXPOSE is False


def test_prepare_returns_none_when_disabled(monkeypatch) -> None:
    """flag OFF 면 prepare 가 None → trailing 에 지시문이 붙지 않는다."""
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", False)
    assert chat_service._prepare_career_transition_block(object(), object()) is None


def test_prepare_returns_none_without_shadow_store(monkeypatch) -> None:
    """flag ON 이어도 shadow store 가 없으면(P3 경계) 지시문 0."""
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", True)
    assert chat_service._prepare_career_transition_block(object(), object()) is None


def test_prepare_failure_never_breaks_chat(monkeypatch) -> None:
    """준비 단계 예외는 삼켜지고 기존 경로가 유지된다."""
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", True)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_service, "_career_shadow_store_for", boom)
    assert chat_service._prepare_career_transition_block(object(), object()) is None


# ── LLM 호출 횟수 ──────────────────────────────────────────────────────────


def test_audit_makes_no_extra_call_when_clean(monkeypatch) -> None:
    """감사 통과 시 추가 LLM 호출 0."""
    calls = {"n": 0}
    monkeypatch.setattr(
        chat_service.llm_client, "generate_reading",
        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), "x")[1],
    )
    prep = career_chat_consumer.CareerBlockPreparation(eligible=False)
    out = chat_service._audit_career_transition_answer(
        "정상 답변", prep, "prompt", "chat", None, "o", "t"
    )
    assert out == "정상 답변"
    assert calls["n"] == 0


def test_audit_retries_exactly_once_on_violation(monkeypatch) -> None:
    """위반 시 커리어 지시문을 뺀 프롬프트로 **정확히 1회** 재생성한다."""
    store = _single_episode_store()
    prep = career_chat_consumer.prepare_career_chat_block(
        store, query_resolution=CareerQueryResolution.GENERAL_CAREER, subject_count=1,
        kind=CareerTransitionKind.EXTERNAL_MOVE, vector=_vector(),
        enabled=True, beta_expose=True,
    )
    assert prep.eligible
    calls: list[str] = []

    def gen(prompt, **k):
        calls.append(prompt)
        return "안전한 기존 답변"

    monkeypatch.setattr(chat_service.llm_client, "generate_reading", gen)
    out = chat_service._audit_career_transition_answer(
        "곧 오퍼가 옵니다.", prep, f"base\n{prep.directive}", "chat", None, "o", "t"
    )
    assert out == "안전한 기존 답변"
    assert len(calls) == 1                       # 3회 호출 금지
    assert (prep.directive or "") not in calls[0]  # 재생성은 legacy 프롬프트


# ── 범위 격리 ──────────────────────────────────────────────────────────────


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_report_and_daily_do_not_import_career_consumer() -> None:
    """report·daily 경로는 커리어 소비 모듈을 import 하지 않는다."""
    services = _SERVICE.parent
    for name in ("report_service.py", "daily_fortune_service.py"):
        path = services / name
        if not path.exists():
            continue
        hit = _imports(path) & {
            "saju_engines.career_chat_consumer",
            "saju_shared_types.career_consumer",
        }
        assert not hit, f"{name} 가 커리어 소비 모듈을 import: {sorted(hit)}"


def test_chat_service_uses_prepare_audit_not_e2e_runner() -> None:
    """chat_service 는 LLM을 자체 호출하는 e2e runner를 쓰지 않는다(이중 호출 방지)."""
    src = _SERVICE.read_text(encoding="utf-8")
    assert "run_career_chat_block" not in src
    assert "prepare_career_chat_block" in src
    assert "audit_career_chat_response" in src


def test_single_generate_reading_call_site_remains() -> None:
    """정상 경로의 generate_reading 호출부가 늘어나지 않았다(감사 재생성 1곳 제외)."""
    src = _SERVICE.read_text(encoding="utf-8")
    assert src.count("llm_client.generate_reading(") == 2  # 본 경로 + 감사 fallback


# ── helper ─────────────────────────────────────────────────────────────────


def _vector():
    from saju_engines.career_effect_vector import build_effect_vector
    from saju_shared_types.career_effect_vector import (
        ContributionRole,
        EffectAxis,
        EffectContribution,
    )

    contribs = tuple(
        EffectContribution(
            evidence_id=f"EV{i}", signal_ref=f"S{i}", axis=axis, value=0.5,
            role=ContributionRole.PRIMARY,
        )
        for i, axis in enumerate(
            (EffectAxis.AGREEMENT_QUALITY, EffectAxis.EXIT_PRESSURE,
             EffectAxis.ENTRY_REALIZATION)
        )
    )
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean and vector is not None
    return vector


def _single_episode_store():
    from saju_engines.career_transition_reducer import reduce_career_command
    from saju_shared_types.career_commands import CareerFactSource, CreateEpisodeCommand
    from saju_shared_types.career_transition import CareerEpisodeStore

    return reduce_career_command(
        CareerEpisodeStore(),
        CreateEpisodeCommand(
            command_id="c0", episode_id="ep-a", recorded_at="t0",
            source_kind=CareerFactSource.USER_CONFIRMED,
        ),
    ).store
