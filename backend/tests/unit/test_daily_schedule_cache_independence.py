"""legacy 와 shared 가 같은 프로세스에서 `load_daily_dicts()` 캐시를 공유해도
결과가 오염되지 않는지 확인한다.

공유 캐시가 결과를 움직이면 다음이 가능해진다.

  · 한쪽이 반환 객체를 바꿔 다른 쪽 결과에 영향
  · 실행 순서에 따라 결과가 달라짐
  · 독립 실행 시엔 갈리는데 같은 캐시 객체 덕분에 우연히 일치

parity 를 공식 근거로 쓰려면 이 셋을 모두 배제해야 한다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import legacy_oa10b_runner as LEGACY  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_schedule_runner import build_rolling_audit_schedule  # noqa: E402
from saju_engines.daily_selection_policy_shadow import SelectionPolicy  # noqa: E402

#: 순서 효과를 드러내기에 충분하고 테스트로 돌릴 만큼 짧은 구간.
_DAYS = 5
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)


def _clear_cache() -> None:
    cache_clear = getattr(M.load_daily_dicts, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _dict_fingerprint() -> str:
    """캐시된 사전 입력의 지문 — 실행 전후로 같아야 한다."""
    catalog = M.load_daily_dicts().catalog
    return hashlib.sha256(
        json.dumps(catalog, ensure_ascii=False, sort_keys=True,
                   default=str).encode("utf-8")
    ).hexdigest()


@pytest.fixture(scope="module")
def family_of() -> dict[str, str]:
    return LEGACY.load_family_map()


def _legacy_rows(family_of) -> list[dict]:
    return LEGACY.build_schedule_observed(family_of, days=_DAYS).rows


def _shared_rows(family_of) -> list[dict]:
    steps, _s = build_rolling_audit_schedule(
        days=_DAYS, policy=C10_POLICY, board_policy=_BOARD, family_of=family_of
    )
    return [dict(r) for st in steps for r in st.rows]


def test_execution_order_does_not_change_results(family_of) -> None:
    """legacy→shared 와 shared→legacy 가 같은 결과를 내야 한다."""
    _clear_cache()
    legacy_first = _legacy_rows(family_of)
    _clear_cache()
    shared_after_legacy = _shared_rows(family_of)

    _clear_cache()
    shared_first = _shared_rows(family_of)
    _clear_cache()
    legacy_after_shared = _legacy_rows(family_of)

    assert legacy_first == legacy_after_shared
    assert shared_first == shared_after_legacy


def test_each_runner_is_stable_across_repeats(family_of) -> None:
    """같은 runner 를 연달아 두 번 — 캐시가 데워진 뒤에도 같아야 한다."""
    assert _legacy_rows(family_of) == _legacy_rows(family_of)
    assert _shared_rows(family_of) == _shared_rows(family_of)


def test_shared_cache_is_not_mutated_by_either_runner(family_of) -> None:
    """반환 객체를 누가 바꾸면 다른 쪽 결과가 조용히 달라진다."""
    _clear_cache()
    before = _dict_fingerprint()
    _legacy_rows(family_of)
    assert _dict_fingerprint() == before, "legacy 실행이 사전 입력을 변경했다"
    _shared_rows(family_of)
    assert _dict_fingerprint() == before, "shared 실행이 사전 입력을 변경했다"


def test_warm_and_cold_cache_agree(family_of) -> None:
    """캐시를 비운 뒤와 데워진 뒤 결과가 같아야 한다."""
    _clear_cache()
    cold = _shared_rows(family_of)
    warm = _shared_rows(family_of)
    assert cold == warm
