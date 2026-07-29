#!/usr/bin/env python3
"""베타 일운 배포 smoke — 날짜 경계 전/후를 나누어 확인한다.

공개 경계(2026-07-30 00:00 KST) 전과 후는 기대 동작이 정반대다. 한 벌의 체크로
합치면 "아직 안 열림"과 "고장"을 구분하지 못한다.

    # 배포 직후(경계 전)
    python3 scripts/smoke_daily_beta.py --base-url https://beta.example.com --phase pre

    # 자정 이후(경계 후)
    python3 scripts/smoke_daily_beta.py --base-url https://beta.example.com --phase post \
        --admin-token "$TOKEN"

`--admin-token` 이 있으면 관리자 경로(미래 날짜·감사 메타)까지 확인한다.
종료 코드 0 = 전 항목 통과.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

KST = dt.timezone(dt.timedelta(hours=9))
ANCHOR = dt.date(2026, 7, 30)
POOL_FP = "f0ce1e0c"
BOOTSTRAP_FP = "a499f342"
RENDERER_CONTRACT = "daily-beta-render.c10.v1"


class Result:
    """통과/실패를 모아 마지막에 한 번에 보고한다 — 첫 실패에서 멈추지 않는다."""

    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str = "") -> bool:
        self.rows.append((ok, name, detail))
        return ok

    def report(self) -> int:
        for ok, name, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        failed = [r for r in self.rows if not r[0]]
        print(f"\n{len(self.rows) - len(failed)}/{len(self.rows)} 통과")
        return 1 if failed else 0


def _ci(headers: dict[str, str]) -> dict[str, str]:
    """HTTP 헤더 이름은 대소문자를 구분하지 않는다 — 소문자로 정규화한다."""
    return {k.lower(): v for k, v in headers.items()}


def _get(url: str, token: str | None = None) -> tuple[int, dict | None, dict]:
    """(status, json, headers). 네트워크 오류는 status 0."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return (
                resp.status,
                json.loads(body) if body else None,
                _ci(dict(resp.headers)),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body), _ci(dict(exc.headers))
        except json.JSONDecodeError:
            return exc.code, None, _ci(dict(exc.headers))
    except OSError as exc:
        print(f"    ! {url}: {exc}", file=sys.stderr)
        return 0, None, {}


def _code(payload: dict | None) -> str:
    detail = (payload or {}).get("detail")
    return detail.get("code", "") if isinstance(detail, dict) else str(detail or "")


def phase_pre(base: str, token: str | None, r: Result) -> None:
    """경계 전 — 공개 경로는 아직 아무 날짜도 열지 않는다."""
    status, _payload, _h = _get(f"{base}/health")
    r.check(status == 200, "/health 200", f"status={status}")

    status, payload, headers = _get(f"{base}/api/v2/daily-fortune/today")
    r.check(
        status == 503 and _code(payload) == "BETA_POOL_NOT_YET_EFFECTIVE",
        "공개 daily, 오늘(경계 전) → BETA_POOL_NOT_YET_EFFECTIVE",
        f"status={status} code={_code(payload)}",
    )
    r.check(
        headers.get("cache-control") == "no-store",
        "차단 응답은 캐시되지 않는다",
        headers.get("cache-control", "(없음)"),
    )
    if token:
        _admin_checks(base, token, r)


