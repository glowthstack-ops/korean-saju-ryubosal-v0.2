-- v2.2 — AI채팅상담 대화 영속화(스레드별 자동저장·열람·삭제·이어가기).
-- ConversationState(003)는 오케스트레이터 상태만 담으므로, 사용자 열람용 대화 전문은 별도 보관.
CREATE TABLE IF NOT EXISTS chat_threads (
  thread_id     TEXT PRIMARY KEY,
  owner_id      TEXT NOT NULL,
  subject_label TEXT,                 -- 대화 기준 사주 별명(표시용)
  title         TEXT,                 -- 첫 질문 요약(목록 표시)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_threads_owner ON chat_threads (owner_id);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          BIGSERIAL PRIMARY KEY,
  thread_id   TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
  text        TEXT NOT NULL,
  meta        JSONB,                  -- status·candidate_count 등(어시스턴트 턴)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages (thread_id, id);
