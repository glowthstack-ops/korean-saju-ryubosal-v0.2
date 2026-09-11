"""컴파일 스냅샷 드리프트 차단 — 리포트·채팅 경로 4종 (2026-09-10, daily 의 교훈 이식).

`test_daily_fortune_snapshot_drift.py` 가 막는 함정과 같다: 원본 사전을 고치고 스냅샷을
재빌드하지 않으면 런타임(스냅샷 우선 로드)이 옛 규칙을 읽어 "새 규칙이 효과 없다"는
오진이 난다. 이벤트 그래프·구조 패턴·방향 제안·선발 배치 가중치는 지금까지 이 가드가
없었다(2026-09-10 감사 — 당시에는 우연히 일치).

각 스냅샷은 빌더의 순수 함수/스키마로 다시 만든 결과와 **의미적으로 같아야** 하고,
빌드 시각(compiled_at·updated_at)만 비교에서 뺀다. 런타임 로더가 참조하는 버전 상수와
빌드 스크립트의 버전 상수도 같아야 한다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from saju_engines.dictionaries import (
    _lint_direction_suggestions,
    _lint_structure_patterns,
)
from saju_engines.direction_suggestion import DIRECTION_SUGGESTIONS_VERSION
from saju_engines.graph_builder import GRAPH_VERSION, build_event_graph, load_event_graph
from saju_engines.selection_allocation import SELECTION_WEIGHTS_VERSION
from saju_engines.structure_patterns import STRUCTURE_PATTERNS_VERSION
from saju_shared_types.direction_suggestions import DirectionSuggestionDict
from saju_shared_types.structure_patterns import StructurePatternDict

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_COMPILED = _BACKEND / "compiled"


def _load_script(name: str) -> ModuleType:
    script = _BACKEND / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    assert path.exists(), f"스냅샷 없음: {path.name} — 빌드 스크립트를 돌리지 않았다"
    return json.loads(path.read_text(encoding="utf-8"))


# ── 이벤트 그래프 (chat_service `_COMPILED_GRAPH`) ───────────────────────────


def test_event_graph_snapshot_matches_sources() -> None:
    path = _COMPILED / f"event_graph_v{GRAPH_VERSION}.json"
    committed = load_event_graph(path)
    regenerated = build_event_graph(_DICTS, updated_at=None)
    a = committed.model_dump(exclude={"updated_at"})
    b = regenerated.model_dump(exclude={"updated_at"})
    assert a["version"] == GRAPH_VERSION
    assert a == b, (
        f"event_graph 스냅샷이 원본과 다르다(nodes {len(a['nodes'])}/{len(b['nodes'])}, "
        f"edges {len(a['edges'])}/{len(b['edges'])}) — "
        "`python scripts/build_event_graph.py` 재실행 필요"
    )


# ── 구조 패턴 ────────────────────────────────────────────────────────────────


def test_structure_patterns_snapshot_matches_source() -> None:
    script = _load_script("build_structure_patterns_snapshot")
    assert script.STRUCTURE_PATTERNS_VERSION == STRUCTURE_PATTERNS_VERSION
    parsed = StructurePatternDict.model_validate(
        json.loads((_DICTS / "structure_patterns.json").read_text("utf-8"))
    )
    assert not _lint_structure_patterns(parsed)
    committed = _read(_COMPILED / f"structure_patterns_v{STRUCTURE_PATTERNS_VERSION}.json")
    assert committed.pop("snapshot_version") == STRUCTURE_PATTERNS_VERSION
    committed.pop("compiled_at", None)
    assert committed == parsed.model_dump(by_alias=True), (
        "structure_patterns 스냅샷이 원본과 다르다 — "
        "`python scripts/build_structure_patterns_snapshot.py` 재실행 필요"
    )


# ── 방향 제안 ────────────────────────────────────────────────────────────────


def test_direction_suggestions_snapshot_matches_source() -> None:
    script = _load_script("build_direction_suggestions_snapshot")
    assert script.DIRECTION_SUGGESTIONS_VERSION == DIRECTION_SUGGESTIONS_VERSION
    parsed = DirectionSuggestionDict.model_validate(
        json.loads((_DICTS / "direction_suggestions.json").read_text("utf-8"))
    )
    assert not _lint_direction_suggestions(_DICTS, parsed)
    committed = _read(_COMPILED / f"direction_suggestions_v{DIRECTION_SUGGESTIONS_VERSION}.json")
    assert committed.pop("snapshot_version") == DIRECTION_SUGGESTIONS_VERSION
    committed.pop("compiled_at", None)
    assert committed == parsed.model_dump(by_alias=True), (
        "direction_suggestions 스냅샷이 원본과 다르다 — "
        "`python scripts/build_direction_suggestions_snapshot.py` 재실행 필요"
    )


# ── 선발 배치 가중치 ─────────────────────────────────────────────────────────


def test_selection_allocation_weights_snapshot_matches_source() -> None:
    script = _load_script("build_selection_allocation_snapshot")
    raw = json.loads((_DICTS / "selection_allocation_weights.json").read_text("utf-8"))
    assert not script.validate(raw)
    assert raw.get("version") == SELECTION_WEIGHTS_VERSION
    committed = _read(_COMPILED / f"selection_allocation_weights_v{SELECTION_WEIGHTS_VERSION}.json")
    assert committed == raw, (
        "selection_allocation_weights 스냅샷이 원본과 다르다 — "
        "`python scripts/build_selection_allocation_snapshot.py` 재실행 필요"
    )