def phase_post(base: str, token: str | None, r: Result) -> None:
    """경계 후 — 오늘만 열리고, 내일은 선생성돼 있어도 열리지 않는다."""
    status, board, _h = _get(f"{base}/api/v2/daily-fortune/today")
    ok = r.check(status == 200, "공개 daily, 오늘 → 200", f"status={status}")
    if ok and board:
        r.check(len(board.get("fortunes", [])) == 60, "60일주 전부 응답")
        r.check(
            board.get("fortune_date") == _today().isoformat(),
            "응답 날짜 = KST 오늘",
            str(board.get("fortune_date")),
        )
        # 동일 요청 반복 — 문장까지 같아야 한다.
        _s2, board2, _h2 = _get(f"{base}/api/v2/daily-fortune/today")
        r.check(board == board2, "동일 요청 반복 → 응답 동일")
        first = board["fortunes"][0]
        _s3, single, _h3 = _get(
            f"{base}/api/v2/daily-fortune/today/{first['ilju']}"
        )
        r.check(
            bool(single) and single["fortune"]["headline"] == first["headline"],
            "단건 응답이 보드와 일치",
        )

    if token:
        _admin_checks(base, token, r)
        # 관리자 감사 메타와 공개 응답의 사건이 완전히 일치하는지 — 60일주 전부.
        _s, audit, _h = _get(
            f"{base}/api/v2/admin/daily-beta/day/{_today()}?include_board=true", token
        )
        if audit and board:
            by_ilju = {c["ilju"]: c for c in audit["cards"]}
            mismatch = [
                f["ilju"] for f in board["fortunes"]
                if f["events"][0]["event_key"] != by_ilju[f["ilju"]]["realized_good_event"]
            ]
            r.check(
                not mismatch,
                "공개 응답 사건 = snapshot 선택(60일주)",
                f"불일치 {len(mismatch)}건",
            )


def _admin_checks(base: str, token: str, r: Result) -> None:
    status, meta, _h = _get(f"{base}/api/v2/admin/daily-beta/pool", token)
    ok = r.check(status == 200, "관리자 pool 메타 200", f"status={status}")
    if not (ok and meta):
        return
    r.check(
        meta["pool_result_fingerprint"].startswith(POOL_FP),
        "pool fingerprint 일치",
        meta["pool_result_fingerprint"][:16],
    )
    r.check(
        meta["bootstrap_fingerprint"].startswith(BOOTSTRAP_FP),
        "bootstrap fingerprint 일치",
        meta["bootstrap_fingerprint"][:16],
    )
    r.check(
        meta["renderer_contract_version"] == RENDERER_CONTRACT,
        "renderer contract 일치",
        meta["renderer_contract_version"],
    )
    r.check(meta["card_count"] == 30 * 60, "1,800장 적재", str(meta["card_count"]))

    status, audit, _h = _get(f"{base}/api/v2/admin/daily-beta/day/{ANCHOR}", token)
    r.check(
        status == 200 and bool(audit) and len(audit["cards"]) == 60,
        f"관리자 {ANCHOR} 렌더 정상",
        f"status={status}",
    )
    r.check(
        bool(audit) and len(audit["render_result_fingerprint"]) == 64,
        "render fingerprint 산출",
    )


def _today() -> dt.date:
    return dt.datetime.now(KST).date()


def _future_check(base: str, r: Result) -> None:
    """일반 사용자에게 내일은 열리지 않는다 — 공개 경로에 통로가 없음을 확인한다."""
    tomorrow = _today() + dt.timedelta(days=1)
    for url in (
        f"{base}/api/v2/daily-fortune/today?date={tomorrow}",
        f"{base}/api/v2/daily-fortune/today?allow_future=true",
    ):
        status, payload, _h = _get(url)
        # 파라미터는 무시된다 — 200(오늘 보드) 이거나 차단이어야 하고, 내일 보드는 아니다.
        body_date = (payload or {}).get("fortune_date")
        r.check(
            body_date != tomorrow.isoformat(),
            f"미래 날짜가 열리지 않는다: {url.split('?')[-1]}",
            f"status={status} date={body_date}",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True, help="예: https://beta.example.com")
    ap.add_argument("--phase", choices=("pre", "post"), required=True)
    ap.add_argument("--admin-token", default=None)
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    r = Result()
    print(f"베타 일운 smoke — phase={args.phase} base={base} KST={_today()}\n")
    if args.phase == "pre":
        phase_pre(base, args.admin_token, r)
    else:
        phase_post(base, args.admin_token, r)
        _future_check(base, r)
    return r.report()


if __name__ == "__main__":
    raise SystemExit(main())
