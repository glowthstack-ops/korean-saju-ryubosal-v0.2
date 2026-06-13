-- v2.2 Life Event Inference — 개인 현실 사건 시그니처 저장소 (doc/v2_2/LIFE_EVENT_INFERENCE.md §4.5).
-- 사용자 확인 사건을 '원자 행'으로 저장한다(미리 버킷팅 금지 — 읽을 때 granularity별 집계).
-- 소스: 현실 신호 캘리브레이션(온보딩) / 채팅 정정·평가 / 지연 outcome 회수.
-- 코호트 지문 = 보정 후 4기둥 간지 + 성별. 일주(pillar_day)+성별 = coarse 코호트, 전체 = fine 코호트.
-- 수집 단계에서는 적재만 한다(랭킹 미반영 — 코호트 활성 게이트는 §4.4, 별도 단계에서 활성).
CREATE TABLE IF NOT EXISTS subject_life_events (
  event_row_id        TEXT PRIMARY KEY,
  subject_id          TEXT NOT NULL,
  owner_id            TEXT NOT NULL DEFAULT 'default',
  -- 코호트 지문(보정 후 산출 간지 — chart_id 아님, 진태양시로 장소별 사주가 갈리므로)
  pillar_year         TEXT NOT NULL,
  pillar_month        TEXT NOT NULL,
  pillar_day          TEXT NOT NULL,          -- 일주: coarse 코호트 키(일주+성별)
  pillar_hour         TEXT,                   -- 시주: 시간 미상이면 NULL
  gender              TEXT,
  -- 사건
  event_key           TEXT NOT NULL,          -- 21키 EventKeyV2
  period              TEXT NOT NULL,          -- '2025' / '2025-08'
  signal_fingerprint  JSONB NOT NULL DEFAULT '{}',   -- 십성그룹·궁성·관계·12운성 지문
  outcome             TEXT NOT NULL
                        CHECK (outcome IN ('confirmed','not_happened','planned',
                                           'pending','reality_fit_only')),
  source              TEXT NOT NULL
                        CHECK (source IN ('reality_signal_calibration','chat_correction',
                                          'chat_rating','delayed_outcome')),
  weight              REAL NOT NULL DEFAULT 1.0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_life_events_subject
  ON subject_life_events (owner_id, subject_id);
-- coarse 코호트(일주+성별) — 콜드스타트에 빨리 충전.
CREATE INDEX IF NOT EXISTS idx_life_events_cohort_coarse
  ON subject_life_events (pillar_day, gender, event_key);
-- fine 코호트(전체 4기둥+성별) — 데이터 쌓인 뒤.
CREATE INDEX IF NOT EXISTS idx_life_events_cohort_fine
  ON subject_life_events (pillar_year, pillar_month, pillar_day, pillar_hour, gender, event_key);
