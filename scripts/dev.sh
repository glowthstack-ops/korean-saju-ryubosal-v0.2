#!/usr/bin/env bash
# 개발 서버 동시 실행: 백엔드(FastAPI:8000) + 프론트(Next:3000).
# 사용: ./scripts/dev.sh   (Ctrl+C 로 둘 다 종료)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv/bin"
API_PORT="${API_PORT:-8000}"

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
NEXT_PUBLIC_API_BASE="http://localhost:$API_PORT" npm run dev
