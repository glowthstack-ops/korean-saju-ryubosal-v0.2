#!/usr/bin/env bash
# 테스트 실행 중 소스가 바뀌면 그 결과는 무효다.
#
# 실제로 겪은 사고: 전체 스위트가 도는 중에 `llm_config.json` 과 그 회귀를 고쳤고,
# pytest 는 편집 전에 컴파일한 바이트코드(구 모델명)와 실행 시점에 읽은 새 설정을
# 비교해 실패했다. 코드에는 아무 문제가 없었는데 결과만 무효가 됐다.
#
# `git status` 문자열 비교로는 이 사고를 잡지 못한다 — 이미 ` M` 이던 파일을 다시
# 고친 것이라 시작과 종료의 상태 문자열이 **완전히 같았다**. 그래서 경로가 아니라
# **내용**을 지문에 넣는다.
#
# worktree 가 clean 일 필요는 없다. 더러운 채로 시작해도 시작·종료 지문이 같으면
# 유효한 실행이다.
#
# 사용법:
#   scripts/run_suite.sh                  # 기본 인자로 전체 스위트
#   scripts/run_suite.sh tests/unit -x    # pytest 인자 그대로 전달
#
# 종료 코드:
#   0   VALID_SUITE_PASS
#   65  SOURCE_CHANGED_DURING_RUN  — 테스트 성공 여부와 무관하게 실패
#   그 외  pytest 종료 코드 (TESTS_FAILED)

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 1

SNAP_DIR="$(mktemp -d)"   # 저장소 밖 — 기록 파일이 지문을 흔들면 안 된다
trap 'rm -rf "$SNAP_DIR"' EXIT

# 저장소 내용 manifest. 추적 + 비무시 미추적 파일을 모두 담는다.
#
#   HEAD          실행 중 커밋 변경 감지
#   index         스테이징 변화 감지(git ls-files -s = mode·blob·stage·path)
#   경로 + 유형   이름 변경·추가·삭제·심볼릭 링크 전환 감지
#   내용 해시     같은 경로 안에서의 수정 감지  ← status 문자열이 못 잡던 것
#
# 캐시·산출물 제외는 저장소의 ignore 계약(.gitignore)에 맡긴다. 래퍼가 임의로 넓게
# 제외하면 진짜 소스 변경까지 함께 가려진다.
manifest() {
    printf 'head\t%s\n' "$(git rev-parse HEAD)"
    printf 'index\t%s\n' "$(git ls-files -s | sha256sum | cut -d' ' -f1)"

    local list="$SNAP_DIR/list" regular="$SNAP_DIR/regular"
    git ls-files -co --exclude-standard -z | LC_ALL=C sort -z > "$list"

    : > "$regular"
    while IFS= read -r -d '' path; do
        if [ -L "$path" ]; then
            # 링크 대상이 바뀌면 내용이 바뀐 것과 같다.
            printf 'symlink\t%s\t%s\n' "$path" \
                "$(readlink -- "$path" | sha256sum | cut -d' ' -f1)"
        elif [ -f "$path" ]; then
            printf '%s\0' "$path" >> "$regular"
        elif [ -d "$path" ]; then
            printf 'gitlink\t%s\t-\n' "$path"   # 서브모듈
        else
            printf 'missing\t%s\t-\n' "$path"   # 추적 중이나 worktree 에 없음
        fi
    done < "$list"

    # 정렬된 입력 순서가 그대로 출력 순서가 된다(결정론적).
    if [ -s "$regular" ]; then
        xargs -0 -r sha256sum -- < "$regular" \
            | sed 's/^\([0-9a-f]*\)  /file\t\1\t/'
    fi
}

fingerprint() { manifest | tee "$1" | sha256sum | cut -d' ' -f1; }

START_HEAD="$(git rev-parse HEAD)"
START_FP="$(fingerprint "$SNAP_DIR/start.manifest")"

cd "$REPO_ROOT/backend" || exit 1
if [ "$#" -eq 0 ]; then
    set -- -q -p no:randomly
fi
TEST_CMD="python -m pytest $*"
python -m pytest "$@"
TEST_EXIT=$?
cd "$REPO_ROOT" || exit 1

END_HEAD="$(git rev-parse HEAD)"
END_FP="$(fingerprint "$SNAP_DIR/end.manifest")"

if [ "$START_FP" != "$END_FP" ]; then
    VERDICT="SOURCE_CHANGED_DURING_RUN"
    EXIT_CODE=65
elif [ "$TEST_EXIT" -ne 0 ]; then
    VERDICT="TESTS_FAILED"
    EXIT_CODE="$TEST_EXIT"
else
    VERDICT="VALID_SUITE_PASS"
    EXIT_CODE=0
fi

echo
echo "== SUITE RUN RECORD =="
printf '%-18s%s\n' "test_command" "$TEST_CMD"
printf '%-18s%s\n' "start_head" "$START_HEAD"
printf '%-18s%s\n' "end_head" "$END_HEAD"
printf '%-18s%s\n' "start_fingerprint" "$START_FP"
printf '%-18s%s\n' "end_fingerprint" "$END_FP"
printf '%-18s%s\n' "test_exit_code" "$TEST_EXIT"
printf '%-18s%s\n' "verdict" "$VERDICT"

if [ "$VERDICT" = "SOURCE_CHANGED_DURING_RUN" ]; then
    # 무엇이 언제 바뀌었는지 없이는 재현도 진단도 못 한다.
    echo
    echo "-- 변경 항목 (< 시작 / > 종료) --"
    diff "$SNAP_DIR/start.manifest" "$SNAP_DIR/end.manifest" | head -40
    echo
    echo "테스트 결과($TEST_EXIT)는 이 실행에서 무효다. 소스를 고정하고 다시 실행하십시오."
fi

exit "$EXIT_CODE"
