"""REL provenance — 엔진 실산출 피연산자 정합 + 외부 경계 미노출 (2026-07-31).

fixture 몇 건으로는 부족하다. 초판 fixture 자체가 `luck_branch=午` 에
`relation_id=rel_harm_申_亥` 를 물려 **성립하지도 않는 해(午亥)** 를 만들었고,
source identity 는 결정론적이라 그걸 아무도 잡지 못했다. 그래서 손으로 만든 조합이
아니라 **엔진이 실제로 낸 전 발동**에 정합 검사를 건다.

고정 방식을 두 층으로 나눈다.

    강한 불변식   위반 0 · identity 충돌 0 · UNRECOGNIZED 0 · 형태 전수 커버
    관측 스냅샷   형태별·명식별 건수 — 탐지기가 늘면 정당하게 변한다

건수를 hard assertion 으로 박으면 관계 탐지기를 확장할 때마다 무의미한 회귀 수정이
생긴다. 반면 위반·충돌 0 은 어떤 확장에서도 지켜져야 한다.

두 번째 축은 `reason_instances` 가 **외부 전달 경계**에 새지 않는다는 것이다. 내부
candidate 직렬화에서 무조건 지울 필요는 없다 — 감사·디버깅 경로에는 남아야 한다.
"""

from __future__ import annotations

import collections
from datetime import date
from typing import Any

import pytest

from saju_api.services import report_service as R
from saju_engines import event_engine_v2 as E
from saju_engines.relation_palace_engine import (
    RelationActivation,
    relation_operand_consistency,
    relation_source_identity,
)
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import RelationIdShape
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

#: 명식 4건 — 한 명식은 관계 종류를 다 만들지 못한다(1980 생은 삼형이 0건이었다).
CHARTS: tuple[tuple[str, date, str, str], ...] = (
    ("1980", date(1980, 11, 22), "09:08", "male"),
    ("1992", date(1992, 5, 14), "23:40", "female"),
    ("1975", date(1975, 2, 3), "14:20", "male"),
    ("2001", date(2001, 8, 29), "06:05", "female"),
)

#: 이 회귀가 실제로 검사해야 하는 형태. 하나라도 0 건이면 그 분기가 무검증이다.
EXPECTED_SHAPES = frozenset({
    RelationIdShape.STEM_PAIR.value,
    RelationIdShape.BRANCH_PAIR.value,
    RelationIdShape.MULTI_NATAL.value,
    RelationIdShape.ELEMENT.value,
    RelationIdShape.SINGLE.value,
    "SYNTHETIC",
})

#: 관측 스냅샷(2026-07-31, 명식 4건). 하한 확인용이며 정확 일치를 요구하지 않는다.
OBSERVED_TOTAL = 2811


class _Run:
    """명식 4건 스코어링 1회분 — 발동 수집과 리포트 데이터를 함께 보관한다."""

    def __init__(self) -> None:
        self.activations: list[RelationActivation] = []
        self.by_chart: dict[str, int] = {}
        self.data: dict[str, Any] = {}


@pytest.fixture(scope="module")
def run() -> _Run:
    """`_activations` 를 감싸 실산출 발동을 모은다(반환값은 그대로 통과시킨다)."""
    out = _Run()
    orig_act, orig_bok = E._activations, E._bokeum_activations

    def spy_act(hits: Any, layer: Any, result: Any) -> Any:
        acts = orig_act(hits, layer, result)
        out.activations.extend(acts)
        return acts

    def spy_bok(result: Any, target: Any, layer: Any) -> Any:
        acts = orig_bok(result, target, layer)
        out.activations.extend(acts)
        return acts

    E._activations, E._bokeum_activations = spy_act, spy_bok
    try:
        for label, birth_date, birth_time, gender in CHARTS:
            before = len(out.activations)
            birth = R.BirthInput(
                calendar_type="solar", birth_date=birth_date, birth_time=birth_time,
                birth_place_name="서울", gender=gender,
            )
            spec = ReportSpec(
                product_code="RPT_FOCUS",
                subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
                topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
            )
            data = R._ReportData(birth, spec, date(2026, 7, 30))
            out.data[label] = (data, data.scorer.score(data.result))
            out.by_chart[label] = len(out.activations) - before
    finally:
        E._activations, E._bokeum_activations = orig_act, orig_bok
    return out


