-- P4-1b 커리어 전이 shadow 상태 — production 권위 상태와 분리된 shadow namespace.
-- 파생 상태(episodes·frontier·observed·고용 컨텍스트)는 저장하지 않는다.
-- load 후 replay(career_journal)로 재구성해 저장-journal divergence를 원천 차단한다.
CREATE TABLE IF NOT EXISTS career_shadow_state (
    shadow_state_id            TEXT PRIMARY KEY,
    thread_id                  TEXT NOT NULL,
    subject_id                 TEXT NOT NULL,
    career_journal             JSONB NOT NULL DEFAULT '[]'::jsonb,
    journal_digest             TEXT NOT NULL DEFAULT '',
    revision                   INTEGER NOT NULL DEFAULT 0,
    semantics_contract_version TEXT NOT NULL DEFAULT '',
    producer_build_sha         TEXT NOT NULL DEFAULT '',
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- thread + subject 격리 키: 다른 thread·다른 subject 와 상태가 섞이지 않는다.
    CONSTRAINT career_shadow_state_scope UNIQUE (thread_id, subject_id)
);
