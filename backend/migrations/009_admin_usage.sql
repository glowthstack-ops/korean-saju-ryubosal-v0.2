-- v2.2 운영 관리자 콘솔 Phase A — LLM 사용량·비용 영속 로깅 + 관리자 등록 단가/환율 + admin 플래그.
-- 기존 in-memory COST_LEDGER는 재시작 시 소실되어 쿼리·집계가 불가 → 호출별 영속 로그를 둔다.
-- 단가(model_pricing)·환율(admin_settings)은 관리자가 페이지에서 직접 등록·변경한다(가격 변동 대응).

-- 호출 1건당 사용량·비용(로그 시점 단가 스냅샷). 일자/상품/모델/사용자별 집계·BI 토대.
CREATE TABLE IF NOT EXISTS llm_usage (
  id            BIGSERIAL PRIMARY KEY,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  owner_id      TEXT,                                  -- 로그인 사용자(NULL=익명/시스템)
  surface       TEXT NOT NULL,                         -- 'chat' | 'report'
  product_code  TEXT,                                  -- CHAT / RPT_YEAR / RPT_FOCUS / RPT_FULL
  call_type     TEXT,                                  -- chat_single / report_focus_section ...
  model         TEXT NOT NULL,
  provider      TEXT NOT NULL,                         -- gemini | openai
  is_fallback   BOOLEAN NOT NULL DEFAULT false,        -- 폴백(비상) 호출 여부
  input_tokens  INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  cached_tokens INT NOT NULL DEFAULT 0,
  cost_usd      NUMERIC(12,6) NOT NULL DEFAULT 0,      -- 로그 시점 단가로 계산한 스냅샷
  ref_id        TEXT                                   -- job_id / thread_id(추적용)
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage (created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_surface ON llm_usage (surface, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_owner ON llm_usage (owner_id, created_at);

-- 관리자 등록 모델 단가(USD / 1M tokens). model_prices.json 대체 — 운영 중 변경 가능.
CREATE TABLE IF NOT EXISTS model_pricing (
  model          TEXT PRIMARY KEY,
  input_per_1m   NUMERIC(12,4) NOT NULL DEFAULT 0,     -- USD / 1M input tokens
  output_per_1m  NUMERIC(12,4) NOT NULL DEFAULT 0,
  cached_per_1m  NUMERIC(12,4) NOT NULL DEFAULT 0,     -- 캐시된 입력 토큰 단가(할인)
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by     TEXT
);

-- 관리자 전역 설정(환율 등) — key/value.
CREATE TABLE IF NOT EXISTS admin_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 관리자 권한 플래그(ID+PIN 계정에 부여). 운영 콘솔 접근 제어.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;
