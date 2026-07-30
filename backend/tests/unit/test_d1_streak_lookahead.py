"""OA-11g — 1일 선행 조회의 정보 범위·순수성·경계 불변식 회귀.

이 정책은 `LOCAL_NONREGRESSION_GUARD` 가 아니다. 오늘의 결정이 내일의 채점에
의존하므로 별도 sequencing 정책이며, 그래서 다음을 코드 수준에서 고정한다.

    LOOKAHEAD_SOURCE  = RAW_SCORER_ONLY
    LOOKAHEAD_HORIZON = EXACTLY_ONE_DAY

핵심 불변식: `d1_raw_good_winner` 는 history 를 **인자로 받지 않는다.** 그래서
"day D 의 결정은 replay 종료일과 무관하게 동일하다" 가 구성상 성립한다. 여기서는
그것을 서명 검사와 실제 호출로 둘 다 확인한다.
"""

from __future__ import annotations

import datetime as dt
import inspect
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (_BACKEND / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_oa11g_d1_streak_shadow as G  # noqa: E402

_DAY = dt.date(2026, 3, 15)
_ILJU_INDEX = 52          # 丙辰 — OA-11f-P 의 대상 일주


@pytest.fixture(scope="module")
def events() -> dict:
    """사건 카탈로그(모듈 1회 로드)."""
    import saju_engines.daily_ilju_fortune as M

    return M.load_daily_dicts().catalog["events"]


# ── 정보 범위 계약 ────────────────────────────────────────────────────────


def test_lookahead_contract_is_raw_scorer_only_and_one_day() -> None:
    """계약 필드가 넓어지면 미래 정책 시뮬레이션으로 넘어간다."""
    c = G.D1_CONTRACT
    assert c.lookahead_source == "RAW_SCORER_ONLY"
    assert c.lookahead_horizon_days == 1
    assert c.compares == "event_key"
    assert not c.reads_history
    assert not c.reads_c10_representative
    assert not c.reads_repeat_severity
    assert not c.reads_marginal_selector
    assert not c.reads_board


def test_lookahead_signature_cannot_receive_history_or_policy_state() -> None:
    """서명 자체로 history·selector·board 접근을 막는다(구성상 불변식)."""
    params = set(inspect.signature(G._raw_good_winner).parameters)
    assert params == {"day", "ilju_index", "events", "oracle_config_fp"}
    forbidden = {
        "history", "headline_history", "good_history", "hh", "gh",
        "policy", "board", "representative", "severity",
    }
    assert not (params & forbidden)


# ── 순수성 ────────────────────────────────────────────────────────────────


def test_oracle_lookup_is_deterministic(events) -> None:
    """같은 (날짜, 일주)는 항상 같은 projection — 반복 조회가 테이블을 안 바꾼다."""
    o = G.build_raw_winner_oracle(
        events, first=dt.date(2026, 3, 15), last=dt.date(2026, 3, 15)
    )
    size = len(o.table)
    reads = [o.lookup(dt.date(2026, 3, 15), "丙辰") for _ in range(3)]
    assert reads[0] is not None
    assert all(r == reads[0] for r in reads)
    assert len(o.table) == size


def test_oracle_end_date_does_not_change_overlapping_projections(events) -> None:
    """생성 종료일을 늘려도 겹치는 구간의 projection 이 동일해야 한다.

    917일 replay 를 종료일 3종으로 돌리는 대형 실행 대신 작은 경계 fixture 로
    봉인한다 — 추가 padding 이 과거 값을 바꾸면 oracle 이 실행 범위를 읽고 있다는
    뜻이고, 그것은 이 범위에서도 드러난다.
    """
    near = G.build_raw_winner_oracle(
        events, first=dt.date(2026, 3, 14), last=dt.date(2026, 3, 16)
    )
    far = G.build_raw_winner_oracle(
        events, first=dt.date(2026, 3, 14), last=dt.date(2026, 4, 30)
    )
    overlap = sorted(near.table)
    assert overlap, "겹치는 키가 없으면 공허한 통과다"
    assert all(near.table[k] == far.table[k] for k in overlap)
    # 설정 지문은 생성 범위에 좌우되지 않는다.
    assert near.config == far.config


def test_oracle_config_fp_ignores_generation_range(events) -> None:
    """oracle 설정 지문에 날짜 범위가 섞이면 padding 이 지문을 흔든다."""
    a = G.build_raw_winner_oracle(
        events, first=dt.date(2026, 3, 14), last=dt.date(2026, 3, 15)
    )
    b = G.build_raw_winner_oracle(
        events, first=dt.date(2027, 1, 1), last=dt.date(2027, 1, 2)
    )
    assert a.config["raw_winner_oracle_config_fp"] == b.config[
        "raw_winner_oracle_config_fp"
    ]


def test_build_fails_closed_on_incomplete_ilju_set(events, monkeypatch) -> None:
    """일주 목록이 줄면 artifact 로 넘기지 않고 build 가 실패해야 한다.

    기대값을 `len(B._ILJUS)` 에서 유도하면 목록이 줄어도 기대값이 같이 줄어 검사가
    통과한다 — 그래서 판 계약 상수 `ILJU_COUNT` 로 고정했고 여기서 그것을 지킨다.
    """
    assert G.ILJU_COUNT == 60
    monkeypatch.setattr(G.B, "_ILJUS", G.B._ILJUS[:59])
    with pytest.raises(RuntimeError, match="ILJU_SET_INCOMPLETE"):
        G.build_raw_winner_oracle(
            events, first=dt.date(2026, 3, 14), last=dt.date(2026, 3, 15)
        )


def test_guard_eligibility_uses_the_r6_proposal_not_the_c10_fallback() -> None:
    """적격성은 'R6 제안이 원시 1위를 치환하는가' 다. fallback 은 기준값이 아니다."""
    assert G.guard_eligible(
        raw_winner_event_key="good_news_arrives",
        proposed_r6_event_key="old_contact",
        safe_positive_candidate_exists=True,
    )
    assert not G.guard_eligible(
        raw_winner_event_key="good_news_arrives",
        proposed_r6_event_key="good_news_arrives",   # 치환하지 않음
        safe_positive_candidate_exists=True,
    )
    assert not G.guard_eligible(
        raw_winner_event_key="good_news_arrives",
        proposed_r6_event_key=None,
        safe_positive_candidate_exists=False,
    )


def test_eligible_partition_is_enforced_by_the_ledger() -> None:
    """적격 행은 세 사유로만 분할된다 — 합이 어긋나면 계상이 틀린 것이다."""
    led = G.LookaheadLedger()
    led.guard_eligible_rows = 3
    led.logical_lookahead_queries = 3
    led.reasons[G.D1_STREAK_PRESERVED] = 2
    led.reasons[G.D1_WINNER_DIFFERENT] = 1
    led.not_eligible_rows = 5
    led.reasons[G.D1_NOT_ELIGIBLE] = 5
    rec = led.as_record()
    assert rec["eligible_partition_sum"] == 3
    assert rec["eligible_partition_holds"]
    assert rec["not_eligible_consumed_zero_lookups"]
    assert rec["repeated_logical_queries"] == 3   # 고유 키를 기록하지 않은 경우


def test_ledger_record_hides_internal_sets() -> None:
    """artifact 에 내부 집합이 그대로 새어 나가면 직렬화가 깨진다."""
    rec = G.LookaheadLedger().as_record()
    assert "unique_oracle_keys" in rec and isinstance(rec["unique_oracle_keys"], int)


# ── 가드 판정 ─────────────────────────────────────────────────────────────


def _proj(key: str | None) -> G.RawWinnerProjection:
    return G.RawWinnerProjection(key, 70, f"-70|{key}", "v", "fp")


def test_reason_is_streak_preserved_when_next_day_repeats() -> None:
    """OA-11f-P 의 2026-03-14 조건 — 내일도 같은 원시 1위."""
    assert G.streak_preservation_reason(
        d_raw_winner="good_news_arrives", proposed_r6_event_key="old_contact",
        d1=_proj("good_news_arrives"),
    ) == G.D1_STREAK_PRESERVED


def test_reason_is_different_when_next_day_changes() -> None:
    """내일 원시 1위가 다르면 연속 반복이 생기지 않으므로 개입을 유지한다."""
    assert G.streak_preservation_reason(
        d_raw_winner="good_news_arrives", proposed_r6_event_key="old_contact",
        d1=_proj("teamwork_flow"),
    ) == G.D1_WINNER_DIFFERENT


def test_reason_is_unavailable_and_fails_closed() -> None:
    """조회 불가는 개입 허용이 아니라 C10 유지(fail-closed)다."""
    assert G.streak_preservation_reason(
        d_raw_winner="good_news_arrives", proposed_r6_event_key="old_contact",
        d1=None,
    ) == G.D1_UNAVAILABLE
    assert G.D1_CONTRACT.unavailable_action == "FAIL_CLOSED_TO_C10"


def test_reason_is_not_eligible_before_any_lookup() -> None:
    """비적격은 조회 **전** 상태다 — 적격 3분할의 분모에 들어가지 않는다."""
    assert G.streak_preservation_reason(
        d_raw_winner="good_news_arrives", proposed_r6_event_key=None, d1=None,
    ) == G.D1_NOT_ELIGIBLE


# ── 경계 계약 ─────────────────────────────────────────────────────────────


def test_oracle_range_is_exactly_one_day_of_padding() -> None:
    """조회가 건드리는 마지막 날은 평가 마지막 날 +1 이며 commit 대상이 아니다."""
    assert G.ORACLE_LAST == G.EVALUATION_LAST + dt.timedelta(days=1)
    assert G.ORACLE_LAST == dt.date(2027, 10, 10)
    assert G.ORACLE_FIRST == dt.date(2025, 4, 7)
    days = (G.ORACLE_LAST - G.ORACLE_FIRST).days + 1
    assert days == 917 and days * 60 == 55_020


def test_fixture_target_matches_the_measured_causal_case() -> None:
    """골든 fixture 대상이 OA-11f-P 가 확정한 사례에서 벗어나면 안 된다."""
    assert G.FIXTURE_ILJU == "丙辰"
    assert (G.FIXTURE_BLOCK_DATE, G.FIXTURE_EFFECT_DATE) == (
        "2026-03-14", "2026-03-15"
    )
    assert G.FIXTURE_ANCHOR == "2026-04-02"
