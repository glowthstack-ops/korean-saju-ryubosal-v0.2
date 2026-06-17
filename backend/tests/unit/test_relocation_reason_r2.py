"""Phase R2 — M10 십성 이유분류 검증 (relocation_ten_gods.json 주입).

이유분류는 해석 라벨 전용 — 점수·날짜·랭킹에 개입하지 않는다(절대원칙 1·12). 천간=명분
(이유) / 지지본기=현장(집 성격)으로 분류한다(사용자 스펙 5장). 십성 통제를 위해 합성
LuckComposite로 결정론 검증하고, 실차트로 점수 불변성을 교차 확인한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.relocation import RelocationResolver
from saju_engines.topic_builder import build_topic_context
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.precompute import (
    CompositeGanji,
    CompositeLevel,
    LuckComposite,
    TenGodPair,
)
from saju_shared_types.relocation import RelocationPeriod, RelocationQuery
from saju_shared_types.topic_context import PeriodSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_SELF = SubjectRef(kind=SubjectKind.SELF, label="본인")


def _comp(level: CompositeLevel, period_key: str, stem_tg: str, branch_tg: str) -> LuckComposite:
    """십성을 통제한 합성 LuckComposite(분류 검증 전용)."""
    return LuckComposite(
        subject_id="본인",
        level=level,
        period_key=period_key,
        ganji=CompositeGanji(stem="甲", branch="寅"),
        ten_god=TenGodPair(stem=stem_tg, branch_main=branch_tg),
        twelve_stage="건록",
        favorability="용신",
        dict_version="1.0.0",
        computed_at="2026-06-17T00:00:00+00:00",
    )


def _query() -> RelocationQuery:
    return RelocationQuery(
        group_subjects=[_SELF],
        period=RelocationPeriod(start="2026-01", end="2026-12"),
        current_location="서울",
    )


def test_reason_classifies_stem_as_motive_branch_as_property() -> None:
    """세운/월운 천간=명분, 지지=현장으로 십성 프로파일을 매핑한다."""
    resolver = RelocationResolver(_DICTS)
    # 월운 천간 상관(비표준주거형), 지지본기 식신(생활편의형).
    comps = [
        _comp(CompositeLevel.YEAR, "2026", "정관", "정관"),
        _comp(CompositeLevel.MONTH, "2026-06", "상관", "식신"),
    ]
    profiles = resolver._reason_profiles(["2026-06"], {"본인": comps}, _query())
    by_tg = {p.ten_god: p for p in profiles}
    # 천간(명분) 먼저, 지지(현장) 다음 — 십성 기준 dedup.
    assert "상관" in by_tg and by_tg["상관"].type == "비표준주거형"
    assert "위반건축물" in by_tg["상관"].risk
    assert "식신" in by_tg and by_tg["식신"].type == "생활편의형"
    assert "정관" in by_tg  # 세운 천간=지지 동일 십성은 1건으로 합쳐짐
    # source 라벨이 명분/현장을 구분한다.
    assert by_tg["상관"].source == "월운 천간(명분)"
    assert by_tg["식신"].source == "월운 지지(현장)"


def test_reason_empty_when_no_candidate_month() -> None:
    """후보월이 없으면(이사운 미약) 이유분류는 빈 리스트."""
    resolver = RelocationResolver(_DICTS)
    comps = [_comp(CompositeLevel.MONTH, "2026-06", "상관", "식신")]
    assert resolver._reason_profiles([], {"본인": comps}, _query()) == []


def test_reason_dedup_keeps_first_source() -> None:
    """동일 십성이 천간·지지에 겹치면 첫 출처(천간=명분)만 남는다."""
    resolver = RelocationResolver(_DICTS)
    comps = [
        _comp(CompositeLevel.YEAR, "2026", "편재", "편재"),
        _comp(CompositeLevel.MONTH, "2026-06", "편재", "편재"),
    ]
    profiles = resolver._reason_profiles(["2026-06"], {"본인": comps}, _query())
    assert [p.ten_god for p in profiles] == ["편재"]
    assert profiles[0].source == "세운 천간(명분)"


# ── 실차트 교차검증: 분류가 점수에 미개입 ──────────────────────────


@pytest.fixture(scope="module")
def composites_with_feb_days():
    """기준 + 2026-02 일운 병합(M10 테스트와 동일 패턴)."""
    base = CompositeBuilder(_DICTS).build(
        calculate(BirthInput(
            calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
            birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
        )), "본인", "1.0.0", "2026-06-11T00:00:00+00:00",
    )
    feb = CompositeBuilder(_DICTS).build(
        calculate(BirthInput(
            calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
            birth_place_name="서울", gender="male", reference_date=date(2026, 2, 15),
        )), "본인", "1.0.0", "2026-02-15T00:00:00+00:00",
        levels={CompositeLevel.DAY},
    )
    return [*base, *feb]


def test_reason_profiles_do_not_change_scores(composites_with_feb_days) -> None:
    """이유분류 산출 여부와 무관하게 move_dates 점수는 동일(해석 라벨 전용)."""
    resolver = RelocationResolver(_DICTS)
    result = resolver.resolve(_query(), {"본인": composites_with_feb_days}, {"본인": "土"})
    # reason_profiles는 별도 경로 — move_dates 점수에 영향이 없어야 한다.
    scores_with = [c.final_score for c in result.move_dates]
    # _reason_profiles를 빈 사전으로 무력화해도 점수가 같은지 비교.
    resolver._reason_by_ten_god = {}
    result2 = resolver.resolve(_query(), {"본인": composites_with_feb_days}, {"본인": "土"})
    assert [c.final_score for c in result2.move_dates] == scores_with
    assert result2.reason_profiles == []


def test_topic_builder_orders_reason_before_move(composites_with_feb_days) -> None:
    """M10 TopicContext: reason@ findings가 move@ findings보다 앞에 온다(출력 순서)."""
    period = PeriodSpec(start="2026-01", end="2026-12", granularity="day")
    ctx = build_topic_context(
        "M10", [_SELF], period, composites_with_feb_days,
        relocation_query=_query(),
        composites_by_subject={"본인": composites_with_feb_days},
        yongsin_by_subject={"본인": "土"},
    )
    keys = [f.key for f in ctx.findings]
    reason_idx = [i for i, k in enumerate(keys) if k.startswith("reason@")]
    move_idx = [i for i, k in enumerate(keys) if k.startswith("move@")]
    if reason_idx and move_idx:
        assert max(reason_idx) < min(move_idx)
    # 단정 금지 스타일 규칙이 실린다.
    assert any("이사 발생 단정 금지" in t for t in ctx.style_rules.tone_notes)
