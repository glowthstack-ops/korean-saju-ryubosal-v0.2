"""REL 근거의 source identity 회귀 (2026-07-31).

`REL_{kind}_{palace}` 에는 어느 운 층위·어느 글자가 발동시켰는지가 없다. 그래서 서로
다른 발동이 같은 문자열로 기록되고 "같은 근거가 중복 기록됐다" 로 오독된다 —
WC-SCORE 감사에서 72건 중 18건이 그랬고, 감사자(나) 자신이 실제로 오독했다.

기존 코드 문자열을 바꾸면 `marriage_output_guard` 와 리포트 근거 블록이 깨지므로,
**기존 `reason_codes` 는 그대로 두고 구조화 provenance 를 병렬 추가**한다.

여기서 고정하는 불변식:

    reason_codes            값·순서·중복 모두 불변
    score / quality         불변
    marriage_output_guard   불변
    reason_instances        감사 전용 — 사용자 출력·LLM 입력 미연결
    source_identity         입력 의미에서만 결정(배열 순서·객체 id 사용 금지)
    피연산자 정합            relation_id 의 피연산자 == 기록된 운·원국 글자

마지막 항목은 뒤늦게 추가됐다. 초판 fixture 가 `luck_branch=午` 에
`relation_id=rel_harm_申_亥` 를 물려 **성립하지도 않는 해(午亥)** 를 만들었는데,
identity 는 결정론적이라 아무 검사도 이를 잡지 못했다. identity 가 안정적인 것과
의미가 맞는 것은 별개다.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from saju_engines.relation_palace_engine import (  # noqa: E402
    RelationActivation,
    relation_operand_consistency,
    relation_reason_instance,
    relation_source_identity,
)
from saju_shared_types.event_engine import (  # noqa: E402
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)
from saju_shared_types.ganji_calendar import (  # noqa: E402
    RELATION_ID_SHAPE,
    RelationType,
)

# 육해 쌍은 子未·丑午·寅巳·卯辰·申亥·酉戌 — 申↔亥 는 실제로 성립한다.
_HARM_ID = "rel_harm_申_亥"
# 삼형 寅巳申 — 운 申 하나가 원국 寅·巳 두 자리를 동시에 자극한다(1:N 분해).
_TRIPLE_ID = "rel_punishment_triple_申_寅巳"


def _harm(layer: LuckLayer, luck_stem: str) -> RelationActivation:
    """申↔亥 해 발동. 지지 관계는 고정하고 층위·운 천간만 변수로 둔다."""
    return RelationActivation(
        RelationKind.HAE, Pillar4.DAY, layer, position="branch",
        relation_id=_HARM_ID,
        luck_stem=luck_stem, luck_branch="申", natal_branch="亥",
    )


def _triple(natal_branch: str, palace: Pillar4) -> RelationActivation:
    """寅巳申 삼형 발동 1건. 같은 운 글자가 서로 다른 원국 자리를 건드린다."""
    return RelationActivation(
        RelationKind.HYEONG, palace, LuckLayer.SEWOON, position="branch",
        relation_id=_TRIPLE_ID,
        luck_stem="甲", luck_branch="申", natal_branch=natal_branch,
    )


# ── source identity ──────────────────────────────────────────────────────


def test_same_code_from_different_layers_gets_distinct_identity() -> None:
    """같은 `REL_HAE_day` 라도 대운 발동과 세운 발동은 구분돼야 한다."""
    a = _harm(LuckLayer.DAEWOON, "壬")
    b = _harm(LuckLayer.SEWOON, "壬")
    assert relation_source_identity(a) != relation_source_identity(b)
    # 코드 문자열 자체는 여전히 같다 — 그래서 identity 가 필요했다.
    assert (
        relation_reason_instance(a, 1.0)["reason_code"]
        == relation_reason_instance(b, 1.0)["reason_code"]
    )


def test_same_layer_different_transit_stem_gets_distinct_identity() -> None:
    """같은 층위·같은 지지 관계라도 운 천간이 다르면 다른 발동이다.

    甲申 세운과 壬申 세운은 둘 다 亥 를 해하지만 별개 시점의 별개 발동이다.
    """
    a = _harm(LuckLayer.SEWOON, "甲")
    b = _harm(LuckLayer.SEWOON, "壬")
    assert relation_source_identity(a) != relation_source_identity(b)


def test_same_activation_yields_same_identity() -> None:
    """입력 의미가 같으면 항상 같은 값 — 배열 순서·객체 id 에 의존하지 않는다."""
    a = _harm(LuckLayer.DAEWOON, "壬")
    b = _harm(LuckLayer.DAEWOON, "壬")
    assert a is not b
    assert relation_source_identity(a) == relation_source_identity(b)


def test_identity_includes_natal_side() -> None:
    """같은 운 글자가 서로 다른 원국 글자를 건드리면 별개 발동이다.

    삼형 寅巳申 의 실제 1:N 분해다 — 원국 글자를 identity 에서 빼면 이 둘이 하나로
    붕괴한다. 억지로 만든 조합이 아니라 엔진이 실제로 내는 형태다.
    """
    a = _triple("寅", Pillar4.YEAR)
    b = _triple("巳", Pillar4.YEAR)
    assert relation_source_identity(a) != relation_source_identity(b)


# ── instance 내용 ────────────────────────────────────────────────────────


def test_instance_preserves_human_readable_fields() -> None:
    """해시만 남기면 감사에서 역추적할 수 없다 — 원필드를 보존한다."""
    inst = relation_reason_instance(_harm(LuckLayer.SEWOON, "甲"), 3.25)
    assert inst["reason_code"] == "REL_HAE_day_pillar"
    assert inst["source_layer"] == "sewoon"
    assert inst["natal_pillar"] == "day_pillar"
    assert inst["relation_kind"] == "HAE"
    assert inst["transit_ganzhi"] == "甲申"
    assert inst["natal_ganzhi"] == "亥"
    assert inst["relation_id"] == _HARM_ID
    assert inst["contribution"] == 3.25


# ── 피연산자 정합 ────────────────────────────────────────────────────────


def test_shape_table_covers_every_relation_type() -> None:
    """새 관계 종류를 추가하고 형태표를 빠뜨리면 여기서 깨져야 한다.

    빠뜨린 종류는 `UNRECOGNIZED` 로 떨어져 **그 종류만 조용히 무검증**이 된다.
    """
    assert set(RELATION_ID_SHAPE) == set(RelationType)


def test_consistent_activations_pass() -> None:
    """정상 발동은 형태별로 모두 통과한다."""
    for act in (_harm(LuckLayer.SEWOON, "甲"), _triple("寅", Pillar4.YEAR)):
        v = relation_operand_consistency(act)
        assert v.valid, v.reason


@pytest.mark.parametrize(
    ("relation_id", "luck_branch", "natal_branch", "shape"),
    [
        # 초판 fixture 가 실제로 만들었던 조합 — 운 글자가 relation_id 와 다르다.
        (_HARM_ID, "午", "亥", "branch_pair"),
        # 원국 글자만 어긋난 경우.
        (_HARM_ID, "申", "子", "branch_pair"),
        # 삼형인데 원국 글자가 피연산자에 없다.
        (_TRIPLE_ID, "申", "亥", "multi_natal"),
        # 형태표에 없는 종류 — fail-closed.
        ("rel_unknown_kind_申_亥", "申", "亥", "UNRECOGNIZED"),
        # 형식 자체를 벗어난 값.
        ("申亥해", "申", "亥", "UNRECOGNIZED"),
    ],
)
def test_inconsistent_operands_are_rejected(
    relation_id: str, luck_branch: str, natal_branch: str, shape: str
) -> None:
    """배선이 어긋나면 identity 가 안정적이어도 위반으로 잡힌다."""
    act = RelationActivation(
        RelationKind.HAE, Pillar4.DAY, LuckLayer.SEWOON, position="branch",
        relation_id=relation_id, luck_stem="甲",
        luck_branch=luck_branch, natal_branch=natal_branch,
    )
    v = relation_operand_consistency(act)
    assert not v.valid
    assert v.relation_shape == shape
    assert v.reason  # 감사에서 원인을 볼 수 있어야 한다


def test_missing_relation_id_is_rejected() -> None:
    """provenance 없는 발동은 통과가 아니라 위반이다."""
    v = relation_operand_consistency(
        RelationActivation(RelationKind.HAE, Pillar4.DAY, LuckLayer.SEWOON)
    )
    assert not v.valid
    assert v.relation_shape == "MISSING"


# ── 계약 불변 ────────────────────────────────────────────────────────────


def test_candidate_schema_defaults_to_empty_instances() -> None:
    """기존 후보는 필드 부재로도 생성돼야 한다(하위호환)."""
    c = EventCandidateV2(event_key="wealth_change", period="2027-02", score=90)
    assert c.reason_instances == []
    assert c.reason_codes == []


def test_reason_codes_contract_is_not_deduplicated() -> None:
    """중복 코드를 제거하면 기존 소비자(guard·리포트)의 입력이 달라진다.

    같은 코드가 두 번 나오는 것은 서로 다른 발동의 정당한 누적이다 — 제거 대상이
    아니라 식별 대상이었다.
    """
    codes = ["REL_HAE_day_pillar", "REL_HAE_day_pillar", "SINGLE_JIECAI"]
    c = EventCandidateV2(
        event_key="wealth_change", period="2027-02", score=90,
        reason_codes=list(codes),
    )
    assert c.reason_codes == codes          # 순서·중복 그대로
    assert len(c.reason_codes) == 3
