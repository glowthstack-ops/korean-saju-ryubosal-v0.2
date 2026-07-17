#!/usr/bin/env bash
# 개발 서버 동시 실행: 백엔드(FastAPI:8000) + 프론트(Next:3000).
# 사용: ./scripts/dev.sh   (Ctrl+C 로 둘 다 종료)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv/bin"
API_PORT="${API_PORT:-8000}"

# .env 자동 로드 — SAJU_V2_DATABASE_URL(DB DSN)·LLM 키가 환경에 없으면
# 백엔드가 DSN 없이 떠서 모든 DB 엔드포인트(auth/subjects/report 등)가 503이 된다.
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi
# 위험 노출 베타 활성화 값(.env.risk — gitignore): pytest가 읽지 않도록
# .env와 분리, 서버 기동 시에만 주입된다. 파일 부재=위험 기능 전부 잠금.
if [ -f "$ROOT/.env.risk" ]; then
  set -a; . "$ROOT/.env.risk"; set +a
fi
if [ -z "${SAJU_V2_DATABASE_URL:-}" ]; then
  echo "[warn] SAJU_V2_DATABASE_URL 미설정 — DB 엔드포인트가 503을 반환한다. .env 확인 필요." >&2
fi

if [ ! -x "$VENV/uvicorn" ]; then
  echo "[setup] backend editable install…"
  "$VENV/pip" install -e "$ROOT/backend[dev]" >/dev/null
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "[setup] frontend npm install…"
  (cd "$ROOT/frontend" && npm install)
fi

echo "[run] backend  → http://localhost:$API_PORT"
"$VENV/uvicorn" saju_api.main:app --reload --port "$API_PORT" &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT INT TERM

echo "[run] frontend → http://localhost:3000"
cd "$ROOT/frontend"
# 기본 연결 = 상대경로 /api (next.config rewrite가 백엔드로 프록시 → same-origin·CORS 불필요).
# NEXT_PUBLIC_API_BASE는 비워 상대 /api를 쓰고, 프록시 목적지만 SAJU_BACKEND_URL로 지정한다.
SAJU_BACKEND_URL="http://localhost:$API_PORT" npm run dev
