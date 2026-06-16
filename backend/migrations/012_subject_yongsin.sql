-- v2.2 — 확정 용신을 사주별 독립 테이블로 분리(2026-06-16).
-- user_profiles.confirmed_yongsin은 basic/persona NOT NULL이라 프로필 행 없이는 저장 불가했다.
-- 만세력 페이지의 용신 검증 확정이 프로필 행 유무와 무관하게 DB에 영속되도록 전용 테이블로 옮긴다.
-- (사주목록 카드·수정 폼·백엔드가 모두 get_yongsin/set_yongsin 메서드로만 접근하므로 호출부 불변.)
CREATE TABLE IF NOT EXISTS subject_yongsin (
  subject_id        TEXT PRIMARY KEY,
  confirmed_yongsin TEXT,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 기존 user_profiles.confirmed_yongsin(migration 005) 값을 이관(컬럼이 있을 때만, 멱등).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'user_profiles' AND column_name = 'confirmed_yongsin'
  ) THEN
    INSERT INTO subject_yongsin (subject_id, confirmed_yongsin)
    SELECT user_id, confirmed_yongsin FROM user_profiles
    WHERE confirmed_yongsin IS NOT NULL
    ON CONFLICT (subject_id) DO NOTHING;
  END IF;
END $$;
