-- 2026-10-24 보안 점검 S4: 대화 스레드를 명식(subject_id)에 묶는다.
-- 대화 상태(user_facts·약속·시점 슬롯)는 thread_id 에만 묶여 있어, 같은 계정에서 명식을
-- 바꾼 뒤 이어보기를 누르면 다른 명식의 사실이 주입되던 결함의 교정. 기존 행은 NULL(미바인딩)
-- 이며 다음 턴에 그 턴의 subject_id 로 1회 묶인다(COALESCE).
ALTER TABLE chat_threads ADD COLUMN IF NOT EXISTS subject_id TEXT;
CREATE INDEX IF NOT EXISTS idx_chat_threads_owner_subject ON chat_threads (owner_id, subject_id);
