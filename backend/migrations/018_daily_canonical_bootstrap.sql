-- OA-10a 개정 — `CANONICAL_BOOTSTRAP`.
--
-- 초기 계획(과거 90일을 CONTRACT_REPLAY 로 채운다)은 전제가 틀렸다. 일운 서비스는
-- 2026-07-23 에 시작했고, D-90 구간의 83일은 서비스가 존재하지 않던 날짜다. 그 구간을
-- 현재 코드로 만들면 재현이 아니라 날조다.
--
-- 그런데 애초에 필요한 것이 "사용자가 실제로 본 90일"이 아니었다. 일운 보드는 일주별
-- **공통** 결과이고, C10 이 필요로 하는 것은 개인 열람 기록이 아니라
-- **공식 풀에서 어떤 사건이 어떻게 배치됐는가** 라는 스케줄러 순환 상태다.
--
--   LIVE_COMMITTED       실제로 그 날짜에 공개된 공식 보드
--   CONTRACT_REPLAY      과거에 실제 존재했던 계약을 재현한 결과
--   CANONICAL_BOOTSTRAP  공개 전 최종 정책을 안정 상태로 초기화하는 가상 배치
--
-- bootstrap 은 "과거에 이 사건을 보여줬다"고 주장하지 않는다. 공개일 스케줄러를 미리
-- 안정화하는 계산 구간이므로 날조가 아니다. C10 이 이미 통과한 self-warmup 측정
-- (warm-up 90일 → 측정 90일)을 배포 초기화 계약으로 공식화한 것이다.

DO $$ BEGIN
    ALTER TYPE daily_generation_source ADD VALUE IF NOT EXISTS 'CANONICAL_BOOTSTRAP';
END $$;

DO $$ BEGIN
    ALTER TYPE daily_replay_fidelity ADD VALUE IF NOT EXISTS 'NOT_APPLICABLE';
END $$;

ALTER TABLE daily_fortune_board_generation
    ADD COLUMN IF NOT EXISTS bootstrap_contract_version TEXT,
    ADD COLUMN IF NOT EXISTS bootstrap_anchor_date      DATE,
    ADD COLUMN IF NOT EXISTS bootstrap_warmup_days      SMALLINT,
    -- 최초 공개일 이전의 canonical 행은 상태 계산용이며 사용자에게 공개되지 않는다.
    ADD COLUMN IF NOT EXISTS is_published               BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN daily_fortune_board_generation.bootstrap_anchor_date IS
    'C10 최초 공개일. bootstrap 은 anchor - warmup - lookback 부터 anchor - 1 까지를 만든다.';
COMMENT ON COLUMN daily_fortune_board_generation.is_published IS
    'false = 스케줄러 상태 계산용(비공개). true = 사용자에게 제공된 보드.';

-- 017 의 `dfbg_replay_fidelity_declared` 는 source 가 replay 2종이거나 아니거나의
-- 이분법이었다. bootstrap 은 재현이 아니므로 제3의 상태가 필요하다 — 재정의한다.
--   replay 2종   → EXACT_CONTRACT_REPLAY | PARTIAL
--   bootstrap    → NOT_APPLICABLE
--   그 외(live)  → NOT_REPLAY
ALTER TABLE daily_fortune_board_generation
    DROP CONSTRAINT IF EXISTS dfbg_replay_fidelity_declared;

DO $$ BEGIN
    ALTER TABLE daily_fortune_board_generation
        ADD CONSTRAINT dfbg_replay_fidelity_declared CHECK (
            CASE generation_source::text
                WHEN 'CONTRACT_REPLAY'    THEN replay_fidelity::text IN
                                               ('EXACT_CONTRACT_REPLAY', 'PARTIAL')
                WHEN 'BACKFILL_REPLAY'    THEN replay_fidelity::text IN
                                               ('EXACT_CONTRACT_REPLAY', 'PARTIAL')
                WHEN 'CANONICAL_BOOTSTRAP' THEN replay_fidelity::text = 'NOT_APPLICABLE'
                ELSE replay_fidelity::text = 'NOT_REPLAY'
            END
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- bootstrap 은 anchor·계약·기간을 반드시 밝힌다. 그래야 언제든 같은 입력으로
-- 재생해 fingerprint 일치를 확인할 수 있다.
DO $$ BEGIN
    ALTER TABLE daily_fortune_board_generation
        ADD CONSTRAINT dfbg_bootstrap_fields CHECK (
            generation_source::text <> 'CANONICAL_BOOTSTRAP'
            OR (
                bootstrap_contract_version IS NOT NULL
                AND bootstrap_anchor_date IS NOT NULL
                AND bootstrap_warmup_days IS NOT NULL
                AND bootstrap_warmup_days > 0
                AND history_lookback_days IS NOT NULL
            )
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- bootstrap 행은 anchor 이전만 존재한다. anchor 당일부터는 실제 공개 보드다.
DO $$ BEGIN
    ALTER TABLE daily_fortune_board_generation
        ADD CONSTRAINT dfbg_bootstrap_is_before_anchor CHECK (
            generation_source::text <> 'CANONICAL_BOOTSTRAP'
            OR fortune_date < bootstrap_anchor_date
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- bootstrap 행을 공개본으로 표시할 수 없다 — 사용자에게 제공한 적이 없다.
DO $$ BEGIN
    ALTER TABLE daily_fortune_board_generation
        ADD CONSTRAINT dfbg_bootstrap_is_not_published CHECK (
            generation_source::text <> 'CANONICAL_BOOTSTRAP' OR is_published = false
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- bootstrap 계약이 바뀌면 기존 generation 을 재사용하지 않는다.
-- 술어에 `generation_source` 를 쓰지 않는다 — 새 enum 값은 같은 트랜잭션에서
-- 리터럴로 쓸 수 없고(unsafe use of new value), `::text` 캐스트는 STABLE 이라
-- index predicate 에 들어갈 수 없다. `bootstrap_anchor_date IS NOT NULL` 이
-- bootstrap 행과 동치다(`dfbg_bootstrap_fields` 가 보장).
CREATE UNIQUE INDEX IF NOT EXISTS dfbg_bootstrap_identity
    ON daily_fortune_board_generation (
        fortune_date, selection_policy_version, bootstrap_contract_version,
        bootstrap_anchor_date
    )
    WHERE generation_status = 'COMMITTED' AND bootstrap_anchor_date IS NOT NULL;

-- 공개된 보드만 조회하는 경로(정식 공개 이후 불변성 검사에 쓴다).
CREATE INDEX IF NOT EXISTS dfbg_published
    ON daily_fortune_board_generation (fortune_date)
    WHERE is_published;
