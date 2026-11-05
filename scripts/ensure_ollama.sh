#!/usr/bin/env bash
# 질문 이해 층(docs/03 B6) 로컬 소형 모델 서버(Ollama) 보장 — 서버 기동 절차의 한 단계.
#
# 백엔드는 Ollama 없이도 정상 기동한다(프레임 호출 실패 = 관측 1건, 룰만 동작 — 절대 원칙 11).
# 다만 색·방향·음식·장소·행동 가부의 Q1 폴백 보정(게이트)이 멈추므로, dev.sh / restart_backend.sh 가
# 백엔드를 띄우기 전에 이 스크립트를 호출한다. **실패해도 백엔드 기동을 막지 않는다**(exit 0).
#
# 하는 일(멱등):
#   1. .env 의 SAJU_QUESTION_FRAME_SHADOW / SAJU_QUESTION_FRAME_GATE 둘 다 꺼져 있으면 no-op
#   2. SAJU_OLLAMA_BASE_URL(기본 http://127.0.0.1:11434) 이 응답하면 통과
#      — WSL2 는 11434 가 Windows 예약 포트 범위(11368–11467)일 수 있어 .env 에서 포트를 바꾼다(실측 11500)
#   3. 응답이 없으면 사용자 레벨 `ollama serve` 를 그 주소로 기동(nohup setsid, 로그 var/ollama.log)
#      — systemd 유닛(ollama.service)이 같은 포트로 살아 있으면 그쪽을 쓴다
#   3b. 지정 포트가 bind 불가(Windows 예약 범위는 재부팅마다 옮겨 다닌다 — 2026-11-05 실측 11471–11570 에
#      11500 이 들어가 `bind: address already in use`)면 **이 케이스에 한해** 후보 포트
#      (SAJU_OLLAMA_FALLBACK_PORTS, 기본 11700 11800 11900 12100)를 차례로 시도한다(데굴님 승인).
#      .env 는 건드리지 않고, 실제 쓰는 주소를 var/ollama_base_url 에 적는다 — dev.sh / restart_backend.sh 가
#      .env 로드 뒤 이 파일로 SAJU_OLLAMA_BASE_URL 을 덮어써 백엔드에 넘긴다. 파일은 매 실행 시 지우고
#      성공했을 때만 다시 쓴다(no-op·미설치·전부 실패 = 파일 없음 = .env 값 그대로).
#   4. llm_config.json question_frame.model 이 없으면 `ollama pull`
#
# 영구화(선택, sudo 필요 — 데굴님 작업): sudo systemctl edit ollama →
#   [Service]
#   Environment=OLLAMA_HOST=127.0.0.1:11500
#
# 사용: ./scripts/ensure_ollama.sh            (단독 실행 가능)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${OLLAMA_LOG:-$ROOT/var/ollama.log}"
START_WAIT="${OLLAMA_START_WAIT:-60}"
#: 실제 사용 주소 기록(폴백 시 .env 와 달라진다) — 기동 스크립트가 읽는다.
STATE_FILE="$ROOT/var/ollama_base_url"
PY="$ROOT/.venv/bin/python"

log() { printf '[ollama] %s\n' "$*" >&2; }

# 지난 실행의 기록은 지운다 — 이번 실행이 성공한 주소만 남긴다.
rm -f "$STATE_FILE"

if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi

if [ "${SAJU_QUESTION_FRAME_SHADOW:-0}" != "1" ] && [ "${SAJU_QUESTION_FRAME_GATE:-0}" != "1" ]; then
  log "질문 이해 층 OFF(SAJU_QUESTION_FRAME_SHADOW/GATE 모두 미설정) — Ollama 기동 생략"
  exit 0
fi

CONFIGURED_URL="${SAJU_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
CONFIGURED_URL="${CONFIGURED_URL%/}"
HOSTPORT="${CONFIGURED_URL#http://}"; HOSTPORT="${HOSTPORT#https://}"
HOST="${HOSTPORT%%:*}"
FALLBACK_PORTS="${SAJU_OLLAMA_FALLBACK_PORTS:-11700 11800 11900 12100}"
MODEL="$("$PY" - <<'PY' 2>/dev/null || echo gemma4:e2b
import json, pathlib
cfg = json.loads((pathlib.Path("backend/config/llm_config.json")).read_text("utf-8"))
print(cfg["question_frame"]["model"])
PY
)"

