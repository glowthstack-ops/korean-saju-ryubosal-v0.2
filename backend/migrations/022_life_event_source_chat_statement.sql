-- v2.2 — 채팅 발화 입퇴사 사실의 원장 적재 (doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §8, 2026-11-18).
-- 소스에 'chat_statement'(채팅에 사용자가 스스로 적은 본인 완료형 입사·퇴사 보고)를 추가한다.
-- 이 소스의 행은 적재만 한다 — 개인 시그니처·코호트 집계는 저장소 조회에서 제외한다.
ALTER TABLE subject_life_events
  DROP CONSTRAINT IF EXISTS subject_life_events_source_check;
ALTER TABLE subject_life_events
  ADD CONSTRAINT subject_life_events_source_check
  CHECK (source IN ('reality_signal_calibration','chat_correction',
                    'chat_rating','delayed_outcome','employment_history',
                    'chat_statement'));
