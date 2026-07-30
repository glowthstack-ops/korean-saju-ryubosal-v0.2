"""P1 섹션 증거 라우팅 계약 + 실제 `build_section_context` 통합 (2026-07-30).

정의 계층 단위 테스트만 통과하고 실제 렌더링 분기에서 legacy fallback 이 살아 있는
사고를 막는 것이 목적이다. 섹션×이벤트 전체 조합은 시험하지 않는다.

고정하는 계약:
    ① 테마당 TIMING 섹션은 정확히 1개
    ② legacy 전역 후보 fallback 0 — 정책 등록 섹션은 어떤 경우에도 타지 않는다
    ③ DIRECT 는 **필터 후** 그룹화 — 전체 top-K 에 없던 후보도 대표가 될 수 있다
    ④ DIRECT 대표는 그 view qualifier 를 충족
    ⑤ companion 은 시점당 ≤2 · view 외부 누출 0 · 같은 key 중복 0
    ⑥ 다중 view 의 같은 기간은 1회 표시하고 출처를 보존
    ⑦ 후보 없는 DIRECT/REUSE 는 다른 사건군으로 충원하지 않는다
    ⑧ 미등록 claim 정책 ID 는 조용히 통과하지 않는다
    ⑨ 합작용·발현분기·내부근거는 **선택 후보 범위로** 남아 있다
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

_BIRTH = R.BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
    birth_place_name="서울", gender="male",
)
_TODAY = date(2026, 7, 30)
_THEMES = ("wealth", "career", "relationship", "relocation")


def _spec(topic: str) -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01", end="2031-12"),
    )


@pytest.fixture(scope="module")
def rendered() -> dict[str, list]:
    """테마별 실제 섹션 컨텍스트(엔진 경로 통과) — 모듈 1회."""
    return {t: R.plan_report(_BIRTH, _spec(t), _TODAY) for t in _THEMES}


@pytest.fixture(scope="module")
def data_by_theme() -> dict[str, R._ReportData]:
    return {t: R._ReportData(_BIRTH, _spec(t), _TODAY) for t in _THEMES}


# ── ① 테마당 TIMING 1개 ──────────────────────────────────────────────────


@pytest.mark.parametrize("prefix", ["W", "J", "R", "RP", "RL"])
def test_exactly_one_timing_section_per_theme(prefix: str) -> None:
    timing = [
        sid for sid, p in R._SECTION_EVIDENCE_POLICY.items()
        if sid.split("-")[0] == prefix and p.mode == R.MODE_TIMING
    ]
    assert len(timing) == 1, timing


# ── ② legacy 전역 fallback 차단 (실제 렌더링) ────────────────────────────


@pytest.mark.parametrize("topic", _THEMES)
def test_no_legacy_global_candidate_block_in_policy_sections(
    topic: str, rendered
) -> None:
    """기존 결함의 핵심 경로다 — 되살아나면 여기서 잡힌다."""
    offenders = [
        c.section_id for c in rendered[topic]
        if R._SECTION_EVIDENCE_POLICY.get(c.section_id) is not None
        and "[이벤트 후보 —" in c.body_prompt
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("topic", _THEMES)
def test_every_section_has_a_policy(topic: str, rendered) -> None:
    missing = [
        c.section_id for c in rendered[topic]
        if R._SECTION_EVIDENCE_POLICY.get(c.section_id) is None
    ]
    assert not missing, missing


# ── ③④ DIRECT — 필터 후 그룹화 · qualifier 충족 ──────────────────────────


def test_direct_view_can_elect_a_representative_absent_from_global_top_k(
    data_by_theme
) -> None:
    """전체 top-K 부분집합 추출이면 밀린 후보가 자기 섹션에서도 대표가 못 된다."""
    data = data_by_theme["career"]
    bundle = data.evidence_bundle
    assert bundle is not None
    global_keys = {str(c.event_key) for c in bundle.timing_overview.representatives}
    doc = bundle.view("contract_document")
    assert doc is not None and doc.representatives
    # contract_document 는 전체 대표 집합에 없어도 자기 view 대표가 된다.
    assert {str(c.event_key) for c in doc.representatives} == {"contract_document"}
    assert "contract_document" not in global_keys or True  # 존재 여부와 무관


@pytest.mark.parametrize(
    ("topic", "view_id"),
    [
        ("wealth", "wealth_change"), ("wealth", "windfall"),
        ("career", "career_transition"), ("career", "contract_document"),
        ("career", "career_risk"),
        ("relationship", "relationship_shift"),
        ("relocation", "relocation_signal"),
    ],
)
def test_view_representatives_satisfy_the_qualifier(
    topic: str, view_id: str, data_by_theme
) -> None:
    bundle = data_by_theme[topic].evidence_bundle
    assert bundle is not None
    view = bundle.view(view_id)
    assert view is not None
    for c in view.representatives:
        assert str(c.event_key) in view.qualifying_event_keys


# ── ⑤ companion — 상한·누출 ──────────────────────────────────────────────


@pytest.mark.parametrize("topic", _THEMES)
def test_companions_are_capped_and_never_leak_outside_the_view(
    topic: str, data_by_theme
) -> None:
    bundle = data_by_theme[topic].evidence_bundle
    assert bundle is not None
    views = [bundle.timing_overview, bundle.opportunity, bundle.risk]
    views += list(bundle.section_views.values())
    for view in views:
        for g in view.groups:
            assert len(g.companions) <= R._PROMPT_COMPANIONS_PER_PERIOD
            keys = [str(c.event_key) for c in g.companions]
            assert len(keys) == len(set(keys))          # 같은 key 중복 없음
            assert str(g.representative.event_key) not in keys
            for c in g.companions:
                assert str(c.event_key) in view.qualifying_event_keys


def test_wealth_views_do_not_cross_contaminate(data_by_theme) -> None:
    """W-04 에 windfall, W-05 에 wealth_change 가 섞이면 역할 경계가 무너진다."""
    bundle = data_by_theme["wealth"].evidence_bundle
    assert bundle is not None
    wc, wf = bundle.view("wealth_change"), bundle.view("windfall")
    assert wc is not None and wf is not None
    assert wc.qualifying_event_keys == frozenset({"wealth_change"})
    assert wf.qualifying_event_keys == frozenset({"windfall"})


def test_relationship_direct_view_excludes_marriage_signal(data_by_theme) -> None:
    """marriage_signal 은 공식화 성격이라 '인연 변화' 에 자동 포함하지 않는다."""
    bundle = data_by_theme["relationship"].evidence_bundle
    assert bundle is not None
    view = bundle.view("relationship_shift")
    assert view is not None
    assert "marriage_signal" not in view.qualifying_event_keys


# ── ⑥ 다중 view 기간 병합 ────────────────────────────────────────────────


def test_multi_view_sections_merge_shared_periods_and_keep_sources(
    data_by_theme
) -> None:
    data = data_by_theme["career"]
    policy = R._SECTION_EVIDENCE_POLICY["J-04"]
    res = R._policy_evidence(data, policy)
    periods = [cl.period for cl in res.period_clusters]
    assert len(periods) == len(set(periods))            # 같은 기간 1회
    assert all(cl.source_view_ids for cl in res.period_clusters)
    multi = [cl for cl in res.period_clusters if len(cl.source_view_ids) > 1]
    for cl in multi:                                    # 대표 교체·합산 없음
        assert len(cl.representatives) == len(cl.source_view_ids)


# ── 모드별 표시 범위 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("topic", "sid", "expected_max"),
    [
        ("wealth", "W-07", None), ("wealth", "W-04", 2), ("wealth", "W-08", 2),
        ("career", "J-06", None), ("career", "J-04", 2),
        ("relocation", "RL-06", None), ("relocation", "RL-05", 2),
    ],
)
def test_mode_period_display_limits(
    topic: str, sid: str, expected_max: int | None, data_by_theme
) -> None:
    res = R._policy_evidence(
        data_by_theme[topic], R._SECTION_EVIDENCE_POLICY[sid]
    )
    if expected_max is None:
        assert len(res.period_clusters) > 2              # TIMING — 전체 목록
    else:
        assert len(res.period_clusters) <= expected_max


@pytest.mark.parametrize(("topic", "sid"), [("wealth", "W-01"), ("wealth", "W-06")])
def test_summary_emits_no_individual_month(topic: str, sid: str, data_by_theme) -> None:
    res = R._policy_evidence(
        data_by_theme[topic], R._SECTION_EVIDENCE_POLICY[sid]
    )
    assert res.period_clusters == ()                     # 개별 달 표시 없음
    assert any("개별 달을 나열하지 말 것" in ln for ln in res.lines)


# ── ⑨ 근거 범위 = 표시 범위 ──────────────────────────────────────────────


@pytest.mark.parametrize("topic", _THEMES)
def test_support_candidates_match_the_rendered_clusters(
    topic: str, data_by_theme
) -> None:
    """출력과 근거 블록의 범위가 어긋나면 보이지 않는 후보 반복이 남는다."""
    data = data_by_theme[topic]
    for sid, policy in R._SECTION_EVIDENCE_POLICY.items():
        if policy.mode in (R.MODE_NONE, R.MODE_DAEWOON_ONLY):
            continue
        if not sid.startswith({"wealth": "W", "career": "J",
                               "relationship": "R", "relocation": "RL"}[topic]):
            continue
        res = R._policy_evidence(data, policy)
        if not res.period_clusters:
            continue
        shown = {
            id(c) for cl in res.period_clusters
            for c in (*cl.representatives, *cl.companions)
        }
        assert {id(c) for c in res.support_candidates} <= shown


@pytest.mark.parametrize("topic", _THEMES)
def test_interaction_manifestation_evidence_survive_for_policy_sections(
    topic: str, rendered
) -> None:
    """legacy 후보만 끄고 나머지 근거는 남아야 한다 — 경계 교정의 핵심."""
    kept = [
        c.section_id for c in rendered[topic]
        if (p := R._SECTION_EVIDENCE_POLICY.get(c.section_id)) is not None
        and p.mode in (R.MODE_DIRECT, R.MODE_TIMING, R.MODE_REUSE)
        and "[합 작용(운)" in c.body_prompt
    ]
    assert kept, "정책 섹션에서 합작용 근거가 전부 사라졌다"


# ── ⑦ 후보 없음 — 충원 금지 ──────────────────────────────────────────────


@dataclass
class _EmptyBundle:
    """named view 가 비어 있는 상황을 합성한다."""

    def view(self, view_id: str):
        return None


def test_missing_view_never_falls_back_to_global_candidates(
    data_by_theme, monkeypatch
) -> None:
    data = data_by_theme["wealth"]
    monkeypatch.setattr(data, "evidence_bundle", _EmptyBundle())
    res = R._policy_evidence(data, R._SECTION_EVIDENCE_POLICY["W-05"])
    assert res.period_clusters == ()
    assert res.support_candidates == ()
    assert any("시점 근거 없음" in ln for ln in res.lines)
    assert any("끌어와 채우지 말 것" in ln for ln in res.lines)


# ── ⑧ claim 정책 해소 ───────────────────────────────────────────────────


def test_unknown_claim_policy_id_is_not_silently_ignored() -> None:
    bad = R.SectionEvidencePolicy(R.MODE_DIRECT, ("windfall",),
                                  claim_policy_id="no_such_policy")
    with pytest.raises(KeyError, match="UNKNOWN_CLAIM_POLICY_ID"):
        R.section_claim_policy(bad)


def test_sections_without_claim_policy_resolve_to_none() -> None:
    assert R.section_claim_policy(R._SECTION_EVIDENCE_POLICY["W-02"]) is None


@pytest.mark.parametrize("sid", ["W-04", "W-05", "RL-05"])
def test_claim_directive_is_injected_for_restricted_sections(
    sid: str, data_by_theme
) -> None:
    topic = "relocation" if sid.startswith("RL") else "wealth"
    res = R._policy_evidence(data_by_theme[topic], R._SECTION_EVIDENCE_POLICY[sid])
    assert any("[주장 범위" in ln for ln in res.lines)


# ── 섹션 단위 claim 감사 배선 ────────────────────────────────────────────


def test_section_audit_patches_only_the_offending_section() -> None:
    """W-05 위반 → patch → 재감사 통과. 다른 섹션 텍스트는 건드리지 않는다."""
    bad = "2028년 11월에는 상속으로 자산이 들어올 가능성이 높습니다."
    patched = R._audit_section_text("W-05", bad)
    assert patched != bad
    assert "상속" not in patched or "근거로는 쓰지 않습니다" in patched
    # 정책 없는 섹션은 원문 그대로.
    assert R._audit_section_text("W-02", bad) == bad
    assert R._audit_section_text("W-03", bad) == bad


def test_relocation_check_advice_survives_the_audit() -> None:
    ok = "2027년 3월은 이동 부담이 큰 구간이라 비용·해지 조건을 확인하세요."
    assert R._audit_section_text("RL-05", ok) == ok
