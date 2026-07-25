"""P0-B shadow 불변성 census — CAREER_TRANSITION_SYSTEM §15-3·§16-0.

P0-B 종료 조건을 테스트로 제도화한다:
- 기존 엔진 점수·랭킹·직렬화 변화 0 (`shadow_output_drift`)
- authoritative career state 변경 0 (신규 모듈이 production에 미배선)
- 사용자용 LLM·report 입력 변화 0 (inbound import 0으로 구조 보장)

`shadow_output_drift`는 단독 0이 아니라 **census와 함께** 평가한다(INV-25):
`eligible_count > 0` · `measured_count == eligible_count` · `violation_count == 0`.

비교는 **격리된 control/treatment 프로세스**로 수행한다 — 같은 프로세스에서 import 전후를
비교하면 import cache·전역 상태 때문에 검증력이 약하다.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[1]
_BACKEND = _TESTS.parent
_REPO = _BACKEND.parent

#: 커리어 shadow 신규 모듈(P0-B·P1) — production 경로에서 import되면 안 된다.
#: 이 목록의 모듈끼리 서로 import하는 것은 허용된다(shadow 내부 의존).
_NEW_MODULES = (
    "saju_shared_types.career_transition",
    "saju_shared_types.career_commands",
    "saju_shared_types.event_semantics",
    "saju_engines.event_semantics_resolver",
    "saju_engines.career_stage_adapter",
    "saju_engines.career_shadow_observation",
    "saju_engines.career_transition_reducer",
    "saju_engines.career_shadow_metrics",
    "saju_shared_types.career_effect_vector",
    "saju_engines.career_effect_vector",
    "saju_engines.career_fact_parser",
    "saju_engines.career_state_shadow",
)

#: census manifest — **분모는 실행 결과가 아니라 독립 고정 manifest에서 나온다.**
#: 동적으로 로딩된 성공 건수를 분모로 쓰면 fixture가 누락돼도 eligible=measured로
#: 잘못 통과한다(INV-25).
_CORPUS_ID = "career-p0b-drift.v1"
_EXPECTED_CASE_IDS: frozenset[str] = frozenset(
    {"1980-11-22-m-seoul", "1992-03-05-f-busan", "2001-08-17-m-seoul-late"}
)
_EXPECTED_CASE_COUNT = 3

#: drift census 코퍼스 — 고유 case identity(=고유 입력 조합).
_CASES: tuple[dict[str, str], ...] = (
    {"case_id": "1980-11-22-m-seoul", "birth_date": "1980-11-22", "birth_time": "09:08",
     "place": "서울", "gender": "male"},
    {"case_id": "1992-03-05-f-busan", "birth_date": "1992-03-05", "birth_time": "14:20",
     "place": "부산", "gender": "female"},
    # seed_locations 에 등록된 지명만 사용한다(서울·부산·Tokyo·New York).
    {"case_id": "2001-08-17-m-seoul-late", "birth_date": "2001-08-17", "birth_time": "23:40",
     "place": "서울", "gender": "male"},
)

# control/treatment 러너 — treatment 만 P0-B 모듈을 명시적으로 import 한다.
_RUNNER = r"""
import json, sys
from datetime import date

arm = sys.argv[1]
payload = json.loads(sys.argv[2])

if arm == "treatment":
    import saju_shared_types.career_transition  # noqa: F401
    import saju_shared_types.event_semantics  # noqa: F401
    import saju_engines.career_shadow_observation  # noqa: F401
    import saju_engines.career_stage_adapter  # noqa: F401
    import saju_engines.event_semantics_resolver  # noqa: F401

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import EVENT_CATEGORY
from saju_shared_types.ganji_calendar import GanjiLevel

