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

log() { printf '[ollama] %s\n' "$*" >&2; }

if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi

if [ "${SAJU_QUESTION_FRAME_SHADOW:-0}" != "1" ] && [ "${SAJU_QUESTION_FRAME_GATE:-0}" != "1" ]; then
  log "질문 이해 층 OFF(SAJU_QUESTION_FRAME_SHADOW/GATE 모두 미설정) — Ollama 기동 생략"
  exit 0
fi

BASE_URL="${SAJU_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
BASE_URL="${BASE_URL%/}"
HOSTPORT="${BASE_URL#http://}"; HOSTPORT="${HOSTPORT#https://}"
MODEL="$("$ROOT/.venv/bin/python" - <<'PY' 2>/dev/null || echo gemma4:e2b
import json, pathlib
cfg = json.loads((pathlib.Path("backend/config/llm_config.json")).read_text("utf-8"))
print(cfg["question_frame"]["model"])
PY
)"

alive() { curl -s -m 2 "$BASE_URL/api/tags" >/dev/null 2>&1; }

if ! command -v ollama >/dev/null 2>&1; then
  log "ollama 미설치 — 질문 이해 층은 룰만으로 동작한다. 설치: curl -fsSL https://ollama.com/install.sh | sh"
  exit 0
fi

if alive; then
  log "서버 응답 확인 $BASE_URL"
else
  if systemctl is-active --quiet ollama 2>/dev/null; then
    log "systemd ollama.service 가 활성이지만 $BASE_URL 에 응답하지 않는다 — 유닛 포트가 다르거나 bind 실패 루프"
    log "  (WSL2: netsh.exe interface ipv4 show excludedportrange protocol=tcp 로 예약 포트 확인)"
  fi
  mkdir -p "$(dirname "$LOG")"
  log "사용자 레벨 기동: OLLAMA_HOST=$HOSTPORT → $LOG"
  OLLAMA_HOST="$HOSTPORT" nohup setsid ollama serve >>"$LOG" 2>&1 < /dev/null &
  for _ in $(seq 1 "$START_WAIT"); do
    alive && break
    sleep 1
  done
  if ! alive; then
    log "기동 실패($START_WAIT s) — $LOG 확인. 백엔드는 룰만으로 계속 기동한다."
    exit 0
  fi
  log "서버 기동 확인 $BASE_URL"
fi

if curl -s -m 5 "$BASE_URL/api/tags" | grep -q "\"name\":\"$MODEL\""; then
  log "모델 준비됨 $MODEL"
else
  log "모델 내려받기 $MODEL (최초 1회, 수 GB)"
  OLLAMA_HOST="$HOSTPORT" ollama pull "$MODEL" >>"$LOG" 2>&1 \
    && log "모델 준비됨 $MODEL" \
    || log "모델 내려받기 실패 — $LOG 확인. 백엔드는 룰만으로 계속 기동한다."
fi
exit 0
