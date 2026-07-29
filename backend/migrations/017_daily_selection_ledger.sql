-- OA-10a 일별 선택 원장 — C10 표시 정책의 상태 SSOT.
--
-- C10 은 이전 날짜의 선택 결과에 의존한다. 메모리 순차 재생만으로는 재기동·캐시
-- 유실·백필·동시 생성을 감당할 수 없으므로 **DB 원자성을 최종 SSOT** 로 두고
-- Redis 는 보조 캐시로만 쓴다.
--
--   생성 시도          board_generation   어떤 계약·history 로 만들었나
--   60일주 결과 원장   selection_ledger   무엇을 골랐고 왜 골랐나
--   날짜별 활성 포인터 active_board       그 날짜의 게시 기준은 무엇인가
--
-- 계약을 코드에만 두지 않는다. 미래 누수·손실 예산·s5 보호·2단계 밴드 하락·설명되지
-- 않은 domain 초과는 CHECK 로 내려, 잘못된 행은 **저장 자체가 실패**하게 한다.
--
-- 개인정보를 저장하지 않는다 — 일주별 공통 보드 이력이며 subject/account/조회 여부/
-- 카드 본문을 담지 않는다. 따라서 TTL 파기 대상이 아니고 장기 보존한다.

DO $$ BEGIN
    CREATE TYPE daily_generation_status AS ENUM ('STAGING', 'COMMITTED', 'ABORTED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE daily_generation_source AS ENUM (
        'LIVE_PREGEN',        -- 23:50 KST 선생성
        'LIVE_ON_DEMAND',     -- 캐시 미스 시 요청 경로 생성
        'CONTRACT_REPLAY',    -- 원장이 없어 당시 계약으로 재현 (실제 게시본이 아님)
        'BACKFILL_REPLAY'     -- 결손·변경 이후 날짜순 재생
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE daily_replay_fidelity AS ENUM ('EXACT_CONTRACT_REPLAY', 'PARTIAL', 'NOT_REPLAY');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE daily_activation_reason AS ENUM (
        'LIVE_INITIAL', 'REPLAY_RECOVERY', 'BACKFILL_REPLACEMENT', 'EMERGENCY_ROLLBACK'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ── A. 보드 생성 단위 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_fortune_board_generation (
    generation_id                UUID PRIMARY KEY,
    fortune_date                 DATE NOT NULL,
    generation_status            daily_generation_status NOT NULL DEFAULT 'STAGING',
    generation_source            daily_generation_source NOT NULL,
    -- 재현본의 정확성. PARTIAL 은 C10 history 로 쓸 수 없다.
    replay_fidelity              daily_replay_fidelity NOT NULL DEFAULT 'NOT_REPLAY',

    -- 계약 6종. 하나라도 다르면 다른 결과가 나올 수 있다.
    selection_policy_version     TEXT NOT NULL,
    history_contract_version     TEXT NOT NULL,
    taxonomy_version             TEXT NOT NULL,
    active_dict_version          TEXT NOT NULL,
    content_version              TEXT NOT NULL,
    event_selection_contract     TEXT NOT NULL,

    -- 어떤 이력을 읽고 만들었는가
    history_start_date           DATE,
    history_end_date             DATE,
    history_set_fingerprint      TEXT NOT NULL,
    engine_input_fingerprint     TEXT NOT NULL,
    board_result_fingerprint     TEXT,

    -- 제약 완화 결과. 승인된 override 만 허용된다.
    authorized_domain_overrides  INTEGER NOT NULL DEFAULT 0,
    event_cap_relaxations        INTEGER NOT NULL DEFAULT 0,
    constraint_outcomes          JSONB NOT NULL DEFAULT
        '{"domain_cap_hard_violation": 0}'::jsonb,

    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    committed_at                 TIMESTAMPTZ,
    replay_batch_id              UUID,

    -- 미래 누수 차단 — 오늘(이후) 이력을 오늘 보드에 쓸 수 없다.
    CONSTRAINT dfbg_history_is_past CHECK (
        history_end_date IS NULL OR history_end_date < fortune_date
    ),
    CONSTRAINT dfbg_history_range CHECK (
        history_start_date IS NULL OR history_end_date IS NULL
        OR history_start_date <= history_end_date
    ),
    -- C10 은 history 없이 실행될 수 없다. 빈 이력으로 돌리면 전 사건이
    -- "90일 미사용" 으로 인식돼 결과가 크게 흔들린다(legacy 정책은 NULL 허용).
    -- 구간 길이(LONGTERM_LOOKBACK_DAYS)는 코드 상수라 SQL 에 복제하지 않는다 —
    -- 여기서는 **끝점만** 강제하고 길이는 서비스·회귀가 지킨다.
    CONSTRAINT dfbg_c10_requires_history CHECK (
        selection_policy_version NOT LIKE 'display-selection.p4-lc.%'
        OR (
            history_start_date IS NOT NULL
            AND history_end_date IS NOT NULL
            AND history_end_date = fortune_date - 1
        )
    ),
    -- COMMITTED 는 결과 지문과 시각을 반드시 갖는다.
    CONSTRAINT dfbg_committed_needs_result CHECK (
        generation_status <> 'COMMITTED'
        OR (board_result_fingerprint IS NOT NULL AND committed_at IS NOT NULL)
    ),
    -- 재현본은 정확성 상태를 밝힌다.
    CONSTRAINT dfbg_replay_fidelity_declared CHECK (
        (generation_source IN ('CONTRACT_REPLAY', 'BACKFILL_REPLAY'))
            = (replay_fidelity <> 'NOT_REPLAY')
    ),
    -- 설명되지 않은 domain 초과는 저장 자체를 막는다. 키 존재와 타입을 먼저
    -- 강제해야 cast 오류가 나지 않는다.
    CONSTRAINT dfbg_no_unauthorized_overflow CHECK (
        constraint_outcomes ? 'domain_cap_hard_violation'
        AND jsonb_typeof(constraint_outcomes -> 'domain_cap_hard_violation') = 'number'
        AND (constraint_outcomes ->> 'domain_cap_hard_violation')::int = 0
    ),
    CONSTRAINT dfbg_override_counts_nonneg CHECK (
        authorized_domain_overrides >= 0 AND event_cap_relaxations >= 0
    )
);

COMMENT ON COLUMN daily_fortune_board_generation.generation_source IS
    'CONTRACT_REPLAY 는 실제 게시본이 아니라 당시 계약을 재실행한 결과다. '
    'LIVE_COMMITTED 로 표기하지 않는다.';


-- ── B. 일주별 선택 원장 ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_fortune_selection_ledger (
    generation_id                   UUID NOT NULL
        REFERENCES daily_fortune_board_generation(generation_id) ON DELETE CASCADE,
    fortune_date                    DATE NOT NULL,
    ilju                            TEXT NOT NULL,

    raw_good_winner                 TEXT NOT NULL,
    raw_good_probability            SMALLINT NOT NULL,
    raw_good_band                   TEXT NOT NULL,

    display_good_representative     TEXT NOT NULL,
    display_good_probability        SMALLINT NOT NULL,
    display_good_band               TEXT NOT NULL,
    -- semantic_family 를 하나만 두지 않는다. C10 은 최종 노출(1차)과 good 슬롯
    -- 본문 반복(보조)을 **각각** 이력으로 쓴다.
    display_good_semantic_family    TEXT NOT NULL,

    support_event                   TEXT NOT NULL,
    caution_event                   TEXT NOT NULL,

    raw_headline                    TEXT NOT NULL,   -- 보드 캡 이전
    final_headline                  TEXT NOT NULL,   -- 보드 캡 이후 = 게시본
    final_headline_semantic_family  TEXT NOT NULL,

    good_selection_reason           TEXT NOT NULL,
    display_displacement_loss       SMALLINT NOT NULL,

    selection_reason_codes          TEXT[] NOT NULL DEFAULT '{}',
    watch_codes                     TEXT[] NOT NULL DEFAULT '{}',

    raw_supporting_groups           SMALLINT,
    display_supporting_groups       SMALLINT,

    ilju_history_fingerprint        TEXT NOT NULL,
    row_result_fingerprint          TEXT NOT NULL,

    PRIMARY KEY (generation_id, ilju),

    CONSTRAINT dfsl_band_vocabulary CHECK (
        raw_good_band IN ('s5','s4','s3','s2')
        AND display_good_band IN ('s5','s4','s3','s2')
    ),
    CONSTRAINT dfsl_probability_range CHECK (
        raw_good_probability BETWEEN 5 AND 95
        AND display_good_probability BETWEEN 5 AND 95
    ),
    CONSTRAINT dfsl_loss_budget CHECK (display_displacement_loss BETWEEN 0 AND 7),
    -- 예외적으로 강한 s5 는 어떤 경우에도 하위 밴드 대표로 대체하지 않는다.
    CONSTRAINT dfsl_exceptional_band_protected CHECK (
        raw_good_band <> 's5' OR display_good_band = 's5'
    ),
    -- 두 단계 이상 하락 금지 (s4→s2 · s3→s2).
    CONSTRAINT dfsl_no_two_band_drop CHECK (
        NOT (raw_good_band = 's4' AND display_good_band = 's2')
        AND NOT (raw_good_band = 's3' AND display_good_band = 's2')
    ),
    -- 대표를 바꾸지 않았으면 손실이 0 이고 점수도 같다.
    CONSTRAINT dfsl_loss_consistency CHECK (
        display_good_representative <> raw_good_winner
        OR (display_displacement_loss = 0
            AND display_good_probability = raw_good_probability)
    ),
    -- 손실은 두 점수의 차와 일치한다.
    CONSTRAINT dfsl_loss_matches_scores CHECK (
        display_displacement_loss = raw_good_probability - display_good_probability
    ),
    -- 카드에 표시되지 않는 사건이 헤드라인이 될 수 없다.
    CONSTRAINT dfsl_headline_is_displayed CHECK (
        final_headline IN (display_good_representative, support_event, caution_event)
        AND raw_headline IN (display_good_representative, support_event, caution_event)
    ),
    CONSTRAINT dfsl_slots_distinct CHECK (
        display_good_representative <> support_event
        AND display_good_representative <> caution_event
        AND support_event <> caution_event
    )
);


-- ── C. 날짜별 활성 보드 포인터 ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_fortune_active_board (
    fortune_date        DATE PRIMARY KEY,
    generation_id       UUID NOT NULL
        REFERENCES daily_fortune_board_generation(generation_id),
    activated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    activation_reason   daily_activation_reason NOT NULL,
    activation_version  BIGINT NOT NULL DEFAULT 1,

    CONSTRAINT dfab_version_positive CHECK (activation_version >= 1)
);

COMMENT ON TABLE daily_fortune_active_board IS
    '서비스는 원장의 최신 행이나 임의의 COMMITTED 행을 읽지 않는다. '
    '언제나 이 포인터가 가리키는 generation 만 조회한다.';


-- ── 인덱스 ────────────────────────────────────────────────────────────────

-- 같은 입력·같은 이력의 재계산은 기존 generation 을 재사용하게 만든다.
CREATE UNIQUE INDEX IF NOT EXISTS dfbg_committed_identity
    ON daily_fortune_board_generation (
        fortune_date, selection_policy_version,
        history_set_fingerprint, engine_input_fingerprint
    )
    WHERE generation_status = 'COMMITTED';

-- 진행 중 STAGING 중복을 조기에 막는다(배치별로는 허용).
CREATE UNIQUE INDEX IF NOT EXISTS dfbg_staging_single
    ON daily_fortune_board_generation (
        fortune_date, selection_policy_version,
        COALESCE(replay_batch_id, generation_id)
    )
    WHERE generation_status = 'STAGING';

CREATE INDEX IF NOT EXISTS dfbg_date_status
    ON daily_fortune_board_generation (fortune_date, generation_status);
CREATE INDEX IF NOT EXISTS dfbg_replay_batch
    ON daily_fortune_board_generation (replay_batch_id)
    WHERE replay_batch_id IS NOT NULL;
-- history 조회 경로 (일주별 D-89 ~ D-1 범위 스캔)
CREATE INDEX IF NOT EXISTS dfsl_history_lookup
    ON daily_fortune_selection_ledger (ilju, fortune_date);


-- ── COMMITTED 전환 전용 함수 ──────────────────────────────────────────────
--
-- 다른 테이블의 60행을 일반 CHECK 로 검사할 수 없다. 서비스가 직접
-- `status='COMMITTED'` 로 UPDATE 하지 못하도록 경로를 이 함수로 제한한다.

CREATE OR REPLACE FUNCTION daily_fortune_commit_generation(
    p_generation_id UUID,
    p_board_result_fingerprint TEXT,
    p_expected_row_count INTEGER DEFAULT 60
) RETURNS daily_fortune_board_generation
LANGUAGE plpgsql AS $$
DECLARE
    v_row_count   INTEGER;
    v_ilju_count  INTEGER;
    v_date        DATE;
    v_out         daily_fortune_board_generation;
BEGIN
    SELECT fortune_date INTO v_date
      FROM daily_fortune_board_generation
     WHERE generation_id = p_generation_id
       AND generation_status = 'STAGING'
     FOR UPDATE;

    IF v_date IS NULL THEN
        RAISE EXCEPTION 'GENERATION_NOT_STAGING: %', p_generation_id
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT count(*), count(DISTINCT ilju)
      INTO v_row_count, v_ilju_count
      FROM daily_fortune_selection_ledger
     WHERE generation_id = p_generation_id
       AND fortune_date = v_date;

    IF v_row_count <> p_expected_row_count OR v_ilju_count <> p_expected_row_count THEN
        RAISE EXCEPTION
            'LEDGER_INCOMPLETE: rows=% distinct_ilju=% expected=%',
            v_row_count, v_ilju_count, p_expected_row_count
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE daily_fortune_board_generation
       SET generation_status = 'COMMITTED',
           board_result_fingerprint = p_board_result_fingerprint,
           committed_at = now()
     WHERE generation_id = p_generation_id
    RETURNING * INTO v_out;

    RETURN v_out;
END $$;

COMMENT ON FUNCTION daily_fortune_commit_generation IS
    'STAGING → COMMITTED 전환의 유일한 경로. 60행·60일주 완전성을 확인한다.';
