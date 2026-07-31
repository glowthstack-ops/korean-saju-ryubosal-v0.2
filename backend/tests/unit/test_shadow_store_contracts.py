"""shadow 저장소 계약 감사 회귀 (2026-07-31).

`take_risk_shadow` · `take_relationship_shadow` 는 이름과 달리 **소비하지 않는다**
(peek). 배경 store(`take_daewoon_hwa_backgrounds`)만 consume-and-reset 이다.

셋을 같은 이름 규칙으로 묶어 무심코 통일하지 않도록 차이를 회귀로 고정한다. peek 두
개를 consume 으로 바꾸는 것은 관측 이름을 맞추려고 **동작 계약을 바꾸는 일**이고,
risk 는 EXPOSE 파이프라인 회귀 범위가 넓어 실익보다 변경 위험이 크다(감사 결론).

감사에서 확인한 사실:

    production stale reuse   도달 불가 — 모든 take 가 같은 함수 안 score 뒤 직선,
                             요청당 1회 호출. score 없는 후속 take 경로가 없다.
    예외 경로                finally 가 현재 요청 결과로 덮어써 이전 값 잔류 없음
    교차 스레드              thread-local 격리 확인
"""

from __future__ import annotations

import re
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "apps" / "api" / "saju_api" / "services"
_PEEK_TAKES = ("take_risk_shadow", "take_relationship_shadow")


def _engine():
    from saju_engines.event_engine_config import build_event_engine_v2

    dicts = Path(__file__).resolve().parents[2] / "dictionaries"
    return build_event_engine_v2(dicts)


def test_peek_takes_do_not_clear_between_calls() -> None:
    """반복 호출이 같은 snapshot 을 돌려준다 — consume 이 아니다."""
    engine = _engine()
    for name in _PEEK_TAKES:
        take = getattr(engine, name)
        first, second = take(), take()
        assert first == second, name


def test_background_store_is_the_only_consuming_take() -> None:
    """배경 store 만 소비한다 — 셋을 같은 규칙으로 통일하면 안 된다."""
    engine = _engine()
    engine._dw_bg_tls.last = {"2027-03": object()}
    assert len(engine.take_daewoon_hwa_backgrounds()) == 1
    assert len(engine.take_daewoon_hwa_backgrounds()) == 0


def test_peek_contract_is_documented() -> None:
    """이름과 계약이 다르다는 사실이 docstring 에 남아 있어야 한다.

    이 사실이 사라지면 다음 사람이 '이름이 take 니까 소비하겠지' 로 읽는다.
    """
    engine = _engine()
    for name in _PEEK_TAKES:
        doc = getattr(engine, name).__doc__ or ""
        assert "peek" in doc, name


def test_every_take_call_site_follows_a_score() -> None:
    """stale reuse 가 도달 불가한 근거 — take 앞에 score 가 있어야 한다.

    이 구조가 깨지면(조기 반환 경로에서 take 를 부르는 소비자가 생기면) peek 계약이
    곧바로 요청 간 누출이 된다. 그때는 consume 전환을 다시 검토해야 한다.
    """
    pattern = re.compile(r"take_(?:risk|relationship)_shadow\(\)|take_daewoon_hwa_backgrounds\(\)")
    for name in ("chat_service.py", "report_service.py"):
        lines = (_SERVICES / name).read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not pattern.search(line):
                continue
            window = "\n".join(lines[max(0, i - 70):i])
            assert re.search(r"\.score\w*\(", window), f"{name}:{i + 1} 앞에 score 없음"