# ── ③ 엔진 실산출 정합 ───────────────────────────────────────────────────


def test_every_activation_has_consistent_operands(run: _Run) -> None:
    """강한 불변식 — 위반 0. relation_id 와 기록된 글자가 어긋나면 안 된다."""
    bad = [
        (a, v) for a in run.activations
        if not (v := relation_operand_consistency(a)).valid
    ]
    assert not bad, "\n".join(
        f"{a.relation_id} luck={a.luck_stem}{a.luck_branch} "
        f"natal={a.natal_stem}{a.natal_branch} → {v.reason}"
        for a, v in bad[:10]
    )


def test_no_unrecognized_relation_id(run: _Run) -> None:
    """강한 불변식 — 형태표 누락 0.

    `UNRECOGNIZED` 가 나오면 관계 종류가 늘었는데 `RELATION_ID_SHAPE` 를 갱신하지
    않은 것이다. 그 종류만 조용히 무검증이 되므로 통과시키면 안 된다.
    """
    unknown = sorted({
        a.relation_id for a in run.activations
        if relation_operand_consistency(a).relation_shape == "UNRECOGNIZED"
    })
    assert not unknown, f"형태표에 없는 relation_id: {unknown}"


def test_source_identity_has_no_collision(run: _Run) -> None:
    """강한 불변식 — 충돌 0. 서로 다른 발동이 같은 identity 를 받으면 식별 실패다."""
    by_identity: dict[str, set[tuple[str, ...]]] = collections.defaultdict(set)
    for a in run.activations:
        by_identity[relation_source_identity(a)].add((
            a.kind.value, a.palace.value, a.layer.value, a.position,
            a.luck_stem, a.luck_branch, a.natal_stem, a.natal_branch, a.relation_id,
        ))
    collisions = {k: v for k, v in by_identity.items() if len(v) > 1}
    assert not collisions, f"identity 충돌 {len(collisions)}건: {list(collisions)[:3]}"


def test_all_shapes_are_exercised(run: _Run) -> None:
    """강한 불변식 — 형태 전수 커버. 0 건인 형태는 검증되지 않은 분기다."""
    seen = {
        relation_operand_consistency(a).relation_shape for a in run.activations
    }
    assert EXPECTED_SHAPES <= seen, f"미검증 형태: {sorted(EXPECTED_SHAPES - seen)}"


def test_activation_volume_snapshot(run: _Run) -> None:
    """관측 스냅샷 — 정확 일치가 아니라 하한만 본다.

    탐지기가 늘면 건수는 정당하게 증가한다. 반면 급감은 수집 자체가 끊겼다는
    신호이므로(스파이 미설치·조기 반환) 하한은 지킬 값어치가 있다.
    """
    total = len(run.activations)
    assert total >= OBSERVED_TOTAL * 0.5, (
        f"발동 수집이 급감했다: {total} (스냅샷 {OBSERVED_TOTAL})"
    )
    assert all(n > 0 for n in run.by_chart.values()), run.by_chart


# ── ④ 외부 전달 경계 미노출 ──────────────────────────────────────────────


def test_v2_candidates_actually_carry_instances(run: _Run) -> None:
    """미노출 검사가 공허하지 않음을 먼저 보인다.

    상류에 provenance 가 애초에 없으면 아래 검사들은 전부 무의미하게 통과한다.
    """
    _data, v2 = run.data["1980"]
    assert any(c.reason_instances for c in v2), "V2 후보에 provenance 가 없다"


def test_legacy_dto_has_no_provenance_field(run: _Run) -> None:
    """다운스트림 DTO 는 필드 자체를 갖지 않는다 — 구조적 차단."""
    assert "reason_instances" not in EventCandidate.model_fields


