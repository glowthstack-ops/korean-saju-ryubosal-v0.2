"""베타 일운 풀 — 배포 단위 설정과 불변 registry.

베타 대상 판정은 **배포 환경 전체 적용**이다. 계정 플래그·요청 헤더·query parameter
로 나누지 않는다 — 사용자마다 legacy 와 C10 이 섞이면 피드백의 기준이 무너지고,
헤더는 위조할 수 있다.

    베타 배포   DAILY_BETA_POOL_ENABLED=true   → 모든 일반 일운 요청이 snapshot 경로
    일반 배포   DAILY_BETA_POOL_ENABLED=false  → 기존 legacy 경로

검증 실패 시 legacy 로 조용히 내려가지 않는다. 시작 preflight 가 실패하면 프로세스를
ready 로 올리지 않고, 런타임 손상이면 베타 일운 API 만 `BETA_POOL_UNAVAILABLE` 로
차단한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from saju_engines.daily_beta_pool import (
    BETA_POOL_FINGERPRINT_MISMATCH,
    BETA_POOL_UNAVAILABLE,
    RENDERER_CONTRACT_VERSION,
    BetaPoolError,
    pool_metadata,
    render_board,
    render_result_fingerprint,
    validate_pool,
)
from saju_shared_types.daily_fortune import DailyFortuneBoard

#: 베타 기간 밖 — legacy 로 내려가지 않는다. 테스터는 한 풀만 본다.
BETA_POOL_NOT_YET_EFFECTIVE = "BETA_POOL_NOT_YET_EFFECTIVE"
BETA_POOL_EXPIRED = "BETA_POOL_EXPIRED"


def _flag(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = _flag(name)
    return default if not raw else raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BetaPoolConfig:
    """배포 환경 계약. 요청마다 다시 읽지 않는다."""

    enabled: bool
    required: bool
    pool_version: str
    audience: str
    renderer_contract: str
    effective_from: date | None
    effective_until: date | None
    expected_pool_fingerprint: str
    expected_bootstrap_fingerprint: str
    compiled_dir: Path

    @classmethod
    def from_env(cls) -> BetaPoolConfig:
        raw_dir = _flag("DAILY_BETA_POOL_PATH")
        return cls(
            enabled=_bool("DAILY_BETA_POOL_ENABLED"),
            required=_bool("DAILY_BETA_POOL_REQUIRED", True),
            pool_version=_flag("DAILY_BETA_POOL_VERSION"),
            audience=_flag("DAILY_BETA_AUDIENCE", "deployment"),
            renderer_contract=_flag(
                "DAILY_BETA_RENDERER_CONTRACT", RENDERER_CONTRACT_VERSION
            ),
            effective_from=(
                date.fromisoformat(_flag("DAILY_BETA_POOL_EFFECTIVE_FROM"))
                if _flag("DAILY_BETA_POOL_EFFECTIVE_FROM") else None
            ),
            effective_until=(
                date.fromisoformat(_flag("DAILY_BETA_POOL_EFFECTIVE_UNTIL"))
                if _flag("DAILY_BETA_POOL_EFFECTIVE_UNTIL") else None
            ),
            expected_pool_fingerprint=_flag("DAILY_BETA_EXPECTED_POOL_FP"),
            expected_bootstrap_fingerprint=_flag("DAILY_BETA_EXPECTED_BOOTSTRAP_FP"),
            compiled_dir=(
                Path(raw_dir) if raw_dir
                else Path(__file__).resolve().parents[4] / "compiled"
            ),
        )


@dataclass(frozen=True)
class BetaDailyPoolRegistry:
    """시작 시 1회 구성하는 불변 registry — 요청마다 파일을 다시 읽지 않는다."""

    config: BetaPoolConfig
    metadata: dict[str, Any]
    selections: dict[tuple[str, str], dict[str, Any]]

    @property
    def pool_version(self) -> str:
        return self.metadata["pool_version"]


def build_registry(config: BetaPoolConfig | None = None) -> BetaDailyPoolRegistry:
    """preflight — 실패하면 예외를 던진다(프로세스를 ready 로 올리지 않는다).

    Raises:
        BetaPoolError: 설정 누락 · 검증 실패 · 지문 불일치.
    """
    cfg = config or BetaPoolConfig.from_env()
    if not cfg.pool_version:
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, "DAILY_BETA_POOL_VERSION 미설정")
    if cfg.audience != "deployment":
        raise BetaPoolError(
            BETA_POOL_UNAVAILABLE,
            f"이번 단계는 배포 전체 적용만 지원한다: {cfg.audience}",
        )
    meta = pool_metadata(cfg.pool_version, cfg.compiled_dir)
    # 버전만 맞고 지문이 다르면 활성화하지 않는다.
    for expected, key in (
        (cfg.expected_pool_fingerprint, "pool_result_fingerprint"),
        (cfg.expected_bootstrap_fingerprint, "bootstrap_fingerprint"),
    ):
        if expected and not meta[key].startswith(expected):
            raise BetaPoolError(
                BETA_POOL_FINGERPRINT_MISMATCH, f"{key}: {meta[key][:16]} != {expected}"
            )
    if meta["display_selection_policy_version"] != (
        "display-selection.p4-lc.c10.v1"
    ):
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, "표시 정책 버전 불일치")
    selections = {
        k: v for k, v in validate_pool(cfg.pool_version, cfg.compiled_dir).items()
    }
    return BetaDailyPoolRegistry(config=cfg, metadata=meta, selections=selections)


def date_gate(registry: BetaDailyPoolRegistry, target_date: date) -> None:
    """베타 기간 판정. 기간 밖이면 **legacy 로 내려가지 않고** 차단한다."""
    cfg = registry.config
    if cfg.effective_from and target_date < cfg.effective_from:
        raise BetaPoolError(
            BETA_POOL_NOT_YET_EFFECTIVE, f"{target_date} < {cfg.effective_from}"
        )
    if cfg.effective_until and target_date > cfg.effective_until:
        raise BetaPoolError(BETA_POOL_EXPIRED, f"{target_date} > {cfg.effective_until}")


def render(
    registry: BetaDailyPoolRegistry,
    target_date: date,
    *,
    now: datetime | None = None,
    allow_future: bool = False,
) -> tuple[DailyFortuneBoard, dict[str, Any]]:
    """베타 보드 + 감사 메타데이터.

    Args:
        registry: 시작 시 구성된 불변 registry.
        target_date: 운세 날짜.
        now: 현재 시각(KST 환산). 테스트가 주입한다.
        allow_future: **관리자 경로 전용.** 공개 라우터는 사용자 입력을 그대로
            전달하지 않는다.

    Returns:
        (보드, 감사 메타). 감사 메타는 사용자 화면에 그대로 노출하지 않는다.
    """
    date_gate(registry, target_date)
    board = render_board(
        registry.pool_version, target_date, now=now, allow_future=allow_future,
        compiled_dir=registry.config.compiled_dir,
    )
    meta = registry.metadata
    audit = {
        "source": "BETA_POOL_SNAPSHOT",
        "pool_version": meta["pool_version"],
        "pool_result_fingerprint": meta["pool_result_fingerprint"],
        "bootstrap_fingerprint": meta["bootstrap_fingerprint"],
        "display_selection_policy_version": meta["display_selection_policy_version"],
        "renderer_contract_version": registry.config.renderer_contract,
        "render_result_fingerprint": render_result_fingerprint(board),
        "cards": [
            {
                "ilju": c["ilju"],
                "intended_good_representative": c["intended_good_representative"],
                "realized_good_event": c["display_good_representative"],
                "representative_realized": c["representative_realized"],
                "realized_display_displacement_loss": c["display_displacement_loss"],
                "selection_reason_codes": _reason_codes(c),
            }
            for c in (
                registry.selections[(target_date.isoformat(), f.ilju)]
                for f in board.fortunes
            )
        ],
    }
    return board, audit


#: 의도만 있었는데 실현된 것처럼 기록하면 이후 감사가 다시 왜곡된다.
LONGITUDINAL_ALTERNATIVE_INTENDED = "LONGITUDINAL_ALTERNATIVE_INTENDED"
LONGITUDINAL_ALTERNATIVE_REALIZED = "LONGITUDINAL_ALTERNATIVE_REALIZED"
LONGITUDINAL_ALTERNATIVE_NOT_REALIZED = "LONGITUDINAL_ALTERNATIVE_NOT_REALIZED"
INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE = "INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE"


def _reason_codes(card: dict[str, Any]) -> list[str]:
    """의도와 실현을 분리해 기록한다."""
    codes = [card["good_selection_reason"]]
    intended_alternative = (
        card["intended_good_representative"] != card["headline_pool_raw_winner"]
    )
    if intended_alternative:
        codes.append(LONGITUDINAL_ALTERNATIVE_INTENDED)
        codes.append(
            LONGITUDINAL_ALTERNATIVE_REALIZED if card["representative_realized"]
            else LONGITUDINAL_ALTERNATIVE_NOT_REALIZED
        )
    if not card["representative_realized"]:
        codes.append(INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE)
    return codes
