"""OA-10a — 적용된 스키마 검증(실제 DB 필요).

SQL 파일 텍스트 확인만으로는 부족하다. `cd` 실패로 편집이 통째로 유실됐는데 파일만
보고 넘어갈 뻔한 적이 있다(`history_lookback_days` 누락). 서비스 계약과 직접 연결된
필드는 **실제 적용된 스키마**에서 확인한다.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"), reason="SAJU_V2_DATABASE_URL 미설정"
)

_GENERATION = "daily_fortune_board_generation"
_LEDGER = "daily_fortune_selection_ledger"
_ACTIVE = "daily_fortune_active_board"

#: 서비스 계약과 직접 연결된 필수 컬럼 — 누락되면 재현 계약이 조용히 깨진다.
_REQUIRED_COLUMNS = {
    _GENERATION: {
        "generation_id", "fortune_date", "generation_status", "generation_source",
        "replay_fidelity", "selection_policy_version", "history_contract_version",
        "taxonomy_version", "active_dict_version", "content_version",
        "event_selection_contract", "history_start_date", "history_end_date",
        "history_lookback_days", "history_set_fingerprint",
        "engine_input_fingerprint", "board_result_fingerprint",
        "authorized_domain_overrides", "event_cap_relaxations",
        "constraint_outcomes", "replay_batch_id",
    },
    _LEDGER: {
        "generation_id", "fortune_date", "ilju",
        "raw_good_winner", "raw_good_probability", "raw_good_band",
        "display_good_representative", "display_good_probability",
        "display_good_band", "display_good_semantic_family",
        "support_event", "caution_event", "raw_headline", "final_headline",
        "final_headline_semantic_family", "good_selection_reason",
        "display_displacement_loss", "selection_reason_codes", "watch_codes",
        "ilju_history_fingerprint", "row_result_fingerprint",
    },
    _ACTIVE: {
        "fortune_date", "generation_id", "activated_at", "activation_reason",
        "activation_version",
    },
}

#: 계약을 DB 로 내린 CHECK — 이름이 사라지면 가드가 사라진 것이다.
_REQUIRED_CONSTRAINTS = {
    "dfbg_history_is_past", "dfbg_lookback_sane", "dfbg_lookback_matches_range",
    "dfbg_history_ends_yesterday", "dfbg_c10_requires_history",
    "dfbg_no_unauthorized_overflow", "dfbg_replay_fidelity_declared",
    "dfsl_exceptional_band_protected", "dfsl_no_two_band_drop",
    "dfsl_loss_budget", "dfsl_loss_matches_scores", "dfsl_headline_is_displayed",
}

_GEN_COLS = (
    "generation_id, fortune_date, generation_source, selection_policy_version,"
    " history_contract_version, taxonomy_version, active_dict_version,"
    " content_version, event_selection_contract, history_start_date,"
    " history_end_date, history_lookback_days, history_set_fingerprint,"
    " engine_input_fingerprint"
)


@pytest.fixture()
def conn():
    with psycopg.connect(os.environ["SAJU_V2_DATABASE_URL"]) as c:
        yield c


def test_all_three_tables_exist(conn) -> None:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    ).fetchall()
    assert {_GENERATION, _LEDGER, _ACTIVE} <= {r[0] for r in rows}


@pytest.mark.parametrize("table", sorted(_REQUIRED_COLUMNS))
def test_required_columns_are_applied(conn, table: str) -> None:
    """SQL 파일이 아니라 **적용된 스키마**에서 확인한다."""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s",
        (table,),
    ).fetchall()
    missing = _REQUIRED_COLUMNS[table] - {r[0] for r in rows}
    assert not missing, f"{table}: 적용된 스키마에 없는 컬럼 {sorted(missing)}"


def test_contract_check_constraints_are_applied(conn) -> None:
    rows = conn.execute("SELECT conname FROM pg_constraint WHERE contype='c'").fetchall()
    missing = _REQUIRED_CONSTRAINTS - {r[0] for r in rows}
    assert not missing, f"적용되지 않은 계약 CHECK: {sorted(missing)}"


def test_commit_function_exists(conn) -> None:
    row = conn.execute(
        "SELECT 1 FROM pg_proc WHERE proname='daily_fortune_commit_generation'"
    ).fetchone()
    assert row, "STAGING → COMMITTED 전환 함수가 없다"


def test_partial_unique_indexes_are_applied(conn) -> None:
    rows = conn.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename=%s",
        (_GENERATION,),
    ).fetchall()
    assert {"dfbg_committed_identity", "dfbg_staging_single"} <= {r[0] for r in rows}


def test_lookback_and_range_must_agree(conn) -> None:
    """`history_lookback_days` 가 실제로 날짜 범위를 강제하는지 DB 에 물어본다."""
    with conn.transaction(), pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            f"INSERT INTO {_GENERATION} ({_GEN_COLS}) VALUES"
            " (%s,'2026-08-01','LIVE_PREGEN','display-selection.p4-lc.c10.v1',"
            " 'daily-selection-history.v1','taxonomy.v1','dict.v1.11','cv','esc',"
            " '2026-05-04','2026-07-31',90,%s,%s)",   # start 가 date-89 라 불일치
            (str(uuid.uuid4()), "hf-x", "if-x"),
        )


def test_ledger_rejects_s5_band_downgrade(conn) -> None:
    """C10 의 s5 보호가 DB 층에서도 강제되는지 확인한다."""
    gen = str(uuid.uuid4())
    try:
        with conn.transaction():
            conn.execute(
                f"INSERT INTO {_GENERATION} ({_GEN_COLS}) VALUES"
                " (%s,'2026-08-01','LIVE_PREGEN','display-selection.legacy-v0',"
                " 'daily-selection-history.v1','taxonomy.v1','dict.v1.11','cv','esc',"
                " '2026-05-03','2026-07-31',90,%s,%s)",
                (gen, f"hf-{gen}", f"if-{gen}"),
            )
            # 중첩 transaction = savepoint. 위반이 나도 바깥 tx 가 살아 있어야
            # 정리(rollback)가 가능하다.
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute(
                    f"INSERT INTO {_LEDGER} VALUES (%s,'2026-08-01','甲子',"
                    " 'a',88,'s5','b',84,'s4','fam','sup','cau','a','a','fam2',"
                    " 'LONGITUDINAL_ALTERNATIVE_SELECTED',4,'{}','{}',2,2,'h','r')",
                    (gen,),
                )
            # 검증만 하고 테스트 DB 를 더럽히지 않는다.
            raise psycopg.Rollback()
    except psycopg.Rollback:
        pass
