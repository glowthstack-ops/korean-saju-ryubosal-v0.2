"""해석 사전(interpretations/) 회귀 테스트 (v2.2.1, docs/05).

검증 항목:
1. 실사전 전체가 validate(스키마) + lint(엔진 교차검증·커버리지·auxiliary 규칙) 통과
2. ilju.json computed 블록 ↔ 만세력 엔진 함수(twelve_unseong 등) 직접 대조
   — dictionaries._expected_twelve_stage 공식이 엔진과 갈라지면 여기서 잡힌다
3. 변조 감지 — computed 값을 틀리게 바꾸면 lint가 잡는다
4. relations_text ↔ relations.json 1:1 정합 + 암합 auxiliary 강제
5. 단정 표현 금지 — 사전 콘텐츠에 확정 표현 미포함 (절대 원칙 3)
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines.dictionaries import (
    IljuFile,
    _lint_ilju,
    lint_dictionaries,
    validate_dictionaries,
)
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import hidden_stems_for, ten_god
from saju_shared_types.enums import Branch, Stem

_DICT_DIR = Path(__file__).resolve().parents[2] / "dictionaries"
_INTERP_DIR = _DICT_DIR / "interpretations"
# 사전 콘텐츠 단정 표현 금지(절대 원칙 3) — narrative/meaning 류 서술 필드 대상.
_PROHIBITED_SUBSTRINGS = ("반드시", "무조건", "확정적으로", "100%")


def _load(name: str) -> dict:
    """interpretations/ 사전 JSON을 로드한다."""
    return json.loads((_INTERP_DIR / name).read_text(encoding="utf-8"))


def test_dictionaries_validate_and_lint_clean() -> None:
    """실사전 전체 — 스키마 검증과 lint(교차검증 포함)에 위반이 없어야 한다."""
    assert validate_dictionaries(_DICT_DIR) == []
    assert lint_dictionaries(_DICT_DIR) == []


def test_ilju_computed_matches_engine_functions() -> None:
    """ilju.json computed ↔ 만세력 엔진 함수 전수 대조(60건).

    lint의 자체 공식이 아니라 엔진 함수(twelve_unseong)를 직접 호출해
    공식 이원화로 인한 잠재 분기를 차단한다.
    """
    data = _load("ilju.json")
    assert len(data["items"]) == 60
    for item in data["items"]:
        ganji = item["ganji"]
        stem, branch = Stem(ganji[0]), Branch(ganji[1])
        hidden = hidden_stems_for(branch)
        main = next(entry[0] for entry in hidden if entry[1].value == "main")
        assert item["computed"]["iljiTenGod"] == str(ten_god(stem, Stem(main.value))), ganji
        assert item["computed"]["twelveStage"] == twelve_unseong(stem, branch), ganji
        assert item["computed"]["hiddenStems"] == [entry[0].value for entry in hidden], ganji


def test_lint_catches_tampered_computed() -> None:
    """computed 값을 변조하면 lint가 잡아야 한다(교차검증 실효성)."""
    data = _load("ilju.json")
    data["items"][0]["computed"]["iljiTenGod"] = "편관"  # 甲子 정인 → 변조
    tampered = IljuFile.model_validate(data)
    errors = _lint_ilju(tampered)
    assert any("甲子" in err and "iljiTenGod" in err for err in errors)


def test_relations_text_one_to_one_with_relations() -> None:
    """relations_text.json은 relations.json의 모든 id를 빠짐없이, 초과 없이 다룬다."""
    base = json.loads((_DICT_DIR / "relations.json").read_text(encoding="utf-8"))
    text = _load("relations_text.json")
    base_ids = {item["id"] for item in base["items"]}
    text_ids = {item["id"] for item in text["items"]}
    assert base_ids == text_ids


def test_amhap_is_auxiliary_only() -> None:
    """암합은 보조 자료(role=auxiliary) — 단독 결론 금지(2026-06-12 사용자 확정)."""
    text = _load("relations_text.json")
    amhap = [item for item in text["items"] if item["type"] == "amhap"]
    assert amhap and all(item["role"] == "auxiliary" for item in amhap)
    assert all("보조" in item["meaning"] for item in amhap)


def test_no_assertive_expressions_in_content() -> None:
    """서술 필드에 단정 표현이 없어야 한다(절대 원칙 3 — 사전 콘텐츠 동일 적용)."""
    targets: list[str] = []
    ilju = _load("ilju.json")
    for item in ilju["items"]:
        targets += [item["imagery"], item["narrative"], item["spouse_palace_note"]]
        targets += item["traits"]["light"] + item["traits"]["shadow"]
    for name, fields in (
        ("ten_gods_text.json", ("core", "metaphor", "natal", "excess", "absence",
                                "incoming", "asYongsin", "asGisin")),
        ("twelve_stages_text.json", ("core", "metaphor", "natal", "incoming")),
        ("relations_text.json", ("meaning", "natal", "fromLuck")),
    ):
        for item in _load(name)["items"]:
            targets += [item[field] for field in fields]
    violations = [
        (text[:40], bad)
        for text in targets
        for bad in _PROHIBITED_SUBSTRINGS
        if bad in text
    ]
    assert violations == []


def test_favorability_text_has_reversal() -> None:
    """용희기구한 5역할 + 흉신(기신·구신) 반전 조건 의무(구신 반전, 2026-06-12)."""
    data = _load("favorability_text.json")
    roles = {item["role"]: item for item in data["items"]}
    assert roles.keys() == {"용신", "희신", "기신", "구신", "한신"}
    # 구신은 4가지 반전(태과 제어·탐합망극·통관·제화)을 담는다.
    gusin = roles["구신"]["reversal"]
    assert "탐합망극" in gusin and "통관" in gusin and "제화" in gusin
    for role in ("기신", "구신"):
        assert len(roles[role]["reversal"]) >= 20


def test_ten_gods_and_stages_have_situational_fields() -> None:
    """일간 중심·상황 의존 원칙 — 원국/운유입/용신·기신 구분 서술이 비어 있지 않아야 한다."""
    for item in _load("ten_gods_text.json")["items"]:
        for field in ("natal", "excess", "absence", "incoming", "asYongsin", "asGisin"):
            assert len(item[field]) >= 20, (item["tenGod"], field)
    for item in _load("twelve_stages_text.json")["items"]:
        for field in ("natal", "incoming"):
            assert len(item[field]) >= 20, (item["stage"], field)
