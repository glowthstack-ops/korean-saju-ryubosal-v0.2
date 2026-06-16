-- v2.2 — AI채팅상담 백그라운드 생성: 어시스턴트 답변 상태(pending/done/error)·열람 여부.
-- 클라이언트 이탈/새로고침/교차기기에도 답변이 서버에서 끝까지 생성·영속되고,
-- 재진입 시 폴링으로 복구하며 미열람 완료 답변은 뱃지로 알린다(2026-06-16).
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'done';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS seen   BOOLEAN NOT NULL DEFAULT TRUE;
-- pending 답변(생성 중)을 스레드별로 빠르게 조회.
CREATE INDEX IF NOT EXISTS idx_chat_messages_pending
  ON chat_messages (thread_id) WHERE status = 'pending';
