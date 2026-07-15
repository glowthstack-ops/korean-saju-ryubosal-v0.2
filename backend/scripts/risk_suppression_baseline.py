"""위험 억제 결과 baseline — 억제 의미 변경의 자동 회귀 게이트 (감수 17차 §7 후속).

메타데이터(감수 21차): baseline_commit·env 버전·해시 스키마·사전 해시·코퍼스 버전·
후보 수·생성 시각을 함께 기록한다 — 어떤 상태의 기준선인지 추적(비대상 도메인 변화
게이트의 전제).

억제 비교자·수렴 그룹 의미가 바뀌는 차수마다 실행한다:
1) 변경 전(직전 승인 커밋) 상태에서 --write로 baseline 기록(git 추적)
2) 변경 후 --check로 diff 산출 — (차트, 기간, risk_id)별 대표 변경·신규 흡수·해제를
   도메인별로 보고한다. **변경 비대상 도메인의 대표 변경 > 0이면 env 버전 갱신 +
   변경 표본 재감수가 필요하다**(감수 보고에 diff 포함).
3) 데굴님 승인 후 --write로 baseline 재생성.

pytest에는 넣지 않는다(코퍼스 만세력 계산 비용) — 차수 절차의 수동 게이트다.

실행: python scripts/risk_suppression_baseline.py --write | --check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

import hashlib  # noqa: E402
import subprocess  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from risk_shadow_density import _CORPUS, _DICTS, _LEVELS  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.dictionaries import (  # noqa: E402
    _RISK_HASH_SCHEMA_VERSION,
    RISK_REVIEW_ENVIRONMENT_VERSION,
)

_BASELINE_PATH = _BACKEND / "tests" / "fixtures" / "risk_suppression_baseline.json"


def snapshot() -> dict[str, dict]:
    """코퍼스 억제 결과 스냅숏 — (차트|기간|risk_id) → {대표, 역할, 도메인}."""
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    levels = {_LEVELS["year"], _LEVELS["month"]}
    out: dict[str, dict] = {}
    for name, birth in _CORPUS:
        chart = calculate(birth)
        engine.score(chart, levels=levels)
        for c in engine.risk_shadow:
            key = f"{name}|{c.period_key}|{c.risk_id}"
            out[key] = {
                "primary": c.suppressed_by_specificity,
                "absorbed_role": c.absorbed_role,
                "domain": c.domain.value,
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="baseline 기록(승인 후)")
    mode.add_argument("--check", action="store_true", help="baseline 대비 diff 보고")
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                        help="개명 매핑 — 소실·신규를 rename-equivalent로 분류")
    args = parser.parse_args()
    current = snapshot()
    if args.write:
        # 메타데이터(감수 21차) — baseline이 어떤 상태에서 기록됐는지 추적.
        dict_hash = hashlib.sha256(b"".join(
            path.read_bytes()
            for path in sorted((_DICTS / "risks").glob("*.json"))
        )).hexdigest()[:16]
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True, cwd=_BACKEND.parent,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            commit = "unknown"
        payload = {
            "meta": {
                "baseline_commit": commit,
                "review_environment_version": RISK_REVIEW_ENVIRONMENT_VERSION,
                "hash_schema_version": _RISK_HASH_SCHEMA_VERSION,
                "dictionary_hash": dict_hash,
                "corpus_version": "seoul-busan-10 (year+month)",
                "candidate_count": len(current),
                "generated_at": datetime.now(UTC).isoformat(
                    timespec="seconds"),
            },
            "candidates": current,
        }
        _BASELINE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"baseline 기록: {_BASELINE_PATH} ({len(current)}건)")
        return 0
    if not _BASELINE_PATH.exists():
        print("baseline 없음 — 먼저 --write로 기록")
        return 1
    stored = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    base = stored.get("candidates", stored)  # 구(평면) 형식 하위 호환
    if "meta" in stored:
        print(f"baseline meta: {stored['meta']}")
    renames = dict(pair.split("=", 1) for pair in args.rename)
    changed: Counter = Counter()  # (도메인, 유형)
    by_risk: Counter = Counter()  # (risk_id, 유형) — 항목별 delta(worklog 기록용)
    details: list[str] = []
    for key in sorted(set(base) | set(current)):
        b, c = base.get(key), current.get(key)
        b_primary = b["primary"] if b else None
        c_primary = c["primary"] if c else None
        domain = (c or b)["domain"]
        rid = key.rsplit("|", 1)[1]
        prefix = key.rsplit("|", 1)[0]
        if b is None:
            # 개명 신규 — baseline에 구 ID의 같은 (차트, 기간) 후보가 있으면 rename.
            old_rid = next((o for o, n in renames.items() if n == rid), None)
            kind = ("rename-equivalent 신규"
                    if old_rid and f"{prefix}|{old_rid}" in base else "후보 신규")
            changed[(domain, kind)] += 1
            by_risk[(rid, kind)] += 1
        elif c is None:
            new_rid = renames.get(rid)
            kind = ("rename-equivalent 소실"
                    if new_rid and f"{prefix}|{new_rid}" in current else "후보 소실")
            changed[(domain, kind)] += 1
            by_risk[(rid, kind)] += 1
        elif b_primary != c_primary:
            kind = ("대표 변경" if b_primary and c_primary
                    else "신규 흡수" if c_primary else "흡수 해제")
            changed[(domain, kind)] += 1
            by_risk[(rid, kind)] += 1
            if len(details) < 30:
                details.append(f"  {key}: {b_primary} → {c_primary}")
    if not changed:
        print(f"diff 없음 — baseline {len(base)}건과 일치")
        return 0
    print("baseline 대비 diff(도메인별):")
    for (domain, kind), n in sorted(changed.items()):
        print(f"  {domain} · {kind}: {n}건")
    print("항목별 delta:")
    for (rid, kind), n in sorted(by_risk.items()):
        print(f"  {rid} · {kind}: {n}건")
    print("표본(최대 30):")
    for line in details:
        print(line)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
