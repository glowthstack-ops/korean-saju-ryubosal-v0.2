#!/usr/bin/env bash
# Production 타입 게이트 실행 SSOT (2026-07-30 데굴님 확정).
#
# 검사 **범위**는 backend/pyproject.toml 의 [tool.mypy] packages 가 정한다.
# 이 스크립트는 실행 방식만 고정한다 — CI 와 문서가 패키지 경로를 각자 나열하면
# drift 가 생기고, 실제로 그런 상태에서 `mypy .` 가 실패하는데도 게이트가 통과한
# 것처럼 보고된 적이 있다(2026-07-30).
#
# tests/ 와 scripts/ 는 blocking 대상이 아니다. 전 트리 진단은 다음으로 따로 돈다.
#   cd backend && python -m mypy --no-incremental .
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

exec python -m mypy --no-incremental
