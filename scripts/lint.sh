#!/usr/bin/env bash
# ruff 게이트 실행 SSOT.
#
# 다른 게이트(typecheck.sh · typecheck_maintained_scripts.sh · run_suite.sh)는 모두
# 저장소 루트를 스스로 확정하는데 ruff 만 스크립트가 없어 `cd backend && ruff check .`
# 로 돌았다. 그러다 **호출자가 이미 backend 에 있으면 `cd` 가 실패하고, `&&` 때문에
# ruff 는 실행조차 되지 않은 채 `cd` 의 exit code 1 이 lint 실패로 보고됐다**
# (2026-08-03 실측). 통과 실패가 아니라 미실행이었다.
#
# 검사 범위는 backend/pyproject.toml 의 [tool.ruff] 가 정한다. 저장소 루트에서 돌리면
# doc/ 하위 기존 부채까지 걸리므로 게이트 범위는 backend 로 고정한다.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

exec python -m ruff check "$@" .
