-- v2.2 — 용신 검증 Q&A 답변을 사주별로 서버 영속(2026-07-02).
-- 기존 subject_yongsin(012)에는 확정 용신 오행만 저장돼, 다른 기기에서 재검증 시 과거 답변이
-- 초기화됐다. 검증 답변+결과(jsonb)를 함께 저장해 어느 기기에서든 '수정 모드'로 프리필한다.
ALTER TABLE subject_yongsin ADD COLUMN IF NOT EXISTS calibration jsonb;
