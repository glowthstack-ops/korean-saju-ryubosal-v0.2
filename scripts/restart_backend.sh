#!/usr/bin/env bash
# 백엔드 안전 재기동 (P0.5 — 2026-07-27 데굴님 지시).
#
# 배경: 플래그 적용 재기동 중 두 차례 서비스가 내려갔다. 원인은 ①pkill 직후 포트가
# 해제되기 전에 새 프로세스가 바인딩을 시도 ②셸 cwd가 backend/로 바뀐 상태에서
# `. ./.env` 상대 경로를 써서 환경변수 미로드. 실사용 중인 서비스이므로 재기동을
# 손으로 하지 않고 이 스크립트로 고정한다.
#
# 절차: env 확인 → 설정 검증 → graceful stop → 포트 해제 대기 → 기동 →
#       내부 health → 터널 health → 실패 시 복구 안내.
#
# 사용:
#   ./scripts/restart_backend.sh                      # 내부 health까지 확인
#   TUNNEL_URL=https://xxx.trycloudflare.com ./scripts/restart_backend.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # 항상 절대 경로 — cwd에 의존하지 않는다
API_PORT="${API_PORT:-8000}"
API_HOST="${API_HOST:-127.0.0.1}"
LOG="${BACKEND_LOG:-$ROOT/var/backend.log}"
STOP_WAIT="${STOP_WAIT:-30}"      # graceful stop 최대 대기(초)
START_WAIT="${START_WAIT:-60}"    # health 200 최대 대기(초)
PATTERN="uvicorn saju_api.main:app"

log() { printf '[restart] %s\n' "$*" >&2; }
fail() { printf '[restart][FAIL] %s\n' "$*" >&2; exit 1; }

# ── 1. env 파일 존재 확인(절대 경로) ────────────────────────────────────────
[ -f "$ROOT/.env" ] || fail ".env 없음 — $ROOT/.env"
log "env 로드: .env$([ -f "$ROOT/.env.risk" ] && printf ' .env.risk')$([ -f "$ROOT/.env.beta" ] && printf ' .env.beta')"
set -a
. "$ROOT/.env"
[ -f "$ROOT/.env.risk" ] && . "$ROOT/.env.risk"
[ -f "$ROOT/.env.beta" ] && . "$ROOT/.env.beta"
set +a
[ -n "${SAJU_V2_DATABASE_URL:-}" ] || fail "SAJU_V2_DATABASE_URL 미설정 — DB 엔드포인트가 503이 된다"

# ── 2. 설정 검증(기동 전에 무효 플래그 조합을 걸러낸다) ──────────────────────
"$ROOT/.venv/bin/python" - <<'PY' || fail "플래그 조합 검증 실패 — 기동 중단(기존 프로세스 유지)"
import sys
try:
    from saju_engines import period_v2_config as c
    c.validate_flags()
    print("[restart] 활성 설정: " + " ".join(
        f"{k}={v}" for k, v in c.active_versions().items() if isinstance(v, bool)
    ), file=sys.stderr)
except Exception as exc:  # noqa: BLE001
    print(f"[restart] {exc}", file=sys.stderr)
    sys.exit(1)
PY

# ── 3. graceful stop ────────────────────────────────────────────────────────
PIDS="$(pgrep -f "$PATTERN" || true)"
if [ -n "$PIDS" ]; then
  log "graceful stop: $PIDS"
  # shellcheck disable=SC2086
  kill -TERM $PIDS 2>/dev/null || true
  for _ in $(seq 1 "$STOP_WAIT"); do
    pgrep -f "$PATTERN" >/dev/null || break
    sleep 1
  done
  if pgrep -f "$PATTERN" >/dev/null; then
    log "graceful stop 실패 → SIGKILL"
    pkill -KILL -f "$PATTERN" || true
    sleep 1
  fi
else
  log "기존 프로세스 없음"
fi

# ── 4. 포트 해제 대기(즉시 기동하면 바인딩에 실패한다) ───────────────────────
for _ in $(seq 1 "$STOP_WAIT"); do
  ss -ltn 2>/dev/null | grep -q ":$API_PORT " || break
  sleep 1
done
ss -ltn 2>/dev/null | grep -q ":$API_PORT " && fail "포트 $API_PORT 해제되지 않음 — 기동 중단"
log "포트 $API_PORT 해제 확인"

# ── 5. 기동 ─────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$LOG")"
nohup "$ROOT/.venv/bin/uvicorn" saju_api.main:app \
  --port "$API_PORT" --host "$API_HOST" >>"$LOG" 2>&1 &
NEW_PID=$!
log "기동 pid=$NEW_PID log=$LOG"

# ── 6. 내부 health ──────────────────────────────────────────────────────────
CODE=000
for _ in $(seq 1 "$START_WAIT"); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://$API_HOST:$API_PORT/health" || echo 000)"
  [ "$CODE" = "200" ] && break
  kill -0 "$NEW_PID" 2>/dev/null || fail "프로세스가 죽었다 — $LOG 확인"
  sleep 1
done
[ "$CODE" = "200" ] || fail "내부 health 실패(code=$CODE) — $LOG 확인"
log "내부 health 200"
curl -s "http://$API_HOST:$API_PORT/health" | "$ROOT/.venv/bin/python" -c \
  'import json,sys; d=json.load(sys.stdin); print("[restart] beta_flags: " + json.dumps(d.get("beta_flags", {}), ensure_ascii=False))' >&2

# ── 7. 터널 health(선택) ────────────────────────────────────────────────────
if [ -n "${TUNNEL_URL:-}" ]; then
  TCODE="$(curl -s -o /dev/null -w '%{http_code}' "$TUNNEL_URL/api/v2/calendar/2026/7" || echo 000)"
  [ "$TCODE" = "200" ] || fail "터널 health 실패(code=$TCODE) — 백엔드는 살아 있으니 터널 확인 필요"
  log "터널 health 200"
fi

log "완료"
