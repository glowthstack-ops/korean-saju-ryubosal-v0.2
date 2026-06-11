"""Event Graph 컴파일 스크립트 (v2.2 Phase 2 T2.1, docs/05 graph:build 단계).

사전 원본(dictionaries/)을 검증한 뒤 이벤트 그래프 스냅샷(compiled/)을 생성한다.
운영 코드는 이 스냅샷만 읽는다(절대 원칙 5).

사용법:
    python scripts/build_event_graph.py [dictionaries_dir] [compiled_dir]
종료 코드 0=성공, 1=사전 위반 또는 빌드 실패.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from saju_engines.dictionaries import lint_dictionaries, validate_dictionaries
from saju_engines.graph_builder import build_event_graph, save_event_graph

_BACKEND = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    """사전 검증 → 그래프 빌드 → 스냅샷 저장."""
    dicts_dir = Path(argv[1]) if len(argv) > 1 else _BACKEND / "dictionaries"
    compiled_dir = Path(argv[2]) if len(argv) > 2 else _BACKEND / "compiled"

    violations = validate_dictionaries(dicts_dir) + lint_dictionaries(dicts_dir)
    if violations:
        print("사전 위반으로 빌드 중단:")
        for v in violations:
            print(f"  ✗ {v}")
        return 1

    graph = build_event_graph(dicts_dir, updated_at=datetime.now(UTC).isoformat())
    path = save_event_graph(graph, compiled_dir)
    print(f"빌드 완료: {path}")
    print(f"  노드 {len(graph.nodes)}개 · 엣지 {len(graph.edges)}개 · v{graph.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
