"""RelationPalaceEngine 검증 (이벤트 엔진 재설계 Phase 6).

합충형파해 종류 × 궁성 활성으로 사건화 보너스·생활영역(palace) 부여를 확인한다(타입 불변).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> RelationPalaceEngine:
    return RelationPalaceEngine(_DICTS)


def _cand(event: str, score: int = 50) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score)


def test_month_palace_activates_career() -> None:
    e = _eng()
    # 세운 충이 월주를 자극 → career_change 발동 가점 + palace=월주.
    act = [RelationActivation(RelationKind.CHUNG, Pillar4.MONTH, LuckLayer.SEWOON)]
    out = e.apply([_cand("career_change", 50)], act)
    c = out[0]
    assert c.score > 50
    assert c.palace is Pillar4.MONTH
    assert any(r.startswith("REL_CHUNG_month_pillar") for r in c.reason_codes)


def test_palace_mismatch_no_bonus() -> None:
    e = _eng()
    # 시주 자극인데 후보는 직업(career_change) → 시주 event_domains에 없으므로 무보정.
    act = [RelationActivation(RelationKind.HAP, Pillar4.HOUR, LuckLayer.SEWOON)]
    out = e.apply([_cand("career_change", 50)], act)
    assert out[0].score == 50
    assert out[0].palace is None


def test_compound_hyeong_chung_bonus() -> None:
    e = _eng()
    act = [
        RelationActivation(RelationKind.HYEONG, Pillar4.MONTH, LuckLayer.SEWOON),
        RelationActivation(RelationKind.CHUNG, Pillar4.MONTH, LuckLayer.SEWOON),
    ]
    out = e.apply([_cand("career_change", 50)], act)
    assert "REL_COMPOUND" in out[0].reason_codes
    assert out[0].score > 60


def test_relation_to_palace_rule_boost() -> None:
    e = _eng()
    # 일주 자극 + relocation: day_pillar event_domains에 relocation 포함 → 가점·palace.
    act = [RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON)]
    out = e.apply([_cand("relocation", 50)], act)
    assert out[0].palace is Pillar4.DAY
    assert out[0].score > 50


def test_no_activation_unchanged() -> None:
    e = _eng()
    out = e.apply([_cand("wealth_change", 50)], [])
    assert out[0].score == 50
    assert out[0].palace is None


# Task 2 — 복음(伏吟) 결혼 보조 트리거: 운 지지=원국 일지 → 일지궁 marriage_signal 강화.
def test_bokeum_day_boosts_marriage_signal() -> None:
    e = _eng()
    act = [
        RelationActivation(RelationKind.BOKEUM, Pillar4.DAY, LuckLayer.SEWOON, position="branch"),
    ]
    out = e.apply([_cand("marriage_signal", 50)], act)
    c = out[0]
    assert c.score > 50  # 복음이 결혼 신호를 강화(단독 생성 아님, 기존 후보 가점)
    assert c.palace is Pillar4.DAY
    assert any(r.startswith("REL_BOKEUM_day_pillar") for r in c.reason_codes)


def test_bokeum_weaker_than_clash() -> None:
    e = _eng()
    bok = e.apply(
        [_cand("marriage_signal", 50)],
        [RelationActivation(RelationKind.BOKEUM, Pillar4.DAY, LuckLayer.SEWOON, position="branch")],
    )[0]
    chung = e.apply(
        [_cand("marriage_signal", 50)],
        [RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON, position="branch")],
    )[0]
    # 복음(보조 트리거, bonus 5)은 충(bonus 10)보다 약하게 가점된다.
    assert 50 < bok.score <= chung.score


def test_bokeum_activation_detection() -> None:
    """_bokeum_activations — 운 지지가 원국 일지와 같을 때만 BOKEUM/일지 발동(타 지지는 미발동)."""
    from types import SimpleNamespace

    from saju_api.services.manse_service import calculate
    from saju_engines.event_engine_v2 import _bokeum_activations
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1985-03-15", birth_time="14:30",
        birth_place_name="서울", gender="female",
    ))
    assert r.pillars is not None
    day_branch = r.pillars.day.branch  # 癸丑 → 丑
    # 일지와 같은 지지 → 복음 발동(일지궁).
    acts = _bokeum_activations(
        r, cast("LuckPillar", SimpleNamespace(branch=day_branch)), LuckLayer.SEWOON)
    assert len(acts) == 1
    assert acts[0].kind is RelationKind.BOKEUM and acts[0].palace is Pillar4.DAY
    assert acts[0].position == "branch" and acts[0].layer is LuckLayer.SEWOON
    # 다른 지지 → 미발동.
    other = "寅" if day_branch != "寅" else "卯"
    assert _bokeum_activations(
        r, cast("LuckPillar", SimpleNamespace(branch=other)), LuckLayer.SEWOON) == []


# ── B2 보강(RELATIONSHIP_EVENT_SYSTEM 부록 B) — REL_COMPOUND 고아 방지 불변식 ──────


def test_compound_always_with_constituent_codes() -> None:
    """정상 경로에서 REL_COMPOUND는 반드시 구성 REL 코드와 동반한다(고아 금지).

    구성 코드가 제거되면 출력 가드가 COMPOUND 단독을 보수적 미판정해 방향 누수가
    재발할 수 있으므로, 엔진 산출 불변식으로 고정한다.
    """
    e = _eng()
    act = [
        RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON),
        RelationActivation(RelationKind.HAP, Pillar4.DAY, LuckLayer.SEWOON),
    ]
    out = e.apply([_cand("relationship_change", 50)], act)
    codes = out[0].reason_codes
    assert "REL_COMPOUND" in codes  # 합+충 복합 → COMPOUND 발생 전제 확인
    assert any(c.startswith("REL_") and c != "REL_COMPOUND" for c in codes)


# ── 인성 동요 신호(2026-08-10, relation_target_ten_god_rules) — feature flag ──────


def _resource_clash_act() -> RelationActivation:
    """년주 충 + 피자극 글자=정인 — 년주는 contract_document 도메인이 아니어서
    기존 (관계,궁성) 경로가 매칭하지 않는 격리 조건이다."""
    return RelationActivation(
        RelationKind.CHUNG, Pillar4.YEAR, LuckLayer.SEWOON,
        position="branch", target_ten_god="ZHENGYIN",
    )


def test_renewal_off_by_default_unchanged() -> None:
    """flag OFF(기본) — 인성 충이어도 기존 결과 byte 불변."""
    e = _eng()
    out = e.apply([_cand("contract_document", 50)], [_resource_clash_act()])
    assert out[0].score == 50
    assert out[0].palace is None
    assert not any("RESOURCE" in r for r in out[0].reason_codes)


def test_renewal_on_boosts_contract_document() -> None:
    """flag ON + 인성 세력 충분 — 문서 교체 가산 + RENEWAL reason + palace 부여."""
    e = _eng()
    out = e.apply(
        [_cand("contract_document", 50)], [_resource_clash_act()],
        renewal_enabled=True, ten_god_group_powers={"resource": 25.0},
    )
    c = out[0]
    assert c.score > 50
    assert "REL_CHUNG_RESOURCE_RENEWAL" in c.reason_codes
    assert c.palace is Pillar4.YEAR


def test_renewal_weak_resource_gated() -> None:
    """인성군 세력이 약하면(12% 미만) 축소 가산 + UNROOTED(동요) reason.

    스크립트 유래 규칙 '인성이 뿌리내려야 충을 버텨 성사로 이어진다'의 계산 번역 —
    기존 십성군 세력 재사용(2026-08-10 사용자 확정).
    """
    e = _eng()
    strong = e.apply(
        [_cand("contract_document", 50)], [_resource_clash_act()],
        renewal_enabled=True, ten_god_group_powers={"resource": 25.0},
    )[0]
    weak = e.apply(
        [_cand("contract_document", 50)], [_resource_clash_act()],
        renewal_enabled=True, ten_god_group_powers={"resource": 5.0},
    )[0]
    assert "REL_CHUNG_RESOURCE_UNROOTED" in weak.reason_codes
    assert "REL_CHUNG_RESOURCE_RENEWAL" not in weak.reason_codes
    assert 50 < weak.score < strong.score


def test_renewal_powers_unknown_uses_base_bonus() -> None:
    """세력 정보 미제공(None) — 게이트 판정 불가 시 base_bonus(동요 격하 없음)."""
    e = _eng()
    out = e.apply(
        [_cand("contract_document", 50)], [_resource_clash_act()],
        renewal_enabled=True, ten_god_group_powers=None,
    )[0]
    assert "REL_CHUNG_RESOURCE_RENEWAL" in out.reason_codes


def test_renewal_non_resource_target_no_match() -> None:
    """피자극 십성이 인성이 아니면(재성 등) 룰 미적용."""
    e = _eng()
    act = RelationActivation(
        RelationKind.CHUNG, Pillar4.YEAR, LuckLayer.SEWOON,
        position="branch", target_ten_god="ZHENGCAI",
    )
    out = e.apply(
        [_cand("contract_document", 50)], [act],
        renewal_enabled=True, ten_god_group_powers={"resource": 25.0},
    )
    assert out[0].score == 50


def test_renewal_relocation_and_career_also_boosted() -> None:
    """likely_events 3종(contract_document/relocation/career_change) 모두 가산 대상."""
    e = _eng()
    for ek in ("relocation", "career_change"):
        out = e.apply(
            [_cand(ek, 50)], [_resource_clash_act()],
            renewal_enabled=True, ten_god_group_powers={"resource": 25.0},
        )
        assert out[0].score > 50, ek
        assert "REL_CHUNG_RESOURCE_RENEWAL" in out[0].reason_codes, ek
