-- v2.2 Phase 2.5 (docs/09 3장) — 사전계산 저장 테이블.
-- 대상 인스턴스: saju-v2-db (호스트 5433) — v1 DB(5432)와 분리 운영.
CREATE TABLE IF NOT EXISTS luck_composites (
  subject_id   TEXT NOT NULL,
  level        TEXT NOT NULL CHECK (level IN ('natal','daewoon','year','month','day')),
  period_key   TEXT NOT NULL,
  dict_version TEXT NOT NULL,
  payload      JSONB NOT NULL,          -- LuckComposite 직렬화
  computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (subject_id, level, period_key, dict_version)
);
CREATE INDEX IF NOT EXISTS idx_lc_subject_level ON luck_composites (subject_id, level);
-- day 레벨 보존 기간: 과거 90일 / 미래 400일 외 삭제 배치 (스토리지 통제 — T2.5.5)
