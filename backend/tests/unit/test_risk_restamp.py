"""재스탬프 절차 가드 회귀 (감수 20차 조건 1).

불변 판정의 기준은 저장된 감수 해시(reviewHashes)다 — **변경이 먼저 커밋되어도**
저장 해시와 다르면 반드시 강등 대상으로 분류돼야 한다(작업 순서 비의존). git HEAD
비교는 해시 스키마 이행 시의 보조 진단일 뿐이다.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "risk_restamp", _BACKEND / "scripts" / "risk_restamp.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_reviewed_items_all_unchanged() -> None:
    """현재 리포 상태 — 저장 감수 해시 기준 변경 항목 0(스탬프 정합)."""
    tool = _load_tool()
    unchanged, changed = tool.classify(_BACKEND / "dictionaries" / "risks")
    assert changed == []
    assert len(unchanged) >= 30


def test_rule_change_demoted_even_if_committed(tmp_path: Path) -> None:
    """룰 변경이 '이미 커밋된 것과 동일한 상황'에서도 반드시 강등 분류된다.

    임시 사전 사본에서 reviewed 항목의 trigger를 변경 — git HEAD와 무관하게 저장된
    reviewHashes와 재계산이 불일치하므로 changed로 분류돼야 한다(커밋 순서 비의존:
    이 사본엔 git 이력 자체가 없어 HEAD 비교는 불가능한 조건이다).
    """
    tool = _load_tool()
    risks = tmp_path / "risks"
    shutil.copytree(_BACKEND / "dictionaries" / "risks", risks)
    target = risks / "finance.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    victim = next(i for i in data["items"] if i.get("reviewed"))
    victim["triggerRules"][0]["strength"] = 0.99  # 룰 본문 변경
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    unchanged, changed = tool.classify(risks)
    assert victim["riskId"] in changed
    assert victim["riskId"] not in unchanged


def test_missing_stamp_counts_as_changed(tmp_path: Path) -> None:
    """scope 대비 해시 누락(부분 스탬프)도 불변으로 오판하지 않는다."""
    tool = _load_tool()
    risks = tmp_path / "risks"
    shutil.copytree(_BACKEND / "dictionaries" / "risks", risks)
    target = risks / "finance.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    victim = next(i for i in data["items"] if i.get("reviewed"))
    victim["reviewHashes"] = {}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _, changed = tool.classify(risks)
    assert victim["riskId"] in changed
