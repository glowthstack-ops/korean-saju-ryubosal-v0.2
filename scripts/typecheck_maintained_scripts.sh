#!/usr/bin/env bash
# 유지 대상 스크립트 타입 게이트 — allowlist 만 blocking.
#
# `backend/scripts/` 전체는 283건의 기존 부채를 안고 있고, 그 98%가 감사·포렌식
# 스크립트다. 측정 결과가 커밋 메시지와 판정 상태명으로 이미 동결돼 있어 재실행 수요가
# 낮고, production mypy gate 범위(`[tool.mypy] packages`)에도 CI 실행 경로에도 없다.
# 그래서 전량 정리는 추진하지 않는다.
#
# 대신 **실제로 다시 실행할 스크립트만** 여기서 0건으로 지킨다. 목록에 넣는 기준:
#
#   운영 smoke 에 사용
#   설계 변경 전후를 같은 모집단으로 재현
#   판정 기준선 또는 재현 지문을 생성
#   향후 실제로 다시 실행할 계획이 있음
#
# 일회성 포렌식은 넣지 않는다. 새 스크립트가 재실행 기준선으로 승격되면 그때 목록에
# 추가하고, **추가 시점부터** 0건을 요구한다.
#
# 게이트 명칭을 production gate 와 섞지 않는다:
#
#   production mypy gate          ./scripts/typecheck.sh            blocking SSOT
#   maintained scripts mypy gate  이 스크립트                        blocking (allowlist)
#   full scripts-tree mypy audit  python -m mypy scripts/           non-blocking 부채

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT/backend" || exit 1

# 유지 대상 — 경로는 backend/ 기준.
MAINTAINED=(
    # 운영 smoke
    scripts/smoke_daily_beta.py
    scripts/smoke_openai_fallback.py
    # 사전 v2 검증·컴파일 파이프라인 — 카탈로그 수정 시마다 재실행한다(docs/17 §22-6)
    scripts/build_daily_fortune_v2_snapshot.py
    # v2 funnel 상설 감사 — 카탈로그·가중 수정 전후를 같은 모집단으로 재측정(§22-4·§22-5)
    scripts/audit_daily_v2_funnel.py
    # 이벤트 채점 층별 ablation 상설 감사 — 채점 규칙 변경 전후 같은 코퍼스 재측정(EVENT_SCORING_3LAYER_PROPOSAL P0)
    scripts/audit_event_layer_ablation.py
    # 재현 기준선 — 설계 변경 전후를 같은 모집단으로 재측정한다
    scripts/audit_amhap_saturation.py
    scripts/audit_wealth_taxonomy_separability.py
    scripts/shadow_daewoon_hwa_post_selection.py
    # 임계값 판정 기준선 — ROLE_CLOSE_MARGIN 을 조정할 때마다 같은 모집단으로 재측정한다
    scripts/audits/measure_role_margin_census.py
)

missing=()
for f in "${MAINTAINED[@]}"; do
    [ -f "$f" ] || missing+=("$f")
done
if [ ${#missing[@]} -gt 0 ]; then
    # 목록에 있는데 파일이 없으면 조용히 통과시키지 않는다 — 이름이 바뀌었거나
    # 지워졌는데 게이트는 계속 초록으로 보이는 상태를 막는다.
    echo "maintained 목록에 있으나 존재하지 않는 파일:" >&2
    printf '  %s\n' "${missing[@]}" >&2
    exit 1
fi

exec python -m mypy --no-incremental "${MAINTAINED[@]}"
