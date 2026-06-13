"""Phase 1 사전 데이터 검증 — 엔진 일치(SSOT)·스키마·충돌 검사(lint).

사전의 기계적 사실(십성표·지장간·생극·관계 글자)은 엔진 상수와 1:1 일치해야 한다
(엔진 = 유일 진실 공급원). 명리 매핑·가중치는 reviewed:false 초안으로, 여기서는
구조·범위·일관성만 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines.dictionaries import (
    EventMappingFile,
    RelationsFile,
    lint_dictionaries,
    validate_dictionaries,
)
from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    CONTROLS,
    GENERATES,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem

_DICT_DIR = Path(__file__).resolve().parents[2] / "dictionaries"


def _load(rel: str) -> dict:
    """사전 JSON 파일 로드."""
    return json.loads((_DICT_DIR / rel).read_text(encoding="utf-8"))


# ── 전체 통과 ────────────────────────────────────────────────────


def test_real_dictionaries_validate_and_lint_clean() -> None:
    """체크인된 사전 전체가 스키마 검증과 충돌 검사를 통과한다."""
    assert validate_dictionaries(_DICT_DIR) == []
    assert lint_dictionaries(_DICT_DIR) == []


# ── 엔진 일치 (기계적 사실) ──────────────────────────────────────


def test_stems_ten_god_table_matches_engine() -> None:
    """stems.json의 십성표(10×10)가 엔진 ten_god()과 전부 일치한다."""
    data = _load("common/stems.json")
    assert len(data["items"]) == 10
    for item in data["items"]:
        target = Stem(item["stem"])
        assert item["element"] == str(STEM_ELEMENT[target])
        table = item["tenGodByDayMaster"]
        assert len(table) == 10
        for dm_str, expected in table.items():
            assert expected == str(ten_god(Stem(dm_str), target))


def test_branches_hidden_stems_match_engine() -> None:
    """branches.json의 지장간 구성·가중치가 엔진 표와 일치한다."""
    data = _load("common/branches.json")
    assert len(data["items"]) == 12
    for item in data["items"]:
        b = Branch(item["branch"])
        assert item["element"] == str(BRANCH_ELEMENT[b])
        engine = [(str(s), str(k), w) for s, k, w in hidden_stems_for(b)]
        ours = [(h["stem"], h["type"], h["weight"]) for h in item["hiddenStems"]]
        assert ours == engine


def test_elements_cycle_matches_engine() -> None:
    """elements.json의 생극이 엔진 GENERATES/CONTROLS와 일치한다."""
    data = _load("common/elements.json")
    assert len(data["items"]) == 5
    for item in data["items"]:
        e = Element(item["element"])
        assert item["generates"] == str(GENERATES[e])
        assert item["controls"] == str(CONTROLS[e])


def test_relations_fixed_pairs_match_engine_tables() -> None:
    """relations.json의 글자 고정 항목이 엔진 관계 테이블을 정확히 커버한다."""
    parsed = RelationsFile.model_validate(_load("relations.json"))
    by_type: dict[str, list] = {}
    for item in parsed.items:
        by_type.setdefault(item.type, []).append(item)

    combos = {frozenset(Stem(p) for p in i.participants): i for i in by_type["stem_combination"]}
    assert set(combos) == set(STEM_COMBINATIONS)
    for pair, item in combos.items():
        assert item.result_element == str(STEM_COMBINATIONS[pair])

    sixes = {frozenset(Branch(p) for p in i.participants): i for i in by_type["six_combination"]}
    assert set(sixes) == set(SIX_COMBINATIONS)

    clashes = {frozenset(Branch(p) for p in i.participants) for i in by_type["branch_clash"]}
    assert clashes == BRANCH_CLASHES

    assert len(by_type["three_harmony"]) == 4
    assert len(by_type["directional"]) == 4
    assert len(by_type["branch_break"]) == 6
    assert len(by_type["harm"]) == 6
    assert len(by_type["punishment_triple"]) == 2
    assert len(by_type["punishment_mutual"]) == 1
    assert len(by_type["self_punishment"]) == 4


def test_taxonomy_covers_event_keys_exactly() -> None:
    """21키 taxonomy_v2(EVENT_KO)가 EventKeyV2 전체를 중복 없이 1:1 커버한다(Phase 7).

    레거시 events/taxonomy.json은 구 25키 보존 아티팩트로 graph_builder가 21키로 리맵한다.
    """
    from saju_shared_types.event_engine import EventKeyV2
    from saju_shared_types.event_taxonomy_v2 import EVENT_KO

    assert set(EVENT_KO) == set(EventKeyV2)
    assert len(EVENT_KO) == 21


def test_all_items_carry_reviewed_flag() -> None:
    """모든 사전 항목은 reviewed 플래그(검수 워크플로)를 갖는다."""
    for rel in [
        "common/stems.json", "common/branches.json", "common/ten_gods.json",
        "common/elements.json", "relations.json", "events/taxonomy.json",
        "events/career_change.json", "events/relocation.json", "favorability_rules.json",
    ]:
        for item in _load(rel)["items"]:
            assert item.get("reviewed") is False, f"{rel}: 초안 항목은 reviewed:false"


# ── lint 충돌 검출 ───────────────────────────────────────────────


def _write(tmp: Path, rel: str, payload: dict) -> None:
    """임시 사전 디렉토리에 JSON 파일을 만든다."""
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_lint_catches_duplicate_relation_id(tmp_path: Path) -> None:
    """relation id 중복은 lint 위반."""
    entry = {
        "id": "rel_dup", "type": "branch_clash", "name": "중복",
        "participants": ["子", "午"], "resultElement": None,
        "possibleModes": ["충발"], "eventDomains": [], "baseScore": 0.5, "reviewed": False,
    }
    _write(tmp_path, "relations.json", {"version": "1.0.0", "items": [entry, dict(entry)]})
    errors = lint_dictionaries(tmp_path)
    assert any("relation id 중복" in e for e in errors)


def test_lint_catches_gisin_positive(tmp_path: Path) -> None:
    """기신 신호인데 polarity=positive면 lint 위반."""
    _write(tmp_path, "events/career_change.json", {
        "version": "1.0.0", "domain": "career",
        "items": [{
            "signal": {"favorability": "기신"},
            "eventCandidates": [
                {"event": "career_change", "score": 0.5, "polarity": "positive"}
            ],
            "reviewed": False,
        }],
    })
    errors = lint_dictionaries(tmp_path)
    assert any("기신 신호인데 polarity=positive" in e for e in errors)


def test_lint_catches_strong_opposing_candidates(tmp_path: Path) -> None:
    """같은 신호가 상반 이벤트를 동시에 강하게(≥0.7) 유발하면 lint 위반."""
    _write(tmp_path, "events/relocation.json", {
        "version": "1.0.0", "domain": "relocation",
        "items": [{
            "signal": {"relation": "branch_clash"},
            "eventCandidates": [
                {"event": "relocation", "score": 0.8, "polarity": "positive"},
                {"event": "relationship_end", "score": 0.75, "polarity": "negative_or_forced"},
            ],
            "reviewed": False,
        }],
    })
    errors = lint_dictionaries(tmp_path)
    assert any("상반 이벤트를 동시에 강하게" in e for e in errors)


def test_validate_rejects_bad_event_key(tmp_path: Path) -> None:
    """존재하지 않는 EventKey는 스키마 위반(dict:validate)."""
    _write(tmp_path, "events/taxonomy.json", {
        "version": "1.0.0",
        "items": [
            {"eventKey": "lottery_win", "ko": "없음", "eventType": "instant", "reviewed": False}
        ],
    })
    errors = validate_dictionaries(tmp_path)
    assert errors and "taxonomy" in errors[0]


def test_validate_rejects_out_of_range_score(tmp_path: Path) -> None:
    """사전 점수는 0~1 범위를 벗어나면 스키마 위반."""
    _write(tmp_path, "events/career_change.json", {
        "version": "1.0.0", "domain": "career",
        "items": [{
            "signal": {"tenGod": "정관"},
            "eventCandidates": [
                {"event": "career_change", "score": 1.5, "polarity": "positive"}
            ],
            "reviewed": False,
        }],
    })
    errors = validate_dictionaries(tmp_path)
    assert errors and "career_change" in errors[0]


def test_event_mapping_schema_roundtrip() -> None:
    """체크인된 이벤트 매핑 파일이 스키마로 라운드트립된다."""
    for rel in ("events/career_change.json", "events/relocation.json"):
        parsed = EventMappingFile.model_validate(_load(rel))
        assert parsed.items, rel
        for item in parsed.items:
            assert item.event_candidates
