#!/usr/bin/env bash
# 위험 계수기 validation lease 재검증 (2026-08-04 데굴님 승인 조건 ①·④).
#
# 배경 1: lease는 7일 만료다. 재검증을 손으로 돌리다 `.env`만 로드한 채
# 39표본을 전부 통과시켰으나, HMAC 서명이 dev 기본키라 서버가 그 lease를
# 거부했다(2026-08-04 실측). 서버와 **동일한 방식**으로 env를 로드하는
# 경로를 스크립트로 고정한다 — restart_backend.sh 와 같은 규칙이다.
#
# 배경 2: 환경 가드를 시험하려다 래퍼가 `.env.risk`를 스스로 로드하는 바람에
# 유료 검증이 통째로 실행된 사고가 있었다(2026-08-04). 그래서 **기본 모드는
# preflight(네트워크 호출 0)** 이고, 실제 실행은 `--execute` 를 명시해야 한다.
#
# 사용:
#   ./scripts/revalidate_risk_lease.sh                    # preflight만(기본)
#   ./scripts/revalidate_risk_lease.sh --execute
#   ./scripts/revalidate_risk_lease.sh --execute --repeat 2 --out-dir /tmp/x
#       → 동일 코드 2회 실행. manifest 재감수 전 결정성 확인용
#         (회차별 corpus hash가 모두 같아야 한다).
#
# 종료 코드: 0=합격(또는 preflight OK) / 1=불합격 / 2=env·키·인자 결함
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # 항상 절대 경로 — cwd 비의존
PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/backend/scripts/risk_adapter_shadow_validation.py"
LEASE_DIR="$ROOT/backend/var/risk_state"
ARTIFACT_DIR="$ROOT/backend/compiled/risk_adapter_validation"

EXECUTE=0
REPEAT=1
PASSTHRU=()

log() { printf '[revalidate] %s\n' "$*" >&2; }
fail() { printf '[revalidate][FAIL] %s\n' "$*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --preflight-only) EXECUTE=0; shift ;;
    --repeat) REPEAT="${2:-}"; shift 2 ;;
    *) PASSTHRU+=("$1"); shift ;;
  esac
done
case "$REPEAT" in (''|*[!0-9]*) fail "--repeat 은 양의 정수여야 한다: '$REPEAT'" ;; esac
[ "$REPEAT" -ge 1 ] || fail "--repeat 은 1 이상이어야 한다"

[ -x "$PY" ] || fail "venv python 없음 — $PY"
[ -f "$SCRIPT" ] || fail "검증 스크립트 없음 — $SCRIPT"

# ── env 로드(서버와 동일 규칙: .env → .env.risk → .env.beta) ──────────────
[ -f "$ROOT/.env" ] || fail ".env 없음 — $ROOT/.env"
set -a
. "$ROOT/.env"
[ -f "$ROOT/.env.risk" ] && . "$ROOT/.env.risk"
[ -f "$ROOT/.env.beta" ] && . "$ROOT/.env.beta"
set +a

# 키 존재만 확인한다(유효성 판정은 검증 스크립트가 런타임과 동일 SSOT로
# 수행하고, 부적격이면 외부 호출 전에 exit 2로 끊는다).
[ -n "${RISK_AUDIT_HMAC_KEY_B64:-}" ] || fail "RISK_AUDIT_HMAC_KEY_B64 미설정 — .env.risk 확인(dev 기본키로 서명한 lease는 서버가 거부한다)"
[ -n "${GEMINI_API_KEY:-}" ] || fail "GEMINI_API_KEY 미설정 — .env 확인"

# ── preflight 보고(네트워크 호출 0) ──────────────────────────────────────
KEY_FP="$(printf '%s' "$RISK_AUDIT_HMAC_KEY_B64" | sha256sum | cut -c1-16)"
env_fp() { [ -f "$1" ] && sha256sum "$1" | cut -c1-16 || echo "-"; }
cat >&2 <<EOF
[revalidate] ── preflight ─────────────────────────────────────────────
  env 로드          : .env$([ -f "$ROOT/.env.risk" ] && printf ' .env.risk')$([ -f "$ROOT/.env.beta" ] && printf ' .env.beta')
  .env fingerprint  : $(env_fp "$ROOT/.env")
  .env.risk         : $(env_fp "$ROOT/.env.risk")
  HMAC key fp       : $KEY_FP (값 미출력)
  model / provider  : ${SAJU_READING_MODEL:-gemini-3-flash-preview} / gemini
  git HEAD          : $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '-')
  script fingerprint: $(env_fp "$SCRIPT")
  out-dir           : ${PASSTHRU[*]:-<기본: backend/compiled/risk_adapter_validation>}
  예상 표본         : native 39 (13형×3) + rerouting 3
  repeat            : $REPEAT
  production lease  : $LEASE_DIR (실행 시 **덮어씀** — 합격한 회차만)
  production artifact: $ARTIFACT_DIR ($(ls -1 "$ARTIFACT_DIR" 2>/dev/null | wc -l)개, --out-dir 지정 시 미변경)
EOF

if [ "$EXECUTE" != "1" ]; then
  log "preflight 전용 모드 — 네트워크 호출 없이 종료(--execute 로 실행)"
  exit 0
fi

# ── 실행 ─────────────────────────────────────────────────────────────────
STATUS=0
for i in $(seq 1 "$REPEAT"); do
  [ "$REPEAT" -gt 1 ] && log "run $i/$REPEAT"
  if "$PY" "$SCRIPT" ${PASSTHRU[@]+"${PASSTHRU[@]}"}; then
    log "run $i: 합격"
  else
    STATUS=$?
    log "run $i: 불합격(exit=$STATUS)"
    [ "$STATUS" = "2" ] && exit 2   # env·키 결함은 반복하지 않는다
  fi
done
exit "$STATUS"
