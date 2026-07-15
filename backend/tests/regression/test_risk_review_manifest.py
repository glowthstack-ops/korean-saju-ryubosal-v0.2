"""위험 사전 감수 manifest 정합 회귀 (감수 16차).

reviewed 수량·목록의 유일한 원천은 사전 JSON이다 — 수동 집계("대표 7 + FIN 6 + …")는
중복 집계가 생기므로 금지하고, git 추적 manifest(doc/v2_2/RISK_REVIEW_MANIFEST.json)가
재생성 결과와 일치함을 강제한다. 사전을 바꾸고 manifest 재생성을 잊으면 여기서 실패한다.

재생성: python scripts/risk_review_manifest.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPT = _BACKEND / "scripts" / "risk_review_manifest.py"
_MANIFEST = _BACKEND.parent / "doc" / "v2_2" / "RISK_REVIEW_MANIFEST.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location("risk_review_manifest", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_matches_dictionaries() -> None:
    """git 추적 manifest == 사전 JSON 재생성 결과(환경 버전·수량·목록 전체)."""
    module = _load_builder()
    assert _MANIFEST.exists(), "manifest 미생성 — scripts/risk_review_manifest.py 실행"
    stored = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert stored == module.build_manifest()


def test_manifest_totals_consistent() -> None:
    """수량 정합 — 총계=목록 길이, 도메인별 합=총계(집계 오류 자동 검출)."""
    module = _load_builder()
    m = module.build_manifest()
    assert m["reviewed_total"] == len(m["reviewed_risk_ids"])
    assert m["unreviewed_total"] == len(m["unreviewed_risk_ids"])
    assert m["reviewed_total"] == sum(
        d["reviewed"] for d in m["reviewed_by_domain"].values()
    )
    assert not (set(m["reviewed_risk_ids"]) & set(m["unreviewed_risk_ids"]))
