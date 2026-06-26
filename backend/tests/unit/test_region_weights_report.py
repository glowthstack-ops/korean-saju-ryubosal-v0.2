"""가중치 튜닝 리뷰 시트(P4 #5) 검증 — 파라미터 수집·베이스라인 구조.

값 자체는 reviewed:false라 고정하지 않고, 튜닝에 필요한 knob과 베이스라인이 빠짐없이 모이는지만
회귀로 잡는다(전문가 감수 출발점).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPT = _BACKEND / "scripts" / "region_weights_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("region_weights_report", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_collect_params_has_all_knobs() -> None:
    """사전 5종 + 엔진 상수 7개가 모두 수집된다."""
    mod = _load()
    params = mod.collect_params()
    dicts = params["dictionaries"]
    for fname in (
        "region_layer_weights.json", "region_dominance_rules.json",
        "region_intent_weights.json", "region_geo_signal_rules.json",
        "region_geo_feature_elements.json",
    ):
        assert fname in dicts, f"{fname} 누락"
    # 핵심 매칭 파라미터 존재.
    assert "user_match" in dicts["region_dominance_rules.json"]
    assert len(params["engine_constants"]) == 7
    assert params["engine_constants"]["_INHERIT_DECAY"] > 0


def test_report_writes_review_sheet(tmp_path: Path) -> None:
    """리뷰 시트 json·md 생성 + 베이스라인 분포 포함."""
    mod = _load()
    rc = mod.main(["x", str(tmp_path)])
    assert rc == 0
    review = json.loads((tmp_path / "region_weights_review.json").read_text("utf-8"))
    assert "params" in review and "baseline" in review
    md = (tmp_path / "region_weights_review.md").read_text("utf-8")
    assert "튜닝 리뷰 시트" in md
    # 스냅샷이 있으면 baseline 분포가 채워진다(없으면 available False).
    base = review["baseline"]
    if base.get("available"):
        assert base["by_dominance"] and base["dominant_element"]
