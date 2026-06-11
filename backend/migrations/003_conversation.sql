-- v2.2 Phase 4 (T4.1) — 대화 스레드 상태 저장.
-- ConversationState 전체(JSONB)를 스레드 단위로 보존한다. 전용 인스턴스 saju-v2-db(5433).
CREATE TABLE IF NOT EXISTS conversation_threads (
  thread_id   TEXT PRIMARY KEY,
  owner_id    TEXT NOT NULL DEFAULT 'default',
  subject_id  TEXT,                          -- 주 대상(self) — subjects 테이블 참조(느슨)
  state       JSONB NOT NULL,                -- ConversationState 직렬화
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_threads_owner ON conversation_threads (owner_id);