def test_conversion_drops_provenance(run: _Run) -> None:
    """V2 → 레거시 변환 결과 직렬화에 provenance 흔적이 남지 않는다."""
    _data, v2 = run.data["1980"]
    carrying = [c for c in v2 if c.reason_instances]
    assert carrying
    for c in carrying[:50]:
        dumped = E.to_legacy_candidate(c).model_dump_json()
        assert "source_identity" not in dumped
        assert "reason_instances" not in dumped


#: 인자가 필요한 블록의 호출 인자. 무인자 블록만 훑으면 리포트 evidence 경계의
#: 절반(이사·택일·주제 모듈)이 조용히 검사에서 빠진다.
_BLOCK_ARGS: dict[str, tuple[Any, ...]] = {
    "era_energy_block": (2027,),
    "selection_block": ("career",),
}
_SPEC_BLOCKS = frozenset({
    "relocation_direction_block", "relocation_flow_block", "relocation_reason_block",
    "relocation_risk_block", "relocation_year_block",
})
#: M01~M15 전 모듈 — 주제 모듈이 근거를 어떻게 직렬화하든 경계에 포함된다.
_TOPIC_MODULES = tuple(f"M{i:02d}" for i in range(1, 16))

#: provenance 가 새면 나타날 토큰.
_LEAK_TOKENS = ("source_identity", "reason_instances", "REL|")


def _block_texts(data: Any, spec: ReportSpec) -> dict[str, str]:
    """`_ReportData` 의 모든 `*_block` 산출 텍스트. 인자 필요 블록도 채워 호출한다."""
    texts: dict[str, str] = {}

    def render(name: str, *args: Any) -> None:
        try:
            lines = getattr(data, name)(*args)
        except (TypeError, KeyError, ValueError):
            return  # 이 명식·주제에 해당 없음 — 누출 검사 대상이 아니다
        texts[f"{name}{args if args else ''}"] = "\n".join(
            str(x) for x in lines or ()
        )

    for name in sorted(dir(data)):
        if not name.endswith("_block") or name.startswith("__"):
            continue
        if not callable(getattr(data, name, None)):
            continue
        if name == "topic_module_block":
            for module_id in _TOPIC_MODULES:
                render(name, module_id, spec)
        elif name in _SPEC_BLOCKS:
            render(name, spec)
        else:
            render(name, *_BLOCK_ARGS.get(name, ()))
    return texts


@pytest.mark.parametrize("label", [c[0] for c in CHARTS])
def test_prompt_data_blocks_leak_no_provenance(run: _Run, label: str) -> None:
    """LLM 입력·리포트 근거 블록에 provenance 가 새지 않는다.

    개별 블록을 열거하면 새 블록이 추가될 때 검사에서 빠지므로 `*_block` 을 전수
    순회한다. 부정 검사는 공허하게 통과하기 쉬워, **텍스트를 실제로 읽었다는 양성
    대조**를 같은 검사 안에 둔다 — 블록이 전부 빈 문자열이면 누출 검사도 무의미하다.
    """
    data, _v2 = run.data[label]
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    texts = _block_texts(data, spec)

    # 양성 대조 — 실제 근거 텍스트를 읽고 있는가.
    total = sum(len(t) for t in texts.values())
    assert total > 5_000, f"블록 텍스트가 비었다({total}자) — 누출 검사가 공허하다"
    assert "[대운표]" in texts.get("luck_block", ""), "운 블록이 렌더링되지 않았다"

    leaked = sorted(
        name for name, text in texts.items()
        if any(tok in text for tok in _LEAK_TOKENS)
    )
    assert not leaked, f"provenance 누출 블록: {leaked}"


def test_luck_block_consumes_legacy_candidates_only(run: _Run) -> None:
    """운 블록은 레거시 후보만 받는다 — V2 provenance 가 닿을 수 없는 경로다."""
    data, _v2 = run.data["1980"]
    assert all(isinstance(c, EventCandidate) for c in data.candidates)
    text = "\n".join(data.luck_block())
    assert "REL|" not in text
