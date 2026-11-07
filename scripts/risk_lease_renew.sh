#!/usr/bin/env bash
# 위험 계수기 validation lease 자동 갱신 — cron 전용 래퍼 (2026-11-07 데굴님 "주간 재검증 cron을 등록해줘").
#
# 배경: lease는 7일 만료다. 2026-08-21 재검증 뒤 71일간 방치돼 기동마다
# UNVALIDATED(BYPASS) → 위험 블록 전부 미주입이었다(WORKLOG 2026-11-07).
#
# 단순히 revalidate_risk_lease.sh --execute 를 cron에 거는 것은 두 가지 사고를 만든다.
#   ① 코드 변경으로 위험 블록 본문이 바뀌면 corpus hash가 달라져 운영 artifact 디렉터리에
#      같은 모델 artifact가 2개 생긴다 → 부팅 시 fail-closed(BYPASS).
#   ② 그 lease는 identity(corpus hash 포함)가 manifest 승격본과 달라 부팅 시 IDENTITY_MISMATCH
#      → UNVALIDATED. 아직 유효한 기존 lease까지 덮어써 버린다.
# 그래서 이 래퍼는 artifact를 격리 디렉터리(--out-dir)에만 쓰고, 합격 후 corpus hash를
# manifest의 reviewed 항목과 대조해 같을 때만 새 lease를 인정한다. 다르면 기존 lease를
# 복원하고 CORPUS_DRIFT 로 크게 남긴다(승격은 사람 몫 — WORKLOG 2026-11-07 절차).
#
# 실행 주기: 매일 1회 호출돼도 lease 잔여가 --max-remaining-hours(기본 72h) 이상이면
# 외부 호출 없이 SKIP 한다 → 실제 재검증은 약 4일마다, 실패해도 만료 전 3일간 재시도.
#
# 사용:
#   ./scripts/risk_lease_renew.sh                   # 잔여 72h 미만일 때만 재검증
#   ./scripts/risk_lease_renew.sh --force           # 잔여와 무관하게 재검증
#   ./scripts/risk_lease_renew.sh --dry-run         # 판정만(외부 호출·파일 변경 0)
#   ./scripts/risk_lease_renew.sh --post-check-only <stage_dir>
#                                                   # 격리 디렉터리의 결과로 대조·복원 단계만(테스트용)
#
# 종료 코드: 0=갱신 또는 SKIP / 1=재검증 불합격·drift(기존 lease 복원) / 2=환경 결함
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
MODEL="${SAJU_READING_MODEL:-gemini-3-flash-preview}"
LEASE="$ROOT/backend/var/risk_state/validation_lease__${MODEL}.json"
MANIFEST="$ROOT/doc/v2_2/RISK_REVIEW_MANIFEST.json"
STAGE_ROOT="$ROOT/backend/var/risk_state/revalidation_stage"
LOCK="$ROOT/backend/var/risk_state/.risk_lease_renew.lock"
HEALTH_URL="http://127.0.0.1:${API_PORT:-8000}/health"
MAX_REMAINING_HOURS=72
FORCE=0
DRY_RUN=0
POST_CHECK_ONLY=""

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s [risk_lease_renew] %s\n' "$(ts)" "$*"; }
fail() { printf '%s [risk_lease_renew][FAIL] %s\n' "$(ts)" "$*"; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --max-remaining-hours) MAX_REMAINING_HOURS="${2:-}"; shift 2 ;;
    --post-check-only) POST_CHECK_ONLY="${2:-}"; shift 2 ;;
    *) fail "알 수 없는 인자: $1" ;;
  esac
done
case "$MAX_REMAINING_HOURS" in (''|*[!0-9]*) fail "--max-remaining-hours 는 정수여야 한다" ;; esac
[ -x "$PY" ] || fail "venv python 없음 — $PY"
[ -f "$MANIFEST" ] || fail "manifest 없음 — $MANIFEST"
mkdir -p "$(dirname "$LOCK")"

