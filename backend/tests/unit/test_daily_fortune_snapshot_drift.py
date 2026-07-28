"""컴파일 스냅샷 최신성 — 사전 원본과 배포 스냅샷의 드리프트 차단 (OA-6a 완료 조건).

이 테스트가 없어서 실제로 오진이 났다: `headline_slots`를 원본에만 넣고 스냅샷을
재생성하지 않아 런타임이 옛 사전을 읽었고, "자격을 열었는데 효과가 0"이라는 잘못된
결론으로 점수·명리 가중치를 건드릴 뻔했다.

드리프트는 단순 실수가 아니라 **잘못된 제품·명리 진단을 만드는 빌드 체계 결함**이다:

    새 규칙이 효과 없다고 오진 → 불필요한 가중치 변경
    측정 결과와 운영 결과 불일치
    DICT_VERSION만 보고 최신이라고 착각
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.daily_fortune_snapshot import (
    SOURCES,
    build_snapshot,
    load_snapshot,
    snapshot_path,
    source_digest,
)
from saju_shared_types.daily_fortune import DICT_VERSION

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries" / "daily_fortune"
_COMPILED = _BACKEND / "compiled"

#: 비교에서 제외 — 빌드 시각은 내용이 아니다.
_VOLATILE = ("compiled_at",)


def _normalize(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in _VOLATILE}


@pytest.fixture(scope="module")
def committed() -> dict:
    snap = load_snapshot(DICT_VERSION, _COMPILED)
    assert snap is not None, (
        f"DICT_VERSION={DICT_VERSION} 스냅샷이 없다 — 사전을 고치고 버전만 올렸거나 "
        f"`python scripts/build_daily_fortune_snapshot.py`를 돌리지 않았다. "
        f"이 상태에서는 런타임이 원본으로 폴백해 배포본과 달라진다."
    )
    return snap


def test_snapshot_exists_for_current_version(committed) -> None:
    """현재 버전의 스냅샷이 커밋돼 있어야 한다."""
    assert snapshot_path(DICT_VERSION, _COMPILED).exists()
    assert committed["dict_version"] == DICT_VERSION


def test_source_digest_matches_committed_snapshot(committed) -> None:
    """원본을 고치고 스냅샷을 재생성하지 않으면 여기서 걸린다."""
    stale = []
    for name, _key in SOURCES:
        current = source_digest(_DICTS / name)
        recorded = committed["sources"][name]["sha256"]
        if current != recorded:
            stale.append(name)
    assert not stale, (
        f"사전 원본이 스냅샷보다 새롭다: {stale} — "
        "`python scripts/build_daily_fortune_snapshot.py` 재실행 필요"
    )


def test_regenerated_snapshot_equals_committed(committed) -> None:
    """원본에서 다시 컴파일한 결과가 커밋본과 의미적으로 같아야 한다."""
    regenerated = build_snapshot(DICT_VERSION, _DICTS, compiled_at="")

    assert _normalize(regenerated) == _normalize(committed), (
        "재컴파일 결과가 커밋된 스냅샷과 다르다 — 스냅샷이 오래됐거나 컴파일러가 바뀌었다"
    )


def test_snapshot_carries_provenance(committed) -> None:
    """추적에 필요한 메타데이터를 갖춘다."""
    assert committed["structural_validation"] == "passed"
    for name, _key in SOURCES:
        src = committed["sources"][name]
        assert src["sha256"], f"{name}: source digest 누락"
        assert src["version"], f"{name}: version 누락"
        # 명리 감수 상태는 파이프라인이 참으로 바꾸지 않는다.
        assert src["reviewed"] is False


def test_runtime_reads_compiled_snapshot() -> None:
    """런타임이 실제로 스냅샷을 읽는지 — 폴백으로 조용히 새 값을 잃지 않는다."""
    from saju_engines.daily_ilju_fortune import load_daily_dicts

    runtime = load_daily_dicts()
    committed_catalog = json.loads(
        snapshot_path(DICT_VERSION, _COMPILED).read_text(encoding="utf-8")
    )["catalog"]

    assert runtime.catalog["version"] == committed_catalog["version"]
    # OA-6a 값이 런타임까지 도달했는가(드리프트의 실제 증상).
    assert (
        runtime.catalog["events"]["rest_recharge"].get("headline_slots") is not None
    ), "headline_slots가 런타임에 없다 — 스냅샷 드리프트"
