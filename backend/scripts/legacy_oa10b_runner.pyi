"""동결 소스용 sidecar 타입 계약 (2026-07-31).

`legacy_oa10b_runner.py` 는 **바이트가 동결**돼 있다 — artifact 의
`contract.legacy_runner_source_sha256` 이 파일 digest 에 묶여 있고,
`test_artifact_is_bound_to_the_frozen_source` 가 그 결합을 지킨다. 타입 주석 한 줄만
넣어도 digest 가 달라져 동결이 깨진다(실제로 `payload: dict[str, Any]` 를 넣었다가
회귀가 잡았다).

그래서 `.py` 는 그대로 두고 `.pyi` 로 타입만 제공한다. mypy 는 `.pyi` 를 우선 읽고
런타임은 기존 `.py` 를 그대로 쓰므로 다음이 동시에 성립한다.

    동결 SHA256          불변
    artifact 재생성       불필요
    tests mypy           0건
    ignore_errors 구멍    없음
    런타임 동작           불변

**테스트가 실제로 쓰는 심볼만** 선언한다. 편의로 전부 `Any` 로 채우면 사실상
`ignore_errors` 와 같아진다. 여기 없는 심볼이 필요해지면 그때 실제 시그니처를 보고
추가한다 — 스텁이 구현보다 넓어지지 않게 하려는 것이다.

수정 순서 계약(다른 동결 스크립트에도 적용):

    1. 이미 0건이면 그대로 둔다
    2. 수정이 필요하지만 digest-bound 면 `.pyi` 를 추가한다
    3. 스텁으로 표현할 수 없는 내부 구현 검사가 꼭 필요할 때만 구조 검토
    4. `ignore_errors` 는 마지막 수단
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

WARMUP_DAYS: int
WINDOW: int
FIRST_ANCHOR: dt.date

#: 선별 정책·상한 — 테스트가 동결 파라미터로 직접 읽는다(사설 이름이지만 공개
#: 계약으로 승격하지 않았다. `PRIVATE_SCRIPT_SYMBOL_DEPENDENCIES_RECORDED`).
_BOARD: Any
_DOMAIN_CAP: int
_EVENT_CAP: int
_BUDGET: int

@dataclass
class LegacyObservation:
    rows: list[dict[str, Any]]
    daily_state: list[dict[str, Any]]
    headline_history: dict[str, list[str]]

def schedule_start() -> dt.date: ...
def load_family_map() -> dict[str, str]: ...
def build_schedule_observed(
    family_of: dict[str, str], *, days: int, observe: bool = ...
) -> LegacyObservation: ...
def verify_observation_is_non_perturbing(
    family_of: dict[str, str], *, days: int
) -> bool: ...
