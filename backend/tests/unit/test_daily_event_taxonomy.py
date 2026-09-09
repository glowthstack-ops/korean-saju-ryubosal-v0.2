"""OA-9b — 사건 분류(taxonomy)와 카탈로그의 정합.

분류는 **엔진이 로드하지 않는 inert 메타데이터**다. 그래서 조용히 낡을 수 있다 —
카탈로그에서 사건이 추가·삭제되거나 valence·headline_slots 가 바뀌어도 아무 데서도
터지지 않는다. 그 상태에서 G0/G1 shadow 가 이 파일을 읽으면 **틀린 구조 위에서
측정**하게 되므로, 정합을 회귀로 못박는다.

`primary_evidence_family` 는 기계 산출이 아니라 명리 판정이라 값 자체는 검증하지
않는다. 다만 **자기가 선언한 증거 목록 안에 있는지**는 강제한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import saju_engines.daily_ilju_fortune as M

_DICTS = Path(M.__file__).resolve().parents[3] / "dictionaries" / "daily_fortune"

#: 재성 — 주제(재물·거래·자원) 활성 신호. G0 판정의 기준이다.
_WEALTH_TEN_GODS = ("편재", "정재")
#: 합회·운성은 2026-09-10 §22-7 확장에서 추가(합·12운성이 출전권인 사건의 정직한 분류).
_EVIDENCE_FAMILIES = {"비겁", "식상", "재성", "관성", "인성", "충형파해", "합회", "운성"}
_CONDITIONS = {"favorable_only", "requires_adverse", "mixed_trigger"}
_ROLES = {"full", "support_only", "caution_only"}
_G0_SCOPES = {"money_slice", "deferred_document", "not_applicable"}


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return json.loads((_DICTS / "daily_event_taxonomy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog() -> dict:
    return M.load_daily_dicts().catalog["events"]


def _headline_role(event: dict) -> str:
    """카탈로그에서 파생되는 헤드라인 역할 — 분류가 이것과 어긋나면 안 된다."""
    slots = event.get("headline_slots") or event["slots"]
    if "good" in slots:
        return "full"
    if "caution" in slots:
        return "caution_only"
    return "support_only"


# ── 커버리지 ───────────────────────────────────────────────────────────────


def test_every_catalog_event_is_classified(taxonomy, catalog) -> None:
    missing = sorted(set(catalog) - set(taxonomy["events"]))
    assert not missing, f"분류 누락: {missing}"


def test_no_orphan_classification(taxonomy, catalog) -> None:
    orphan = sorted(set(taxonomy["events"]) - set(catalog))
    assert not orphan, f"카탈로그에 없는 사건이 분류돼 있다: {orphan}"


# ── 카탈로그와의 정합 ──────────────────────────────────────────────────────


def test_domain_and_polarity_match_catalog(taxonomy, catalog) -> None:
    for key, t in taxonomy["events"].items():
        assert t["domain"] == catalog[key]["domain"], key
        assert t["polarity"] == catalog[key]["valence"], key


def test_headline_role_matches_catalog(taxonomy, catalog) -> None:
    """자격 개방·철회(OA-6a 계열)가 분류에 반영되지 않으면 여기서 터진다."""
    for key, t in taxonomy["events"].items():
        assert t["headline_role"] == _headline_role(catalog[key]), key


# ── 어휘 ───────────────────────────────────────────────────────────────────


def test_vocabulary_is_closed(taxonomy) -> None:
    for key, t in taxonomy["events"].items():
        assert t["manifestation_condition"] in _CONDITIONS, key
        assert t["headline_role"] in _ROLES, key
        assert t["g0_rollout_scope"] in _G0_SCOPES, key
        for field in ("subject_evidence", "adverse_evidence"):
            unknown = set(t[field]) - _EVIDENCE_FAMILIES
            assert not unknown, f"{key}.{field}: {unknown}"


def test_primary_evidence_is_declared(taxonomy) -> None:
    """대표 원인군이 자기 증거 목록 밖에서 나오면 안 된다."""
    for key, t in taxonomy["events"].items():
        declared = set(t["subject_evidence"]) | set(t["adverse_evidence"])
        assert t["primary_evidence_family"] in declared, key


# ── 극성 게이트 불변식 (G0 의 전제) ────────────────────────────────────────


def test_adverse_evidence_only_on_caution(taxonomy) -> None:
    """길 사건에 불리 근거가 붙어 있으면 극성 구분이 이미 무너진 것이다."""
    for key, t in taxonomy["events"].items():
        if t["polarity"] == "good":
            assert not t["adverse_evidence"], key


def test_requires_adverse_declares_evidence(taxonomy) -> None:
    for key, t in taxonomy["events"].items():
        if t["manifestation_condition"] == "requires_adverse":
            assert t["adverse_evidence"], key


def test_every_caution_requires_adverse(taxonomy) -> None:
    """주의 사건은 예외 없이 별도 불리 근거를 요구한다 — G0 의 목표 상태."""
    for key, t in taxonomy["events"].items():
        if t["polarity"] == "caution":
            assert t["manifestation_condition"] == "requires_adverse", key


# ── G0 대상 판정은 기계적으로 검증 가능하다 ───────────────────────────────


def test_g0_candidate_equals_wealth_lifted_caution(taxonomy, catalog) -> None:
    """`g0_candidate` = caution 이면서 재성 양수 기여를 받는다 — 동치여야 한다.

    이 동치가 깨지면 G0 범위가 사람 판단으로 흔들린다.
    """
    for key, t in taxonomy["events"].items():
        tg = catalog[key].get("ten_god_affinity") or {}
        wealth_lifted = any(tg.get(g, 0.0) > 0 for g in _WEALTH_TEN_GODS)
        expected = t["polarity"] == "caution" and wealth_lifted
        assert t["g0_candidate"] is expected, (
            f"{key}: caution={t['polarity'] == 'caution'} 재성양수={wealth_lifted}"
        )


def test_g0_candidates_declare_wealth_as_subject_not_adverse(taxonomy) -> None:
    """재성은 **주제 활성** 근거일 뿐 불리 발현 근거가 아니다(G0 핵심 계약)."""
    for key, t in taxonomy["events"].items():
        if not t["g0_candidate"]:
            continue
        assert "재성" in t["subject_evidence"], key
        assert "재성" not in t["adverse_evidence"], (
            f"{key}: 같은 재성 근거가 주제와 불리 발현을 겸하고 있다"
        )


def test_g0_candidates_have_independent_adverse_evidence(taxonomy) -> None:
    """재성 말고 독립된 불리 근거가 있어야 G0 게이트를 통과할 여지가 생긴다."""
    for key, t in taxonomy["events"].items():
        if t["g0_candidate"]:
            assert set(t["adverse_evidence"]) - {"재성"}, key


def test_g0_scope_is_money_only_for_now(taxonomy) -> None:
    """1차 적용 범위는 money 도메인으로 승인됐다 — 조용히 넓어지면 안 된다."""
    scoped = {k for k, t in taxonomy["events"].items() if t["g0_rollout_scope"] == "money_slice"}
    assert scoped == {"overspend_caution", "lend_money_caution"}
    for key, t in taxonomy["events"].items():
        if t["g0_rollout_scope"] != "not_applicable":
            assert t["g0_candidate"], key


# ── 분류가 사전 스냅샷을 오염시키지 않는다 ────────────────────────────────


def test_taxonomy_is_not_part_of_runtime_snapshot() -> None:
    """엔진이 로드하는 3종에 들어가 있으면 inert 가 아니다."""
    from saju_engines.daily_fortune_snapshot import SOURCES

    assert "daily_event_taxonomy.json" not in {name for name, _ in SOURCES}


def test_taxonomy_declares_inert_status(taxonomy) -> None:
    assert taxonomy["runtime_status"] == "INERT"
    assert taxonomy["review_status"] == "PENDING"


# ── OA-9m 이 딛고 설 사실 ─────────────────────────────────────────────────


def test_move_domain_now_has_good_events(taxonomy) -> None:
    """move 의 헤드라인 표 0장은 자격 설정이 아니라 사건 부재에서 왔다(OA-9b findings).

    2026-09-10 §22-7 확장으로 길 move 사건(smooth_trip·errand_done)이 생겨 OA-9m 의
    전제가 바뀌었다 — 이 테스트가 그 사실을 고정한다. 다시 0종이 되면 회귀다.
    """
    move = {k: t for k, t in taxonomy["events"].items() if t["domain"] == "move"}
    assert move
    good = {k for k, t in move.items() if t["polarity"] == "good"}
    assert good == {"smooth_trip", "errand_done"}
    assert any(t["polarity"] == "caution" for t in move.values())
