#!/usr/bin/env bash
# 게이트 4종을 한 번에 돌리고 **각각의 실행 여부와 exit code 를 따로 남긴다.**
#
# 왜 따로 남기는가. `cd backend && ruff check .` 처럼 묶어 두면 앞 단계가 실패했을 때
# 뒤 명령이 실행되지 않은 채 앞 단계의 exit code 가 최종 결과로 보고된다. 실제로 그
# 값을 lint 실패로 오인할 뻔했다(2026-08-03). **미실행과 실패는 다른 상태다.**
#
# 파이프도 쓰지 않는다. `ruff check . | tail -1` 은 파이프라인 exit code 가 tail 것이라
# ruff 의 1 을 삼킨다(2026-07-30 실측).
#
# 사용법:
#   scripts/gates.sh            # 4종 전부
#   scripts/gates.sh --quick    # 스위트 제외(빠른 확인용) — 완료 선언 근거로 쓰지 말 것
#
# 스위트는 소스 지문까지 검증하므로 완료 선언에는 `--quick` 없이 돌린 결과만 쓴다.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

declare -a NAMES=() STATES=() CODES=()
failed=0

run_gate() {
    local name="$1"; shift
    if [ ! -x "$1" ]; then
        NAMES+=("$name"); STATES+=("NOT_EXECUTABLE"); CODES+=("-")
        failed=1
        return
    fi
    "$@"
    local code=$?
    NAMES+=("$name"); STATES+=("RAN"); CODES+=("$code")
    [ "$code" -eq 0 ] || failed=1
}

run_gate ruff              "$REPO_ROOT/scripts/lint.sh"
run_gate typecheck         "$REPO_ROOT/scripts/typecheck.sh"
run_gate maintained_scripts "$REPO_ROOT/scripts/typecheck_maintained_scripts.sh"
if [ "$QUICK" -eq 1 ]; then
    NAMES+=("suite"); STATES+=("SKIPPED_BY_QUICK"); CODES+=("-")
else
    run_gate suite "$REPO_ROOT/scripts/run_suite.sh"
fi

echo
echo "== GATE RECORD =="
for i in "${!NAMES[@]}"; do
    printf '%-20s state=%-18s exit=%s\n' "${NAMES[$i]}" "${STATES[$i]}" "${CODES[$i]}"
done
# SKIPPED 는 실패가 아니지만 통과도 아니다 — 판정은 호출부가 상태를 보고 한다.
echo "any_gate_failed=$failed"
exit "$failed"
