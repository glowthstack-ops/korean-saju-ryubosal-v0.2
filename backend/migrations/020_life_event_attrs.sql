-- v2.2 — 직장 이력 캘리브레이션 P0 (doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §2-1, 2026-10-22).
-- 사용자 제공 사실의 부가 속성(정확한 날짜·회상 정밀도·성격·입사 통로·퇴사 사유·같은 직장 묶기·
-- 회사명·절기월 라벨)을 attrs JSONB 한 컬럼에 담는다. 코호트 인덱스는 건드리지 않는다.
-- 소스에 'employment_history'(자격득실 수준의 직장 이력 — 정본)를 추가한다.
ALTER TABLE subject_life_events
  ADD COLUMN IF NOT EXISTS attrs JSONB NOT NULL DEFAULT '{}';
ALTER TABLE subject_life_events
  DROP CONSTRAINT IF EXISTS subject_life_events_source_check;
ALTER TABLE subject_life_events
  ADD CONSTRAINT subject_life_events_source_check
  CHECK (source IN ('reality_signal_calibration','chat_correction',
                    'chat_rating','delayed_outcome','employment_history'));
