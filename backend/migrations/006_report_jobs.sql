-- v2.2 프론트 확장 Phase 6 — 리포트(테마사주) 비동기 생성 잡.
-- RPT_FULL은 섹션별 LLM 호출을 순차로 도는 수 분 작업이라 동기 응답이 불가 → 잡 + 폴링.
CREATE TABLE IF NOT EXISTS report_jobs (
  job_id         TEXT PRIMARY KEY,
  owner_id       TEXT NOT NULL,
  spec           JSONB NOT NULL,           -- ReportSpec 직렬화(재현·표시용)
  status         TEXT NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued','running','completed','on_hold','failed')),
  sections_done  INT NOT NULL DEFAULT 0,
  sections_total INT NOT NULL DEFAULT 0,
  result         JSONB,                    -- ReportResult(완료 시)
  error          TEXT,                     -- 실패 사유(LLM 키 미설정 등)
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_report_jobs_owner ON report_jobs (owner_id);
