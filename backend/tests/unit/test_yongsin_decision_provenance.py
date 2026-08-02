"""용신 결정 provenance 회귀 (CAL-ROLE-BORDERLINE-01c0, 2026-08-02).

**checkpoint 회귀다.** 재생으로 확인된 것만 고정하고, 아직 실행하지 않은 반사실은 고정하지
않는다. 잘못된 사실을 회귀로 굳히면 뒤 슬라이스가 그 전제 위에서 다시 틀린다 — 01a·01b 가
실제로 그렇게 진행됐다.

확정해 고정하는 것.

    canonical         완비 모델맵이 있으면 **그 모델의 역할표**가 canonical 이다
    _classify_roles   부분맵 모델·특수분기의 **폴백 전용** — canonical 의 기본 출처가 아니다
    confidence        selection score 의 **곱셈 인수**이며 단독 순위 결정자는 아니다
    competing         warning 과 status 승격 guard 외 소비처가 없다

고정하지 않는 것.

    runner-up 水 를 production 실현 경로로 재생했을 때의 최종 역할표. `_classify_roles(水)`
    가 그 답일 **가능성**이 있을 뿐이며, top model·완전성·특수분기를 실제로 재실행한 뒤에야
    기대값이 된다 (CAL-ROLE-BORDERLINE-01c1).

`competing` 판정은 소스 위치·근접성으로 주장하지 않는다. 소비처를 AST 로 열거하고, 서로 다른
competing 구간의 실제 산출물을 비교하는 두 층으로만 뒷받침한다.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.yongsin import candidates as cand_mod
from saju_manse_analysis.yongsin import role_realization as realization_mod
from saju_manse_analysis.yongsin.candidates import _classify_roles

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")

_CASE_A = BirthInput(
    birth_date=date(1987, 8, 5), birth_time="21:00", birth_place_name="서울",
    gender="male", reference_date=date(2026, 7, 27),
)

#: competing 참·거짓이 모두 나오는 코호트. 한쪽만 관측되면 비교 자체가 성립하지 않는다.
_COHORT = (
    (date(1987, 8, 5), "21:00", "male"),
    (date(1990, 3, 12), "07:30", "female"),
    (date(1975, 11, 2), "14:00", "male"),
    (date(2001, 6, 21), "03:10", "female"),
    (date(1968, 1, 9), "19:45", "male"),
    (date(1995, 9, 30), "11:20", "female"),
    (date(1983, 4, 17), "23:40", "male"),
    (date(1979, 12, 25), "05:05", "female"),
)


def _case_a():  # noqa: ANN202 - 엔진 반환 타입은 내부 모델이다
    """사례 A 의 용신 분석 결과."""
    return calculate(_CASE_A).yongsin_analysis


def _source() -> str:
    """`build_yongsin` 의 소스. 계산식 계약 고정에만 쓴다."""
    return inspect.getsource(cand_mod.build_yongsin)


@lru_cache(maxsize=1)
def _build_yongsin_ast() -> ast.Module:
    """`build_yongsin` 의 AST. 소비처 추적의 근거다."""
    return ast.parse(textwrap.dedent(_source()))


def _model_of(analysis, model_type: str):  # noqa: ANN001, ANN202
    """후보 모델 하나를 model_type 으로 찾는다."""
    return next(c for c in analysis.candidate_models if c.model_type == model_type)


# ── canonical 실현 출처 ──────────────────────────────────────────────────


def test_canonical_comes_from_the_complete_model_map_not_classify_roles() -> None:
    """완비 모델이 있으면 **그 모델의 역할표를 그대로 채택**한다.

    `_classify_roles` 는 부분맵 모델·특수분기의 폴백 전용이다. 이 구분을 놓치면 "canonical 은
    용신 오행에서 기계적으로 배정된다" 는 잘못된 전제가 다시 들어온다.
    """
    y = _case_a()
    eokbu = _model_of(y, "eokbu_normal")
    assert y.canonical_roles == {k: getattr(eokbu, k) for k in _ROLE_KEYS}
    # 정적 생극 폴백과는 다르다 — 희신·구신·한신 셋이 갈린다.
    assert y.canonical_roles != _classify_roles(y.final["yongsin"])


#: 실현 규칙(승격 조건·특수분기 우선·부분맵 폴백)은 **소스 문자열이 아니라 행동**으로
#: `test_role_realization_boundary` 가 고정한다. 01c1-a 에서 경계를 뽑기 전에는 경로가
#: 함수 안에 잠겨 있어 소스 pinning 밖에 방법이 없었다.


def test_promotion_expression_lives_in_the_extracted_boundary() -> None:
    """승격 판정이 `build_yongsin` 이 아니라 실현 경계에 있다."""
    boundary = inspect.getsource(realization_mod.resolve_realized_roles)
    assert "model_map_promoted = special_kind is None and model_complete" in boundary
    assert "roles = {k: getattr(selected_model, k) for k in _ROLE_KEYS}" in boundary
    # 호출부에는 판정식이 남아 있지 않다 — 경계 결과를 받아 쓰기만 한다.
    src = _source()
    assert "model_map_promoted = not special_roles and model_complete" not in src
    assert "model_map_promoted = realized.model_map_promoted" in src


def test_incomplete_model_cannot_be_promoted() -> None:
    """부분맵(johu·pattern_sangsin)은 5역할 완비가 아니라 승격 대상이 아니다."""
    partial = [c for c in _case_a().candidate_models if c.is_auxiliary]
    assert partial
    assert any(
        any(getattr(c, k) is None for k in _ROLE_KEYS) for c in partial
    )


def test_partial_auxiliary_models_are_not_full_role_maps() -> None:
    """johu·pattern_sangsin 은 부분 역할표다 — canonical alternate 로 쓸 수 없다."""
    auxiliary = [c for c in _case_a().candidate_models if c.is_auxiliary]
    assert auxiliary
    assert any(c.gisin is None or c.hansin is None for c in auxiliary)


# ── selection score — confidence 는 인수이지 순위가 아니다 ────────────────


def test_useful_score_formula_multiplies_confidence() -> None:
    """`useful` 점수 계산식이 confidence × 축 가중치임을 고정한다.

    "confidence 는 선택에 쓰이지 않는다" 는 이전 주장은 **틀렸다**. 점수의 곱셈 인수다.
    """
    src = _source()
    assert '_put(useful, m.yongsin, m.confidence * w, m.model_type, "yongsin")' in src
    assert '_put(useful, m.heesin, m.confidence * w * 0.85, m.model_type, "heesin")' in src


def test_confidence_is_a_weighted_selection_input() -> None:
    """사례 A 점수를 인수 단위로 분해한다.

        土  0.6033 × 0.25 = 0.150825 → 0.1508
        水  0.7000 × 0.20 = 0.140000 → 0.1400

    표시값이 아니라 반올림 전 원시 정밀도로 비교한 뒤, production 이 보고한 4자리 값과
    맞춘다. 계산식이나 축 가중치가 바뀌면 여기서 깨진다.
    """
    y = _case_a()
    earth_raw = Decimal("0.6033") * Decimal("0.25")
    water_raw = Decimal("0.7000") * Decimal("0.20")
    assert earth_raw == Decimal("0.150825")
    assert water_raw == Decimal("0.140000")

    quantum = Decimal("0.0001")
    useful = y.useful_candidates
    assert Decimal(str(useful[0].score)) == earth_raw.quantize(quantum)
    assert Decimal(str(useful[1].score)) == water_raw.quantize(quantum)
    # 분해에 쓴 confidence 가 실제 모델 값이다.
    assert Decimal(str(_model_of(y, "eokbu_normal").confidence)) == Decimal("0.6033")
    assert Decimal(str(_model_of(y, "pattern_sangsin").confidence)) == Decimal("0.7")


def test_confidence_alone_does_not_rank_the_decision() -> None:
    """confidence 가 낮은 쪽이 이겼다 — 순서를 뒤집은 것은 축 가중치다.

    `CONFIDENCE_IS_WEIGHTED_SELECTION_INPUT` 이며
    `CONFIDENCE_IS_NOT_STANDALONE_RANKING_SCORE` 다.
    """
    y = _case_a()
    primary_conf = Decimal(str(_model_of(y, "eokbu_normal").confidence))
    runner_conf = Decimal(str(_model_of(y, "pattern_sangsin").confidence))
    assert primary_conf < runner_conf
    assert Decimal(str(y.useful_candidates[0].score)) > Decimal(str(y.useful_candidates[1].score))
    # confidence 최고 모델이 선택 모델이 아니다.
    by_conf = sorted(y.candidate_models, key=lambda c: c.confidence or 0.0, reverse=True)
    assert by_conf[0].model_type != y.final["selected_model"]


def test_case_a_primary_and_runner_up_elements() -> None:
    """실제 결정 후보는 오행 단위이며 2개로 잘린다."""
    useful = _case_a().useful_candidates
    assert len(useful) == 2
    assert useful[0].element == "土" and useful[1].element == "水"


def test_case_a_scores_are_on_one_comparable_scale() -> None:
    """0.1508·0.1400 은 같은 `useful` 테이블 값이고 정렬 키의 2차 항목이다."""
    useful = _case_a().useful_candidates
    assert (useful[0].score, useful[1].score) == (0.1508, 0.14)
    assert round(useful[0].score - useful[1].score, 4) == 0.0108


def test_selection_uses_the_same_scores_it_reports() -> None:
    """정렬 키가 (role=='yongsin', score) 임을 계산식으로 고정한다."""
    assert 'key=lambda kv: (kv[1][2] == "yongsin", kv[1][0])' in _source()


def test_alternate_is_capped_at_one_by_the_selector() -> None:
    """`useful_sorted[:2]` 라 후보는 구조적으로 최대 2개 — v1 alternate 는 0~1개."""
    src = _source()
    assert "useful_sorted = sorted(" in src
    assert "[:2]" in src.split("useful_sorted = sorted(")[1][:200]


def test_selected_model_is_a_reporting_label() -> None:
    """보조 모델도 후보로 올라온다 — `selected_model` 은 역할표 채택 근거가 아니다."""
    y = _case_a()
    assert y.final["selected_model"] == "eokbu_normal"
    assert y.useful_candidates[1].model == "pattern_sangsin"
    assert y.final["confidence"] == 0.6033


# ── competing 은 진단 전용 — 소비처와 산출물로만 판정한다 ─────────────────


def _competing_consumer_ifs() -> list[ast.If]:
    """`competing` 을 읽는 지점의 최근접 문(statement)을 중복 없이 모은다."""
    tree = _build_yongsin_ast()
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    stmts: list[ast.stmt] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Name) and node.id == "competing"):
            continue
        if isinstance(node.ctx, ast.Store):
            continue
        cursor: ast.AST | None = node
        while cursor is not None and not isinstance(cursor, ast.stmt):
            cursor = parent.get(cursor)
        assert isinstance(cursor, ast.If), "competing 은 조건문 밖에서 소비되지 않아야 한다"
        if not any(cursor is seen for seen in stmts):
            stmts.append(cursor)
    return [s for s in stmts if isinstance(s, ast.If)]


def test_competing_has_exactly_one_definition() -> None:
    """정의가 하나여야 소비처 열거가 완전하다."""
    stores = [
        n for n in ast.walk(_build_yongsin_ast())
        if isinstance(n, ast.Name) and n.id == "competing" and isinstance(n.ctx, ast.Store)
    ]
    assert len(stores) == 1


def test_competing_consumers_are_only_warning_and_status_guard() -> None:
    """소비처를 AST 로 열거한다 — 소스 위치나 근접성으로 주장하지 않는다.

    허용 소비처는 `warnings.append` 와 `status` 승격 guard 둘뿐이다.
    """
    ifs = _competing_consumer_ifs()
    assert len(ifs) == 2

    targets: set[str] = set()
    calls: set[str] = set()
    for branch in ifs:
        for stmt in list(branch.body) + list(branch.orelse):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    targets.add(node.id)
                elif isinstance(node, ast.Call):
                    calls.add(ast.unparse(node.func))
    assert targets == {"status"}
    assert calls == {"warnings.append"}


def test_competing_guarded_blocks_never_touch_selection_outputs() -> None:
    """선택 산출물 이름이 competing 구간 안에서 재대입되지 않는다."""
    forbidden = {
        "useful", "useful_sorted", "useful_candidates", "yongsin_el",
        "roles", "selected_model", "top_model", "canonical_roles",
    }
    for branch in _competing_consumer_ifs():
        for stmt in list(branch.body) + list(branch.orelse):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    assert node.id not in forbidden


def test_canonical_origin_does_not_depend_on_competing() -> None:
    """competing 참·거짓 양쪽에서 실현 규칙이 동일하게 적용된다.

    소비처 구조 검사보다 강한 증거다 — 실제 산출물이 competing 과 무관하게 **완비 모델맵
    승격** 또는 **특수분기** 로만 결정된다.
    """
    seen: dict[bool, set[str]] = {True: set(), False: set()}
    for birth_date, birth_time, gender in _COHORT:
        y = calculate(BirthInput(
            birth_date=birth_date, birth_time=birth_time, birth_place_name="서울",
            gender=gender, reference_date=date(2026, 7, 27),
        )).yongsin_analysis
        useful = y.useful_candidates
        competing = len(useful) >= 2 and (useful[0].score - useful[1].score) < 0.12

        selected = next(
            (c for c in y.candidate_models
             if c.model_type == y.final["selected_model"]
             and c.yongsin == y.final["yongsin"]),
            None,
        )
        complete = selected is not None and all(getattr(selected, k) for k in _ROLE_KEYS)
        if complete and y.canonical_roles == {k: getattr(selected, k) for k in _ROLE_KEYS}:
            origin = "MODEL_MAP"
        elif y.canonical_roles == _classify_roles(y.final["yongsin"]):
            origin = "CLASSIFY_FALLBACK"
        else:
            origin = "SPECIAL_BRANCH"
        seen[competing].add(origin)

    assert seen[True] and seen[False], "competing 한쪽만 관측되면 비교가 성립하지 않는다"
    assert seen[True] <= {"MODEL_MAP", "SPECIAL_BRANCH"}
    assert seen[False] <= {"MODEL_MAP", "SPECIAL_BRANCH"}


def test_competing_does_not_gate_status_in_the_observed_cohort() -> None:
    """관측 코호트는 전건 `candidate` 다 — status 차이는 **행동으로 증명되지 않았다**.

    `probable` 승격은 `len(models) == 1` 을 함께 요구해 이 코호트에서 도달하지 않는다.
    허용 소비처라는 사실은 AST 검사로만 고정하고, 행동 근거가 있는 것처럼 적지 않는다.
    """
    statuses = {
        calculate(BirthInput(
            birth_date=birth_date, birth_time=birth_time, birth_place_name="서울",
            gender=gender, reference_date=date(2026, 7, 27),
        )).yongsin_analysis.status
        for birth_date, birth_time, gender in _COHORT
    }
    assert statuses == {"candidate"}


# ── 정적 폴백 사실 — runner-up canonical 이 아니다 ────────────────────────


def test_classify_roles_for_water_returns_static_fallback_map() -> None:
    """`_classify_roles(水)` 의 정적 생극 배정만 확인한다.

    **이것은 runner-up 용신 결정의 최종 반사실 역할표가 아니다.** 水 경로의 top model·모델
    완전성·특수분기를 production 실현 경로로 재실행해야 그 답을 알 수 있다. 외부 출처
    역할표와 값이 같더라도 alternate provenance 로 승격시키지 않는다.
    """
    assert _classify_roles("水") == {
        "yongsin": "水", "heesin": "金", "gisin": "土", "gusin": "火", "hansin": "木",
    }


# ── eeaed83 비배선 ───────────────────────────────────────────────────────


def _production_sources() -> list[Path]:
    """production 트리의 파이썬 소스. tests·scripts 는 제외한다."""
    backend = Path(__file__).resolve().parents[2]
    module = backend / "packages/saju_engines/saju_engines/role_candidates.py"
    files: list[Path] = []
    for root in (backend / "apps", backend / "packages"):
        files.extend(
            p for p in root.rglob("*.py")
            if p != module and "tests" not in p.parts and "scripts" not in p.parts
        )
    return files


def _referenced_names(path: Path) -> tuple[set[str], set[str]]:
    """(import 된 모듈 경로, 코드에서 참조된 식별자).

    **텍스트 검색이 아니라 AST 다.** 처음엔 문자열 스캔이었는데, 다른 모듈이 docstring
    에서 "이 타입을 쓰지 않는다" 고 설명한 것까지 위반으로 잡았다(2026-08-03 실측).
    주석·docstring 의 언급은 배선이 아니다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return modules, names


def test_role_candidates_has_no_production_import() -> None:
    """`eeaed83` 계약은 SUPERSEDED — production import 가 0이어야 한다."""
    sources = _production_sources()
    assert len(sources) > 100, "production 소스 스캔 범위가 비었다"
    offenders = [
        str(p) for p in sources
        if any("role_candidates" in m for m in _referenced_names(p)[0])
    ]
    assert offenders == []


def test_role_candidate_set_is_not_constructed_in_production() -> None:
    """타입 노출·직렬화·LLM 입력 어디에도 들어가지 않는다."""
    banned = {"RoleCandidateSet", "RoleModelCandidate", "build_role_candidate_set"}
    offenders = [
        str(p) for p in _production_sources() if _referenced_names(p)[1] & banned
    ]
    assert offenders == []
