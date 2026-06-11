-- v2.2 Phase 8.5 (docs/11 6장) — 사용자 프로필 저장.
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id        TEXT PRIMARY KEY,
  basic          JSONB NOT NULL,        -- BasicProfile
  extended       JSONB,                 -- ExtendedProfile (전체/부분 null 허용)
  persona        JSONB NOT NULL,        -- PersonaConfig (기본값 채움)
  extended_completed_at TIMESTAMPTZ,    -- null = 2단계 스킵 상태
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
