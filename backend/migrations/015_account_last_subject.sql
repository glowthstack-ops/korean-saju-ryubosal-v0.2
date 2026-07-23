-- 재로그인 시 선택 사주 복원(2026-07-23 승인) — 계정 전역 "마지막 선택 사주" 서버 영속.
-- 기존에는 로그아웃 시 로컬 캐시가 삭제되고 서버 저장이 없어 복원 불가였다.
-- 타입은 subjects.subject_id(TEXT)와 동일, 사주 삭제 시 자동 NULL.
ALTER TABLE account_settings
  ADD COLUMN IF NOT EXISTS last_selected_subject_id TEXT
    REFERENCES subjects(subject_id) ON DELETE SET NULL;
