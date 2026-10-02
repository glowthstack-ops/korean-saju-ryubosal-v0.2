"""사문(死文) 경로 회귀 — "사전·필드가 실제로 읽히는가" (2026-09-10, daily 감사 기법 이식).

감사에서 확인된 죽은 경로 4건을 고정한다:
1. 근거 묶음의 `contradicts` 가 항상 빈 배열(컴파일 그래프에 그 엣지 타입이 0건).
2. 운 기둥 12운성 해설이 원국용 `natal` 문장을 쓰고 `incoming` 은 한 번도 읽히지 않음.
3. `void_repetition_modifier.json`·`user_profile_event_gate.json` 을 게이트가 읽지 않음.
4. 리포트 표지 '사전 버전' 이 기본값 "1.0.0" 고정.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from saju_engines import addendum_gate_modifier as AGM
from saju_engines.dictionary_version import dictionaries_fingerprint, report_dict_version
from saju_engines.graph_builder import GRAPH_VERSION, load_event_graph
from saju_engines.graph_retrieval import GraphIndex
from saju_shared_types.events import EventKey

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


# ── 1. contradicts ───────────────────────────────────────────────────────────


def test_contradicts_is_derived_from_opposite_polarity_rules() -> None:
    """같은 이벤트를 반대 극성으로 촉발하는 규칙이 있으면 충돌 근거가 비지 않는다."""
    idx = GraphIndex(load_event_graph(_BACKEND / "compiled" / f"event_graph_v{GRAPH_VERSION}.json"))
    bundles = idx.retrieve(list(EventKey))
    with_contra = [b for b in bundles if b.contradicts]
    assert with_contra, "contradicts 가 전 이벤트에서 비어 있다 — 파생 로직이 죽었다"
    for b in with_contra:
        weights = idx._polarity_weights(f"event_{b.event_key}", b.event_key)
        dominant = "negative_or_forced" if (
            weights["negative_or_forced"] > weights["positive"]
        ) else "positive"
        by_label = {
            idx.label(e.from_): e.from_
            for e in idx.in_edges[f"event_{b.event_key}"] if e.type == "triggers"
        }
        for label in b.contradicts:  # 라벨(규칙 문장)로 돌려준다 — hints 와 같은 형식
            rule_id = by_label[label]
            assert idx.nodes[rule_id].type == "interpretation_rule"
            pol = idx._rule_polarity(rule_id, b.event_key)
            assert pol in {"positive", "negative_or_forced"} and pol != dominant
    # 지배 극성 규칙은 충돌 근거에 들어가지 않는다.
    for b in bundles:
        weights = idx._polarity_weights(f"event_{b.event_key}", b.event_key)
        if weights["positive"] and weights["negative_or_forced"]:
            assert b.contradicts, b.event_key


# ── 2. 운 기둥 12운성 → incoming ─────────────────────────────────────────────


def test_luck_pillar_stage_text_uses_incoming_sentence() -> None:
    src = (
        _BACKEND / "packages" / "saju_engines" / "saju_engines" / "chart_interpretation.py"
    ).read_text(encoding="utf-8")
    start = src.index("def build_luck_grounding")
    fn = src[start : src.index("def ", start + 10)]
    assert 'stage.get("incoming")' in fn, "운 기둥 해설이 incoming 문장을 쓰지 않는다"
    stages_path = _DICTS / "interpretations" / "twelve_stages_text.json"
    items = json.loads(stages_path.read_text("utf-8"))["items"]
    assert all(item.get("incoming") for item in items), "incoming 문장이 비어 있는 스테이지가 있다"
    assert all(item["incoming"] != item["natal"] for item in items)


# ── 3. 게이트 사전 ───────────────────────────────────────────────────────────


def test_void_delta_is_read_from_dictionary() -> None:
    raw = json.loads((_DICTS / "event_engine" / "void_repetition_modifier.json").read_text("utf-8"))
    assert raw["runtime_status"] == "PARAMETER_SOURCE"
    expected = raw["void_activation_modifier"]["score_effect"]["void_unresolved"]
    assert AGM.AddendumGateModifier(_DICTS).void_unresolved_delta == expected
    assert AGM.load_void_unresolved_delta(_DICTS) == expected
    # 확정 의미론(2026-08-21 合則不能空): 해공 가산은 없다.
    assert raw["void_activation_modifier"]["score_effect"]["void_resolved_by_relation"] == 0
    # 파일이 없으면 기본값으로 물러난다(운영 차단 금지).
    assert AGM.load_void_unresolved_delta(Path("/nonexistent")) == AGM._VOID_UNRESOLVED_DEFAULT


def test_profile_gate_rules_declare_implementing_reason_codes() -> None:
    raw = json.loads((_DICTS / "event_engine" / "user_profile_event_gate.json").read_text("utf-8"))
    assert raw["runtime_status"] == "SPEC_ONLY"
    impl = raw["implemented_by"]
    assert set(impl) == set(raw["rules"]), "implemented_by 는 rules 와 키가 같아야 한다"
    src = (
        _BACKEND / "packages" / "saju_engines" / "saju_engines" / "addendum_gate_modifier.py"
    ).read_text(encoding="utf-8")
    codes = set(re.findall(r'reasons\.append\("([A-Za-z_]+)"\)', src))
    for rule, reason_codes in impl.items():
        for code in reason_codes:
            assert code in codes, (rule, code)
    assert any(impl.values()), "구현된 규칙이 하나도 없다"


# ── 4. 리포트 사전 버전 ───────────────────────────────────────────────────────


def test_report_dict_version_is_not_the_stale_default(tmp_path: Path) -> None:
    v = report_dict_version(_DICTS)
    assert v.startswith("dict-") and v != "dict-none" and "1.0.0" not in v
    assert dictionaries_fingerprint(_DICTS) == dictionaries_fingerprint(_DICTS)  # 결정론
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    fp1 = dictionaries_fingerprint(tmp_path)
    (tmp_path / "a.json").write_text('{"x": 1}', encoding="utf-8")
    dictionaries_fingerprint.cache_clear()
    assert dictionaries_fingerprint(tmp_path) != fp1  # 내용이 바뀌면 지문이 바뀐다
    svc_path = _BACKEND / "apps" / "api" / "saju_api" / "services" / "report_service.py"
    svc = svc_path.read_text("utf-8")
    assert "dict_version=report_dict_version(_DICTS)" in svc
