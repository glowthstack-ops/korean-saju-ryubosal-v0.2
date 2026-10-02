"""이벤트 엔진 공통 설정 — 채널 무관 SSOT (2026-07-31).

`marriage_engine_flags()` 는 결혼 타이밍 프로파일 전용이라 범위가 다르다. 대운 합화
배경처럼 **occurrence selection 에 영향을 줄 수 있는 모드**는 채널이 아니라 엔진 전역에서
하나로 정해져야 한다.

    chat engine mode == report engine mode

한 채널만 `post_selection` 으로 바꾸면 같은 명식·같은 질문에서 대표 시점과 사건이 달라진다.
서사 문구는 채널별로 달라도 되지만 선정 모드는 갈리면 안 된다. 그래서 각 서비스가
`os.getenv` 를 직접 읽지 않고 이 모듈이 해석한 값을 공통 팩토리로 받는다.

    환경변수 DAEWOON_HWA_MODE=current|post_selection
    기본값   current                (기존 동작 — production 불변)
    잘못된 값 import 시점 검증 실패   (조용한 폴백 없음)

잘못된 값을 기본값으로 흡수하지 않는 이유: `post_selection` 을 켠 줄 알았는데 오타로
`current` 로 돌고 있으면 배포가 조용히 무의미해진다. 위험 엔진처럼 '켜지면 안 되는' 게이트는
fail-closed 폴백이 맞지만, 이건 **어느 쪽으로든 의도와 다르게 도는 것**이 문제다.

설정은 import 시점에 한 번 굳는다. 요청마다 환경을 읽으면 같은 프로세스 안에서 모드가
갈려 채널 간 일치 계약이 깨진다.
"""

from __future__ import annotations

import os as _os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_ENV_VAR = "DAEWOON_HWA_MODE"
# 인성 동요→문서 교체 신호(2026-08-10 승인, relation_target_ten_god_rules) — on|off.
# 점수(occurrence selection)에 영향을 주므로 채널 무관 프로세스 단위로 하나다.
_ENV_VAR_RENEWAL = "RESOURCE_CLASH_RENEWAL"


class DaewoonHwaMode(StrEnum):
    """대운 합화 배경의 처리 위치.

    CURRENT         기존 ±3% 점수 보정 — 랭킹·대표 시점에 반영(기본값).
    POST_SELECTION  점수 영향 0. 배경은 시점 맵으로만 남고 대표 선정 이후 서사에서 쓴다
                    (DW-HWA 감사 판정 — 랭킹 관여 근거 미입증).
    """

    CURRENT = "current"
    POST_SELECTION = "post_selection"


@dataclass(frozen=True)
class EventEngineFlags:
    """이벤트 엔진 생성 플래그. 채널이 아니라 프로세스 단위로 하나다."""

    daewoon_hwa_mode: DaewoonHwaMode = DaewoonHwaMode.CURRENT
    # 인성 동요 신호 — 기본 OFF(기존 출력 byte 불변). 감수·회귀 확인 후 전환.
    resource_clash_renewal: bool = False


def parse_daewoon_hwa_mode(raw: str | None) -> DaewoonHwaMode:
    """환경변수 문자열 → 모드. 인식할 수 없으면 **예외**를 던진다.

    Args:
        raw: 환경변수 원문. None·빈 문자열이면 기본값(CURRENT).

    Returns:
        해석된 모드.

    Raises:
        ValueError: 허용값 밖. 조용히 기본값으로 흡수하면 오타 배포가 의도와 다르게
            돌면서도 정상으로 보인다.
    """
    text = (raw or "").strip().lower()
    if not text:
        return DaewoonHwaMode.CURRENT
    try:
        return DaewoonHwaMode(text)
    except ValueError:
        allowed = ", ".join(m.value for m in DaewoonHwaMode)
        raise ValueError(
            f"{_ENV_VAR}={raw!r} 는 허용값이 아닙니다. 허용: {allowed}"
        ) from None


def parse_on_off(raw: str | None, *, env_var: str) -> bool:
    """'on'|'off' 환경변수 → bool. 인식할 수 없으면 **예외**(조용한 폴백 없음).

    Args:
        raw: 환경변수 원문. None·빈 문자열이면 False(OFF 기본).
        env_var: 오류 메시지용 변수명.

    Returns:
        True(on) / False(off·미설정).

    Raises:
        ValueError: 허용값('on'/'off') 밖 — 오타 배포가 조용히 무의미해지는 것을 막는다.
    """
    text = (raw or "").strip().lower()
    if not text or text == "off":
        return False
    if text == "on":
        return True
    raise ValueError(f"{env_var}={raw!r} 는 허용값이 아닙니다. 허용: on, off")


def _load_flags() -> EventEngineFlags:
    """환경에서 플래그를 한 번 읽는다(import 시점 고정)."""
    return EventEngineFlags(
        daewoon_hwa_mode=parse_daewoon_hwa_mode(_os.environ.get(_ENV_VAR)),
        resource_clash_renewal=parse_on_off(
            _os.environ.get(_ENV_VAR_RENEWAL), env_var=_ENV_VAR_RENEWAL,
        ),
    )


#: 프로세스 단위 SSOT. 서비스는 이 값을 읽고 `os.getenv` 를 직접 보지 않는다.
EVENT_ENGINE_FLAGS: EventEngineFlags = _load_flags()


def active_event_engine_flags() -> EventEngineFlags:
    """현재 유효 플래그. 테스트는 이 모듈의 `EVENT_ENGINE_FLAGS` 를 monkeypatch 한다."""
    return EVENT_ENGINE_FLAGS


def build_event_engine_v2(dictionaries_dir: Path, **overrides: Any) -> Any:
    """이벤트 엔진 공통 팩토리 — **모든 채널이 같은 모드로 생성된다.**

    결혼 타이밍 프로파일 플래그와 엔진 공통 플래그를 합쳐 넘긴다. 호출부가 모드를
    따로 지정하지 않는 한 채널 간 선정 모드는 항상 같다.

    Args:
        dictionaries_dir: 사전 원본 루트.
        **overrides: 생성자 kwargs 덮어쓰기(테스트·스크립트 전용 — 서비스는 쓰지 않는다).

    Returns:
        EventEngineV2 인스턴스.
    """
    from .event_engine_v2 import EventEngineV2
    from .marriage_timing_profile import marriage_engine_flags

    kwargs: dict[str, Any] = dict(marriage_engine_flags())
    kwargs["daewoon_hwa_mode"] = active_event_engine_flags().daewoon_hwa_mode.value
    kwargs["enable_resource_clash_renewal"] = (
        active_event_engine_flags().resource_clash_renewal
    )
    kwargs.update(overrides)
    return EventEngineV2(dictionaries_dir, **kwargs)


def event_engine_flag_snapshot() -> dict[str, str]:
    """health·startup 감사용 실효값. env 가 아니라 **실제로 쓰이는 값**을 보여준다.

    env 만 보면 "env 에는 켰는데 실제 분기는 current" 인 상태를 구분할 수 없다.
    """
    return {
        "daewoon_hwa_mode": active_event_engine_flags().daewoon_hwa_mode.value,
        "resource_clash_renewal": (
            "on" if active_event_engine_flags().resource_clash_renewal else "off"
        ),
    }