dicts = Path(payload["dicts"])
engine = EventEngineV2(dicts)
out = {}
for case in payload["cases"]:
    y, m, d = (int(x) for x in case["birth_date"].split("-"))
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=case["birth_time"],
        birth_place_name=case["place"], gender=case["gender"],
        reference_date=date(2026, 6, 11),
    ))
    cands = engine.score(chart, levels={GanjiLevel.YEAR})

    # raw 직렬화를 그대로 비교한다 — reason_codes 순서 비결정성이 해소된 뒤로는
    # 정규화 우회가 필요 없다(REASON_CODES_ORDER_NONDETERMINISTIC = CLOSED).
    out[case["case_id"]] = [
        {
            "rank": i,
            "event_key": str(c.event_key),
            "period": c.period,
            "score": c.score,
            "raw_score": c.raw_score,
            "activation": c.activation,
            "favorability": c.favorability,
            "confidence_level": str(c.confidence_level),
            "legacy_serialized_category": EVENT_CATEGORY.get(c.event_key),
            "serialized": c.model_dump(mode="json"),
        }
        for i, c in enumerate(cands)
    ]
print(json.dumps(out, sort_keys=True, ensure_ascii=False))
"""


def _run_arm(arm: str) -> dict[str, list[dict[str, object]]]:
    payload = json.dumps({"dicts": str(_BACKEND / "dictionaries"), "cases": list(_CASES)})
    # 해시 시드를 고정하지 않는다 — 엔진이 seed 무관 결정적이어야 하며, 고정하면 그
    # 성질을 검증하지 못한다(multi-seed 회귀는 tests/regression 에 별도로 있다).
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, "-c", _RUNNER, arm, payload],
        capture_output=True, text=True, cwd=str(_REPO), timeout=900, env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"{arm} arm 실패: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def arms() -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    """격리 실행 2회 — control(미import) / treatment(P0-B 모듈 import)."""
    return _run_arm("control"), _run_arm("treatment")


def test_census_corpus_matches_manifest() -> None:
    """코퍼스 identity 검증 — manifest와 다르면 violation 0이어도 DEGRADED다.

    분모를 실행 결과에서 얻으면 fixture 누락 시 `eligible=measured=2`로 조용히
    통과한다. manifest를 독립 고정해 그 사고를 막는다.
    """
    loaded = [c["case_id"] for c in _CASES]
    assert len(loaded) == len(set(loaded)), f"duplicate_case_count > 0: {loaded}"
    assert set(loaded) == _EXPECTED_CASE_IDS, (
        f"corpus '{_CORPUS_ID}' 불일치 — missing={sorted(_EXPECTED_CASE_IDS - set(loaded))} "
        f"unexpected={sorted(set(loaded) - _EXPECTED_CASE_IDS)}"
    )
    assert len(loaded) == _EXPECTED_CASE_COUNT


def test_shadow_output_drift_census(arms) -> None:
    """P0-B: 신규 모듈 도입이 기존 엔진 출력을 바꾸지 않는다(census 포함).

    비교 단위는 개별 필드가 아니라 **정렬된 후보 목록 전체**다(랭킹 포함).

    비교 모드는 `RAW_BYTE`다 — `REASON_CODES_ORDER_NONDETERMINISTIC` 해소 후로는
    정규화 없이 raw 직렬화를 그대로 비교하며 해시 시드도 고정하지 않는다.
    """
    control, treatment = arms
    # 분모는 manifest에서 — 실행 결과에서 얻지 않는다.
    eligible = set(_EXPECTED_CASE_IDS)
    excluded: set[str] = set()  # 명시적 제외 없음
    measured = (eligible - excluded) & set(control) & set(treatment)
    violations = sorted(cid for cid in measured if control[cid] != treatment[cid])

    # census — "오류 0"이 아니라 "전수 측정 후 오류 0"(INV-25)
    assert len(eligible) > 0, "eligible_count = 0 → NO_ELIGIBLE_CASES(통과 아님)"
    assert measured == eligible - excluded, (
        "measurement_status=DEGRADED — 불완전 계측: "
        f"measured={sorted(measured)} eligible={sorted(eligible)}"
    )
    assert not violations, f"shadow_output_drift violation: {violations}"


def test_drift_corpus_produces_candidates(arms) -> None:
    """빈 결과로 통과하는 착시 방지 — 코퍼스가 실제 후보를 만든다."""
    control, _ = arms
    assert sum(len(v) for v in control.values()) > 0


# ── production 미배선 (기존 파일 무수정 원칙의 테스트 제도화) ──────────────


def _iter_production_py() -> list[Path]:
    roots = [_BACKEND / "packages", _BACKEND / "apps"]
    files: list[Path] = []
    for root in roots:
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.name in {mod.split(".")[-1] + ".py" for mod in _NEW_MODULES}:
                continue  # 신규 모듈 자신은 제외
            files.append(p)
    return files


def _imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - 구문 오류는 별도 게이트가 잡는다
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_production_inbound_import() -> None:
    """P0-B 신규 모듈을 production(packages/apps)에서 import하지 않는다.

    inbound import가 0이면 사용자용 LLM·report 입력과 권위 상태 변경 0이 구조적으로
    보장된다 — "기존 파일 무수정" 원칙을 테스트로 고정한다.
    """
    offenders: list[str] = []
    for path in _iter_production_py():
        hit = _imported_modules(path) & set(_NEW_MODULES)
        if hit:
            offenders.append(f"{path.relative_to(_REPO)} → {sorted(hit)}")
    assert not offenders, "production inbound import 발견:\n" + "\n".join(offenders)


def test_conversation_state_has_no_career_field() -> None:
    """`ConversationState`에 career 필드를 추가하지 않는다(권위 상태 변경 0)."""
    from saju_shared_types.conversation import ConversationState

    career_fields = [f for f in ConversationState.model_fields if "career" in f]
    assert career_fields == []


def test_career_store_is_contract_only() -> None:
    """저장소 aggregate에 authoritative write·영속 메서드가 없다."""
    from saju_shared_types.career_transition import CareerEpisodeStore

    forbidden = {"save", "persist", "commit", "write", "flush", "delete"}
    assert not (forbidden & set(dir(CareerEpisodeStore)))


def test_adapter_has_no_silent_noop_implementation() -> None:
    """어댑터는 Protocol/ABC이며 silent no-op 구현체를 두지 않는다.

    실수로 배선돼도 '후보 없음'처럼 조용히 통과하지 않고 실패해야 한다.
    """
    import inspect

    from saju_engines.career_stage_adapter import CareerStageAdapter

    assert inspect.isabstract(CareerStageAdapter)
    with pytest.raises(TypeError):
        CareerStageAdapter()  # type: ignore[abstract]


#: 기존 파일 수정이 허용된 파일(baseline hygiene 등 명시 승인분).
#: career·score·consumer 파일의 무단 변경은 계속 차단한다.
_MODIFY_ALLOWLIST = frozenset(
    {
        # reason_codes 결정성 수정(REASON_CODES_ORDER_NONDETERMINISTIC 해소).
        "backend/packages/saju_engines/saju_engines/ten_god_brancher.py",
    }
)


def test_diff_outside_allowlist_is_add_only() -> None:
    """P0-A 체크포인트 대비 **신규 파일 추가만** 있어야 한다.

    baseline hygiene 처럼 명시 승인된 파일만 `_MODIFY_ALLOWLIST`로 예외를 둔다.
    문서(doc/)는 계약 갱신이 허용되므로 애초에 대상이 아니다.
    """
    proc = subprocess.run(
        ["git", "diff", "--name-status", "88ac10d", "--", "backend", "frontend"],
        capture_output=True, text=True, cwd=str(_REPO), timeout=120,
    )
    if proc.returncode != 0:
        pytest.skip(f"git diff 불가: {proc.stderr[:200]}")
    modified = [
        line for line in proc.stdout.splitlines()
        if line and not line.startswith("A\t")
        and line.split("\t", 1)[-1] not in _MODIFY_ALLOWLIST
    ]
    assert not modified, (
        "allowlist 밖 기존 파일 변경 발견:\n" + "\n".join(modified)
    )