# ── 보조: lease 잔여 시간(h, 정수) — 부재·손상·만료는 0 ───────────────────
lease_remaining_hours() {
  "$PY" - "$LEASE" <<'EOF'
import json, sys
from datetime import UTC, datetime
try:
    body = json.load(open(sys.argv[1], encoding="utf-8"))["body"]
    exp = datetime.fromisoformat(body["validation_expires_at"])
    print(max(0, int((exp - datetime.now(UTC)).total_seconds() // 3600)))
except Exception:  # noqa: BLE001 — 부재·손상=0(즉시 갱신 대상)
    print(0)
EOF
}

# ── 보조: manifest 의 reviewed corpus hash(해당 모델) ─────────────────────
manifest_reviewed_hash() {
  "$PY" - "$MANIFEST" "$MODEL" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
for e in m["expose_pipeline"].get("validatedTokenCounters", []):
    if e.get("resolvedModelId") == sys.argv[2] and e.get("reviewed") is True:
        print(e["validationCorpusHash"]); break
EOF
}

# ── 보조: 격리 디렉터리 artifact 의 corpus hash ────────────────────────────
staged_hash() {
  local f
  f="$(ls -1t "$1"/"${MODEL}"__*.json 2>/dev/null | head -1)"
  [ -n "$f" ] || return 1
  "$PY" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["validationCorpusHash"])' "$f"
}

# ── 보조: 합격 후 대조·복원 (exit 0=갱신 인정 / 1=drift·복원) ──────────────
post_check() {
  local stage="$1" backup="$2" new reviewed
  reviewed="$(manifest_reviewed_hash)"
  [ -n "$reviewed" ] || { restore_lease "$backup"; log "ERROR MANIFEST_REVIEWED_MISSING model=$MODEL — 기존 lease 복원"; return 1; }
  new="$(staged_hash "$stage")" || { restore_lease "$backup"; log "ERROR STAGED_ARTIFACT_MISSING stage=$stage — 기존 lease 복원"; return 1; }
  if [ "$new" != "$reviewed" ]; then
    restore_lease "$backup"
    log "ERROR CORPUS_DRIFT new=${new:0:16} reviewed=${reviewed:0:16} — 위험 블록 본문이 바뀌어 자동 갱신 불가. 기존 lease 복원. 승격 절차(allowlist 교체→manifest 재생성→구 artifact 삭제, WORKLOG 2026-11-07) 필요. staged=$stage"
    return 1
  fi
  log "RENEWED corpus=${new:0:16} expires_in_h=$(lease_remaining_hours) stage=$stage"
  return 0
}

restore_lease() {
  local backup="$1"
  if [ -n "$backup" ] && [ -f "$backup" ]; then
    cp -f "$backup" "$LEASE"
    log "기존 lease 복원(잔여 $(lease_remaining_hours)h)"
  else
    rm -f "$LEASE"
    log "복원할 기존 lease 없음 — 불일치 lease 제거"
  fi
}

# ── 테스트 진입: 대조·복원 단계만 ─────────────────────────────────────────
if [ -n "$POST_CHECK_ONLY" ]; then
  [ -d "$POST_CHECK_ONLY" ] || fail "stage 디렉터리 없음 — $POST_CHECK_ONLY"
  BACKUP=""
  [ -f "$LEASE" ] && { BACKUP="$(mktemp)"; cp -f "$LEASE" "$BACKUP"; }
  post_check "$POST_CHECK_ONLY" "$BACKUP"; RC=$?
  [ -n "$BACKUP" ] && rm -f "$BACKUP"
  exit "$RC"
fi

# ── 1) 잔여 판정 ──────────────────────────────────────────────────────────
REMAIN="$(lease_remaining_hours)"
if [ "$FORCE" != "1" ] && [ "$REMAIN" -ge "$MAX_REMAINING_HOURS" ]; then
  log "SKIP lease 잔여 ${REMAIN}h ≥ ${MAX_REMAINING_HOURS}h (model=$MODEL)"
  exit 0
fi
log "RUN lease 잔여 ${REMAIN}h < ${MAX_REMAINING_HOURS}h (force=$FORCE model=$MODEL)"
if [ "$DRY_RUN" = "1" ]; then
  log "DRY_RUN — 재검증 실행 생략(reviewed=$(manifest_reviewed_hash | cut -c1-16))"
  exit 0
fi

# ── 2) 단일 실행 잠금 + 기존 lease 백업 + 격리 디렉터리 ────────────────────
exec 9>"$LOCK"
flock -n 9 || { log "SKIP 다른 갱신이 실행 중"; exit 0; }
STAGE="$STAGE_ROOT/$(date +%Y%m%dT%H%M%S)"
mkdir -p "$STAGE"
BACKUP=""
[ -f "$LEASE" ] && { BACKUP="$STAGE/lease.before.json"; cp -f "$LEASE" "$BACKUP"; }

# ── 3) 재검증(유료 호출) — artifact 는 격리 디렉터리, lease 는 합격 시 기록 ──
"$ROOT/scripts/revalidate_risk_lease.sh" --execute --out-dir "$STAGE" >"$STAGE/run.log" 2>&1
RC=$?
if [ "$RC" != "0" ]; then
  restore_lease "$BACKUP"
  log "ERROR REVALIDATION_FAILED exit=$RC — 내일 재시도. 로그: $STAGE/run.log"
  tail -5 "$STAGE/run.log" | sed 's/^/    /'
  exit 1
fi

# ── 4) 대조·복원 ──────────────────────────────────────────────────────────
post_check "$STAGE" "$BACKUP" || exit 1

# ── 5) 오래된 격리 디렉터리 정리(최근 6개 유지) + 서버 상태 참고 출력 ───────
ls -1dt "$STAGE_ROOT"/*/ 2>/dev/null | tail -n +7 | xargs -r rm -rf
if curl -s -m 5 "$HEALTH_URL" >/dev/null 2>&1; then
  log "server $(curl -s -m 5 "$HEALTH_URL" | "$PY" -c 'import json,sys;d=json.load(sys.stdin);print("validation=%s lease_expires_at=%s"%(d.get("risk_token_counter_validation"),d.get("risk_token_counter_lease_expires_at")))' 2>/dev/null || echo 'health 파싱 실패')"
  log "주의: 실행 중인 서버는 기동 시점 lease 로 VALIDATED 를 유지한다. 새 lease 는 다음 재기동부터 적용되며 재기동은 필요 없다."
fi
exit 0
