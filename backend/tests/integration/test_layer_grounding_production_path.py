"""층위 정보 운반 회귀 — 실제 DTO 경로 (2026-07-27 데굴님 확정: B안).

1차 구현은 `SimpleNamespace` 덕타이핑 스텁으로만 검증해서 `to_legacy_candidate`가
층위를 떨어뜨리는 것을 놓쳤고, 그 뒤 실측에서 더 근본적인 문제가 드러났다 —
`EventCandidateV2.source_layers`는 이름과 달리 **후보별 기여가 아니라 그 시점 평가
스택 전체의 층위**다(브랜처가 후보 루프 밖에서 한 번 계산해 전 후보에 같은 값을 넣는다).

그래서 이 테스트가 고정하는 계약은 "층위가 전달된다"가 아니라 다음이다.

    stack_layers            보존한다 (사실)
    candidate_source_layers 비운다   (아직 수집 안 함)
    layer_grounding         None     (지어내지 않는다)

스텁을 쓰지 않고 EventCandidateV2 → to_legacy_candidate → 실제 EventCandidate →
_to_llm_candidate → LlmEventCandidate 전 구간을 통과시킨다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph
from saju_engines.context_reducer import (
    _to_llm_candidate,
    build_llm_input,
    serialize_llm_input,
)
from saju_engines.event_engine_v2 import to_legacy_candidate
from saju_engines.layer_evidence_scope import classify_layer_evidence_scope
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    LayerEvidenceScope,
    LuckLayer,
)
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


def _v2(layers: list[LuckLayer], reasons: tuple[str, ...] = ()) -> EventCandidateV2:
    """대표 후보 하나 — 스택 층위와 억제 사유만 바꾼다."""
    return EventCandidateV2(
        event_key=EventKeyV2.CAREER_CHANGE,
        period="2026-08",
        score=70,
        source_layers=list(layers),
        reason_codes=list(reasons),
    )


def _llm(v2: EventCandidateV2):
    """실제 어댑터 두 단계를 그대로 통과시킨다(스텁 금지)."""
    legacy = to_legacy_candidate(v2)
    return legacy, _to_llm_candidate(legacy, ganji={}, dw_by_year={})


def test_stack_layers_survive_but_candidate_provenance_stays_empty() -> None:
    """스택 층위는 보존하고, 후보별 기여는 비운다 — 지금 데이터가 말할 수 있는 전부."""
    legacy, llm = _llm(_v2([LuckLayer.ILWOON], ("SUPPRESS_minor_layer_only",)))

    assert legacy.stack_layers == ["ilwoon"]
    assert legacy.candidate_source_layers == []
    assert "SUPPRESS_minor_layer_only" in legacy.evidence_path
    # 후보별 provenance가 없으므로 grounding을 만들지 않는다.
    assert llm.layer_grounding is None


@pytest.mark.parametrize(
    "layers",
    [
        [LuckLayer.ILWOON],
        [LuckLayer.WOLWOON, LuckLayer.ILWOON],
        [LuckLayer.SEWOON, LuckLayer.ILWOON],
        [LuckLayer.DAEWOON, LuckLayer.SEWOON, LuckLayer.WOLWOON, LuckLayer.ILWOON],
        [],
    ],
)
def test_stack_layers_never_produce_grounding(layers: list[LuckLayer]) -> None:
    """스택 구성이 무엇이든 후보 지지로 승격되지 않는다 — 오독 차단의 핵심 불변식."""
    _legacy, llm = _llm(_v2(layers))
    assert llm.layer_grounding is None


def test_layer_order_is_deterministic() -> None:
    """표기 순서는 입력 순서가 아니라 대운→세운→월운→일운으로 고정한다."""
    legacy = to_legacy_candidate(
        _v2([LuckLayer.ILWOON, LuckLayer.DAEWOON, LuckLayer.WOLWOON, LuckLayer.SEWOON])
    )
    assert legacy.stack_layers == ["daewoon", "sewoon", "wolwoon", "ilwoon"]


def test_classifier_rejects_stack_layers_as_unknown() -> None:
    """분류기에 후보 provenance가 없으면 상위 지지로 단정하지 않고 UNKNOWN이다."""
    legacy = to_legacy_candidate(_v2([LuckLayer.DAEWOON, LuckLayer.SEWOON]))
    assert (
        classify_layer_evidence_scope(legacy.candidate_source_layers)
        is LayerEvidenceScope.UNKNOWN
    )


def test_no_upper_support_claim_reaches_real_prompt() -> None:
    """실제 챗 프롬프트에 '상위 지지' 주장이 나가지 않는다 — 스택 100%였던 문장."""
    chart = calculate(
        BirthInput(
            calendar_type="solar",
            birth_date=date(1980, 11, 22),
            birth_time="09:08",
            birth_place_name="서울",
            gender="male",
            reference_date=date(2026, 6, 11),
        )
    )
    scorer = EventEngineV2(_DICTS)
    candidates = scorer.score_legacy(
        chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH}
    )
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.1.0.json")
    bundles = GraphIndex(graph).retrieve(
        [EventKey.CAREER_CHANGE, EventKey.CONTRACT_DOCUMENT]
    )
    intent = IntentJson(
        intent_id="i1",
        query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER,
        time_scope=TimeScope.MID_TERM,
        event_key=EventKey.CAREER_CHANGE,
    )
    payload = build_llm_input(
        "올해 이직운 어때?", intent, chart, candidates, bundles, scorer
    )
    text = serialize_llm_input(payload)

    assert payload.event_candidates, "후보가 비면 이 회귀는 의미가 없다"
    assert all(c.layer_grounding is None for c in payload.event_candidates)
    assert "지지도 있음" not in text
    assert "기간 근거" not in text


def test_transport_does_not_change_score() -> None:
    """단계 0은 운반만 바꾼다 — 점수는 어댑터 전후로 동일해야 한다."""
    v2 = _v2([LuckLayer.ILWOON], ("SUPPRESS_minor_layer_only",))
    legacy, llm = _llm(v2)

    assert legacy.score == v2.score
    assert llm.score == v2.score
