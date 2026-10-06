-- LLM 서비스 중단 상태 (2026-10-06, 데굴님 승인 설계 — doc/v2_2/LLM_SERVICE_SUSPENSION.md).
--
-- 공급자 비용 소진(insufficient_quota / 일일 쿼터 / 결제 중단)으로 메인·폴백이 모두 막히면
-- 서비스는 '일시 중단(suspended)' 상태로 전이하고, 관리자가 결제 후 콘솔에서 프로브를 거쳐
-- 재개한다. 상태를 프로세스 메모리가 아니라 DB 단일 행에 두는 이유:
--   ① 재기동 뒤에도 중단 상태가 유지되어야 한다(기동 직후 첫 사용자 요청이 소진 호출을 내지 않게).
--   ② 관리자 재개가 단일 진리원본이어야 한다(채팅·리포트·일운 교정이 같은 상태를 본다).
--
-- providers: 공급자별 소진/쿨다운 기록 {"gemini": {"model","kind","detail","since","until"}, ...}
--   kind = 'quota'(명시 소진 신호) | 'cooldown'(애매한 429 연속 — 자동 복귀)
-- last_probe: 마지막 재개 프로브 결과(관리자 콘솔 표시용)
CREATE TABLE IF NOT EXISTS llm_service_state (
  id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  state         TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'suspended')),
  reason        TEXT,                                   -- quota_exhausted | manual
  suspended_at  TIMESTAMPTZ,
  resumed_at    TIMESTAMPTZ,
  resumed_by    TEXT,                                   -- 재개한 관리자 owner_id
  providers     JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_probe    JSONB,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO llm_service_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
