-- 010: 시스템 에러 중앙 적재 (운영 콘솔 — 에러 모니터링).
-- 미처리 5xx(http)·LLM 호출 실패(llm)·리포트 잡 실패(report_job)·백그라운드(background)를 한 곳에 모은다.
-- fingerprint(출처+종류+정규화 메시지)로 유사 에러를 묶어 빈도·미해결 여부를 본다.
-- resolved_at NULL=미해결. 기록은 best-effort(모니터링이 본 기능을 깨지 않도록 호출 측에서 예외를 삼킨다).

CREATE TABLE IF NOT EXISTS system_errors (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL,                       -- http | llm | report_job | background
    severity    TEXT NOT NULL DEFAULT 'error'
                CHECK (severity IN ('error', 'warning')),
    kind        TEXT NOT NULL,                       -- 예외 클래스명 또는 짧은 코드
    message     TEXT NOT NULL,                       -- 사람이 읽는 오류 메시지
    detail      TEXT,                                -- 스택트레이스/추가 정보
    path        TEXT,                                -- 요청 경로(METHOD /path) 또는 컨텍스트
    owner_id    TEXT,                                -- 관련 사용자(있으면)
    ref_id      TEXT,                                -- job_id/thread_id 등 추적 키
    fingerprint TEXT NOT NULL,                       -- 묶음 키(source+kind+정규화 메시지 해시)
    resolved_at TIMESTAMPTZ                          -- 확인/해결 시각(NULL=미해결)
);

CREATE INDEX IF NOT EXISTS idx_system_errors_created ON system_errors (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_errors_fp ON system_errors (fingerprint);
CREATE INDEX IF NOT EXISTS idx_system_errors_unresolved
    ON system_errors (created_at DESC) WHERE resolved_at IS NULL;
