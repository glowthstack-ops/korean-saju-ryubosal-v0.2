-- v2.2 프론트 확장 Phase 1 — 계정(ID+PIN 경량 인증) + 계정 전역 설정(페르소나).
-- ID+PIN은 OAuth 도입 전 임시 본인 확인 수단(낮은 보안 등급). 같은 login_id+PIN이면
-- 같은 owner_id로 사주목록을 복원해 연속성을 보장한다. PIN은 평문 저장 금지(pbkdf2 해시).
CREATE TABLE IF NOT EXISTS accounts (
  owner_id    TEXT PRIMARY KEY,                 -- 내부 소유자 식별자(subjects.owner_id와 연결)
  login_id    TEXT UNIQUE NOT NULL,             -- 사용자 입력 로그인 ID
  pin_hash    TEXT NOT NULL,                    -- 'iterations$salt_hex$hash_hex' (pbkdf2-sha256)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 계정 전역 페르소나(문체 전용) — 궁합/관계처럼 두 사주를 함께 풀 때 상담가 문체 충돌을
-- 막기 위해 계정당 1개로 고정(docs/11 5장 PersonaConfig). 사주별이 아니다.
CREATE TABLE IF NOT EXISTS account_settings (
  owner_id    TEXT PRIMARY KEY,
  persona     JSONB NOT NULL,                   -- PersonaConfig 직렬화
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 용신 확정 결과(사주별) — user_profiles(subject_id 키)에 확정 용신을 보존해 사주목록의
-- '용신 등록여부' 인디케이터와 풀이 일관 기준으로 쓴다. UserProfile 스키마는 불변이므로
-- 컬럼만 가산(멱등).
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS confirmed_yongsin TEXT;
