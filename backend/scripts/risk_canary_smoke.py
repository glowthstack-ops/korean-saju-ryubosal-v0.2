"""canary smoke test(통합 감수 §9) — 활성화 직후 1회 실행 점검.

운영 preflight 완료·EXPOSE_CANARY 활성 상태에서 실행한다. 확인:
①bootstrap adapter state=VALIDATED ②allowlist 요청=INJECTED·request
shape reviewed·counted==provider reported·cached 0·내부 ref 누출 0·
terminal=DELIVER_* ③allowlist 밖 요청=BYPASS(prompt byte 불변).
설계 검토 없음 — 실행 결과 확인 전용(통합 감수 §9 항목 그대로).

사용: RISK_ENGINE_MODE=expose_canary ... python scripts/risk_canary_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))


def main() -> int:
    from saju_api.services.risk_exposure_bootstrap import (
        bootstrap_risk_exposure,
        last_bootstrap_reason,
    )
    from saju_api.services.risk_exposure_service import apply_risk_exposure
    from saju_engines import risk_engine_config as cfg

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"  [{'OK' if ok else 'FAIL'}] {name} {detail}")

    check("mode=expose_canary", cfg.RISK_ENGINE_MODE == "expose_canary",
          cfg.RISK_ENGINE_MODE)
    check("runtime_enabled", cfg.RISK_EXPOSURE_RUNTIME_ENABLED is True)
    check("topology=single_host_single_process",
          cfg.RISK_DEPLOYMENT_TOPOLOGY == "single_host_single_process",
          cfg.RISK_DEPLOYMENT_TOPOLOGY)
    check("hmac_key=production(32B+·비기본)",
          cfg.RISK_AUDIT_HMAC_KEY != b"dev-only-rotate-before-canary"
          and len(cfg.RISK_AUDIT_HMAC_KEY) >= 32)
    check("allowlist_nonempty",
          len(cfg.RISK_EXPOSE_CANARY_SUBJECT_IDS) > 0,
          f"{len(cfg.RISK_EXPOSE_CANARY_SUBJECT_IDS)}건")

    state = bootstrap_risk_exposure()
    check("bootstrap_state=VALIDATED", state == "VALIDATED",
          f"state={state} reason={last_bootstrap_reason()}")

    # baseline(allowlist 밖) — BYPASS·byte 불변.
    p, s, obs = apply_risk_exposure(
        "smoke baseline 질문", None, subject_id="__not_allowlisted__",
        question_type="period_overview", temporal_scope="future")
    check("non_allowlisted=BYPASS",
          obs.get("disposition") == "BYPASS"
          and p == "smoke baseline 질문" and s is None,
          str(obs.get("reason")))
    print()
    failed = [c for c in checks if not c[1]]
    print(f"결과: {len(checks) - len(failed)}/{len(checks)} 통과")
    if failed:
        print("실패 항목 — canary를 열지 말 것:",
              ", ".join(c[0] for c in failed))
    print("다음 단계: 내부 allowlist 계정 1건으로 실제 chat 요청 후 관측"
          " 확인(disposition=INJECTED·counted==reported·cached=0·"
          "internal ref leak=0·terminal=DELIVER_*).")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