alive() { curl -s -m 2 "$1/api/tags" >/dev/null 2>&1; }
# bind 가능 여부 — `ss` 에 리스너가 없어도 Windows 예약 범위면 EADDRINUSE 가 난다. 실제 bind 로 확인한다.
bindable() {
  "$PY" - "$1" "$2" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}
# 그 주소로 사용자 레벨 서버를 띄우고 응답을 기다린다 → 0=응답 확인.
start_serve() {
  local hostport="$1" url="$2"
  mkdir -p "$(dirname "$LOG")"
  log "사용자 레벨 기동: OLLAMA_HOST=$hostport → $LOG"
  OLLAMA_HOST="$hostport" nohup setsid ollama serve >>"$LOG" 2>&1 < /dev/null &
  for _ in $(seq 1 "$START_WAIT"); do
    alive "$url" && return 0
    sleep 1
  done
  return 1
}

if ! command -v ollama >/dev/null 2>&1; then
  log "ollama 미설치 — 질문 이해 층은 룰만으로 동작한다. 설치: curl -fsSL https://ollama.com/install.sh | sh"
  exit 0
fi

BASE_URL=""
if alive "$CONFIGURED_URL"; then
  BASE_URL="$CONFIGURED_URL"
  log "서버 응답 확인 $BASE_URL"
else
  if systemctl is-active --quiet ollama 2>/dev/null; then
    log "systemd ollama.service 가 활성이지만 $CONFIGURED_URL 에 응답하지 않는다 — 유닛 포트가 다르거나 bind 실패 루프"
    log "  (WSL2: netsh.exe interface ipv4 show excludedportrange protocol=tcp 로 예약 포트 확인)"
  fi
  if bindable "$HOST" "${HOSTPORT##*:}"; then
    if start_serve "$HOSTPORT" "$CONFIGURED_URL"; then
      BASE_URL="$CONFIGURED_URL"
      log "서버 기동 확인 $BASE_URL"
    else
      log "기동 실패($START_WAIT s) $CONFIGURED_URL — $LOG 확인"
    fi
  else
    log "$HOSTPORT 는 bind 불가(점유 또는 Windows 예약 포트) — 임시 포트 폴백 시도: $FALLBACK_PORTS"
  fi
  # 3b. 지정 포트가 안 되는 케이스에 한해 후보 포트를 차례로 — 이미 떠 있으면 그대로 쓴다.
  if [ -z "$BASE_URL" ]; then
    for port in $FALLBACK_PORTS; do
      url="http://$HOST:$port"
      if alive "$url"; then
        BASE_URL="$url"; log "임시 포트 서버 응답 확인 $BASE_URL"; break
      fi
      if ! bindable "$HOST" "$port"; then
        log "$HOST:$port bind 불가 — 다음 후보"; continue
      fi
      if start_serve "$HOST:$port" "$url"; then
        BASE_URL="$url"; log "임시 포트 서버 기동 확인 $BASE_URL"; break
      fi
      log "$url 기동 실패 — 다음 후보"
    done
  fi
  if [ -z "$BASE_URL" ]; then
    log "지정 포트·후보 포트 모두 실패 — $LOG 확인. 백엔드는 룰만으로 계속 기동한다."
    exit 0
  fi
  if [ "$BASE_URL" != "$CONFIGURED_URL" ]; then
    log "임시 포트 사용 $BASE_URL (.env 의 $CONFIGURED_URL 은 그대로 — 재부팅 후 예약 범위를 다시 확인한다)"
  fi
fi
HOSTPORT="${BASE_URL#http://}"; HOSTPORT="${HOSTPORT#https://}"

if curl -s -m 5 "$BASE_URL/api/tags" | grep -q "\"name\":\"$MODEL\""; then
  log "모델 준비됨 $MODEL"
else
  log "모델 내려받기 $MODEL (최초 1회, 수 GB)"
  OLLAMA_HOST="$HOSTPORT" ollama pull "$MODEL" >>"$LOG" 2>&1 \
    && log "모델 준비됨 $MODEL" \
    || log "모델 내려받기 실패 — $LOG 확인. 백엔드는 룰만으로 계속 기동한다."
fi

# 실제 사용 주소를 기록 — dev.sh / restart_backend.sh 가 .env 로드 뒤 이 값으로 덮어쓴다.
mkdir -p "$(dirname "$STATE_FILE")"
printf '%s\n' "$BASE_URL" >"$STATE_FILE"
exit 0
