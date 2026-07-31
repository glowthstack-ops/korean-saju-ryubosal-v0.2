"""이벤트 엔진 모드 중앙 설정 회귀 (2026-07-31).

`daewoon_hwa_mode` 는 occurrence selection 에 영향을 줄 수 있어 채널이 아니라 **엔진 전역**
에서 하나여야 한다. 한 채널만 `post_selection` 으로 바뀌면 같은 명식·같은 질문에서 채팅과
리포트의 대표 시점·사건이 달라진다.

    chat engine mode == report engine mode

이번 커밋은 인프라만 넣는다(inert). 기본값은 `current` 이므로 기존 출력은 불변이고,
서사 배선·claim audit 확장·환경 전환은 포함하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines import event_engine_config as C
from saju_engines.event_engine_config import (
    DaewoonHwaMode,
    EventEngineFlags,
    build_event_engine_v2,
    event_engine_flag_snapshot,
    parse_daewoon_hwa_mode,
)

#: 팩토리에 넘길 사전 경로. 실제 로드는 하지 않지만(가짜 엔진) 타입 계약은 Path 다.
#: cwd 상대 경로를 쓰면 실행 위치에 따라 의미가 달라진다(test_path_hygiene 가 차단).
_DICTS_MARKER = Path(__file__).resolve().parents[2] / "dictionaries"


# ── 환경변수 해석 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DaewoonHwaMode.CURRENT),          # 미설정
        ("", DaewoonHwaMode.CURRENT),            # 빈 값
        ("   ", DaewoonHwaMode.CURRENT),         # 공백만
        ("current", DaewoonHwaMode.CURRENT),
        ("post_selection", DaewoonHwaMode.POST_SELECTION),
        ("POST_SELECTION", DaewoonHwaMode.POST_SELECTION),  # 대소문자 무관
        (" post_selection ", DaewoonHwaMode.POST_SELECTION),
    ],
)
def test_parse_accepts_valid_values(raw: str | None, expected: DaewoonHwaMode) -> None:
    assert parse_daewoon_hwa_mode(raw) is expected


@pytest.mark.parametrize("raw", ["postselection", "shadow", "on", "off", "true", "1"])
def test_invalid_value_fails_startup_validation(raw: str) -> None:
    """조용히 기본값으로 흡수하지 않는다.

    흡수하면 `post_selection` 을 켠 줄 알았는데 오타로 `current` 로 돌면서도 정상으로
    보인다 — 배포가 무의미해진 것을 아무도 모른다.
    """
    with pytest.raises(ValueError, match="DAEWOON_HWA_MODE"):
        parse_daewoon_hwa_mode(raw)


def test_default_flags_are_current() -> None:
    """기본값이 바뀌면 production 선정이 조용히 달라진다."""
    assert EventEngineFlags().daewoon_hwa_mode is DaewoonHwaMode.CURRENT
    assert C.EVENT_ENGINE_FLAGS.daewoon_hwa_mode is DaewoonHwaMode.CURRENT


def test_config_does_not_reread_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """설정이 굳은 뒤 환경을 다시 읽지 않는다.

    요청마다 env 를 읽으면 같은 프로세스 안에서 모드가 갈려 채널 일치 계약이 깨진다.
    """
    before = C.active_event_engine_flags()
    monkeypatch.setenv("DAEWOON_HWA_MODE", "post_selection")
    assert C.active_event_engine_flags() == before


# ── 공통 팩토리 ──────────────────────────────────────────────────────────


class _FakeEngine:
    def __init__(self, dictionaries_dir: object, **kwargs: object) -> None:
        self.dictionaries_dir = dictionaries_dir
        self.kwargs = kwargs


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """사전 로드 없이 팩토리가 넘기는 kwargs 만 본다."""
    import saju_engines.event_engine_v2 as v2

    monkeypatch.setattr(v2, "EventEngineV2", _FakeEngine)


@pytest.mark.usefixtures("fake_engine")
@pytest.mark.parametrize("mode", list(DaewoonHwaMode))
def test_factory_passes_active_mode(
    monkeypatch: pytest.MonkeyPatch, mode: DaewoonHwaMode
) -> None:
    """팩토리가 SSOT 의 모드를 그대로 전달한다."""
    monkeypatch.setattr(C, "EVENT_ENGINE_FLAGS", EventEngineFlags(daewoon_hwa_mode=mode))
    engine = build_event_engine_v2(_DICTS_MARKER)
    assert engine.kwargs["daewoon_hwa_mode"] == mode.value


@pytest.mark.usefixtures("fake_engine")
def test_factory_keeps_marriage_profile_flags() -> None:
    """결혼 프로파일 플래그가 사라지면 기존 동작이 조용히 바뀐다."""
    from saju_engines.marriage_timing_profile import marriage_engine_flags

    engine = build_event_engine_v2(_DICTS_MARKER)
    for key, value in marriage_engine_flags().items():
        assert engine.kwargs[key] == value


@pytest.mark.usefixtures("fake_engine")
@pytest.mark.parametrize("mode", list(DaewoonHwaMode))
def test_chat_and_report_get_identical_mode(
    monkeypatch: pytest.MonkeyPatch, mode: DaewoonHwaMode
) -> None:
    """**핵심 계약** — 두 채널의 선정 모드는 항상 같다.

    갈리면 같은 명식·같은 질문에서 채팅과 리포트의 대표 시점·사건이 달라진다.
    """
    monkeypatch.setattr(C, "EVENT_ENGINE_FLAGS", EventEngineFlags(daewoon_hwa_mode=mode))
    chat = build_event_engine_v2(_DICTS_MARKER)
    report = build_event_engine_v2(_DICTS_MARKER)
    assert chat.kwargs["daewoon_hwa_mode"] == report.kwargs["daewoon_hwa_mode"]


def test_services_use_the_shared_factory() -> None:
    """서비스가 엔진을 직접 생성하면 모드 일치 계약이 우회된다.

    팩토리 호출 여부를 소스에서 고정한다 — 런타임 확인은 사전 로드를 요구해 무겁고,
    회귀가 잡아야 할 것은 '누가 엔진을 만드는가'라는 구조다.
    """
    api = Path(__file__).resolve().parents[2] / "apps" / "api" / "saju_api" / "services"
    for name in ("chat_service.py", "report_service.py"):
        source = (api / name).read_text(encoding="utf-8")
        assert "build_event_engine_v2(" in source, name
        assert "EventEngineV2(_DICTS" not in source, name


# ── 관측 ─────────────────────────────────────────────────────────────────


def test_snapshot_reports_effective_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """env 가 아니라 실제로 쓰이는 값을 보여준다."""
    monkeypatch.setattr(
        C, "EVENT_ENGINE_FLAGS",
        EventEngineFlags(daewoon_hwa_mode=DaewoonHwaMode.POST_SELECTION),
    )
    assert event_engine_flag_snapshot() == {"daewoon_hwa_mode": "post_selection"}


def test_health_exposes_event_engine_flags() -> None:
    """운영에서 실효 모드를 확인할 수단이 있어야 한다."""
    from fastapi.testclient import TestClient

    from saju_api.main import app

    body = TestClient(app).get("/health").json()
    assert body["event_engine_flags"]["daewoon_hwa_mode"] in {
        m.value for m in DaewoonHwaMode
    }
