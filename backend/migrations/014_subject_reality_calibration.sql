-- v2.2 — 현실 신호 캘리브레이션 '해상도' 값 저장(docs/14 결정①, 2026-07-02).
-- subject_life_events는 발생/미발생(personal_match)만 유지하고, 연 단위 overall_rating·
-- domain_ratings·사건별 experience·period_nuance는 per-subject jsonb blob에 별도 저장한다.
-- (per-year 값이 per-event-row 테이블에 안 맞음 → 억지 컬럼화 대신 payload로.)
CREATE TABLE IF NOT EXISTS subject_reality_calibration (
  subject_id TEXT PRIMARY KEY,
  owner_id   TEXT NOT NULL,
  payload    jsonb NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
