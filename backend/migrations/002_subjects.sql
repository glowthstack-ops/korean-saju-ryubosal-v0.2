-- v2.2 Phase 2.5 — 대상(self/동반자) 저장 테이블.
-- Subject Manager(E14) 전체 기능은 Phase 4(T4.4)에서 확장하고, 여기서는 사전계산
-- 스케줄러(T2.5.4)가 필요한 최소 영속화만 정의한다.
-- 활성 대상(docs/09 1장): 최근 30일 내 대화 이력(last_interaction_at) 또는 구독 중.
CREATE TABLE IF NOT EXISTS subjects (
  subject_id          TEXT PRIMARY KEY,
  owner_id            TEXT NOT NULL DEFAULT 'default',  -- 사용자 계정 도입 전 단일 소유자
  kind                TEXT NOT NULL CHECK (kind IN ('self','companion')),
  label               TEXT NOT NULL,
  aliases             JSONB NOT NULL DEFAULT '[]',      -- "1호"/"신랑" 별칭 (E14)
  relation_to_user    TEXT,
  birth               JSONB NOT NULL,                   -- BirthInput 직렬화
  gender              TEXT,
  is_minor            BOOLEAN NOT NULL DEFAULT FALSE,   -- 표현 제한 정책 연동(docs/08 G2)
  subscribed          BOOLEAN NOT NULL DEFAULT FALSE,   -- 일일운세 구독
  last_interaction_at TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_subjects_owner ON subjects (owner_id);
