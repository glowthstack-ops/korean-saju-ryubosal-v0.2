"""질문 이해 층(Question Frame) shadow 측정 — 룰 파서 결정 vs 소형 로컬 LLM 프레임(docs/03 B6).

재실행 기준선 스크립트(maintained). 같은 모집단으로 모델·프롬프트 변경 전후를 비교한다.

    python scripts/measure_question_frame.py               # 고정 모집단(intent_eval + docs/08)
    python scripts/measure_question_frame.py --db --limit 300  # + 저장 채팅 사용자 발화(DSN)
    python scripts/measure_question_frame.py --out var/qf.jsonl

출력: 관측 JSONL(질문·룰 결정·프레임·불일치·지연) + 요약(건수·파싱 실패·지연 p50/p95·불일치
라벨 분포) + 검수용 표본(핵심 결함군 `lifestyle_on_overview_fallback` 전부, 그 외 라벨은 각 5건).
라우팅은 바꾸지 않는다 — 측정 결과를 보고 게이트 ON 범위를 따로 결정한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_api.services import question_frame_service  # noqa: E402
from saju_engines.query_parser import parse_message  # noqa: E402

_EVAL = _BACKEND / "tests" / "fixtures" / "intent_eval.jsonl"
_DOCS08 = _BACKEND.parent / "doc" / "v2_2" / "docs" / "08_QUESTION_PATTERNS.md"
_QUOTE_RE = re.compile(r"[\"“]([^\"”]{4,60})[\"”]")


def _eval_questions() -> list[str]:
    """tests/fixtures/intent_eval.jsonl 의 질문(40건)."""
    if not _EVAL.exists():
        return []
    out: list[str] = []
    for line in _EVAL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(str(json.loads(line)["q"]))
    return out


def _docs08_questions() -> list[str]:
    """docs/08 표·체크리스트의 큰따옴표 예시 발화(한글 포함 4~60자)."""
    if not _DOCS08.exists():
        return []
    out: list[str] = []
    for m in _QUOTE_RE.finditer(_DOCS08.read_text(encoding="utf-8")):
        s = m.group(1).strip()
        # 표 셀·줄바꿈을 가로지른 매치('| C14 | 대운 단위 |')는 발화가 아니다 — 모집단에서 뺀다.
        if "|" in s or "\n" in s or s.startswith("("):
            continue
        if re.search(r"[가-힣]", s) and s not in out:
            out.append(s)
    return out


def _db_questions(limit: int) -> list[str]:
    """저장된 채팅 사용자 발화(중복 제거, 최신순). DSN(SAJU_V2_DATABASE_URL) 없으면 빈 목록."""
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정 — DB 발화 생략", file=sys.stderr)
        return []
    import psycopg

    sql = (
        "SELECT text FROM chat_messages WHERE role = 'user' "
        "GROUP BY text ORDER BY max(created_at) DESC LIMIT %s"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [str(r[0]).strip() for r in rows if str(r[0]).strip()]


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[idx]


def main() -> int:
    """측정 실행 — 종료 코드 0(측정 완료) / 2(모집단 없음)."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db", action="store_true", help="저장된 채팅 사용자 발화 포함")
    ap.add_argument("--limit", type=int, default=300, help="--db 발화 상한")
    ap.add_argument(
        "--out", type=Path, default=_BACKEND.parent / "var" / "question_frame_measure.jsonl",
    )
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    questions: list[str] = []
    db_qs: list[str] = _db_questions(args.limit) if args.db else []
    for src in (_eval_questions(), _docs08_questions(), db_qs):
        for q in src:
            if q not in questions:
                questions.append(q)
    if not questions:
        print("모집단 없음", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with args.out.open("w", encoding="utf-8") as fh:
        for n, q in enumerate(questions, 1):
            try:
                intent = parse_message(q, args.today).intents[0]
            except Exception as exc:  # noqa: BLE001 — 룰 파서 실패도 모집단에 남긴다
                rows.append({"question": q, "rule_error": f"{type(exc).__name__}: {exc}"})
                fh.write(json.dumps(rows[-1], ensure_ascii=False) + "\n")
                continue
            shadow = question_frame_service.observe_sync(q, intent)
            row = shadow.model_dump(mode="json")
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n % 25 == 0:
                print(f"... {n}/{len(questions)}", file=sys.stderr)

    observed = [r for r in rows if "rule_error" not in r]
    ok = [r for r in observed if r["ok"]]
    lat = [int(r["latency_ms"]) for r in observed]
    labels: Counter[str] = Counter(lbl for r in ok for lbl in r["disagreements"])
    print(f"\n== Question Frame 측정 요약 ({args.today}) ==")
    print(
        f"모집단 {len(questions)} · 관측 {len(observed)} · 프레임 OK {len(ok)} · "
        f"실패 {len(observed) - len(ok)}"
    )
    if lat:
        print(f"지연 ms: p50 {_percentile(lat, 0.5)} · p95 {_percentile(lat, 0.95)} · "
              f"max {max(lat)} · mean {statistics.mean(lat):.0f}")
    print(f"불일치 있는 턴 {sum(1 for r in ok if r['disagreements'])}/{len(ok)}")
    for lbl, cnt in labels.most_common():
        print(f"  {lbl:34} {cnt}")
    errors: Counter[str] = Counter(str(r["error"]).split(":")[0] for r in observed if not r["ok"])
    if errors:
        print("실패 사유:", dict(errors))

    print("\n== 검수 표본 ==")
    shown: Counter[str] = Counter()
    for r in ok:
        for lbl in r["disagreements"]:
            cap = 10_000 if lbl == "lifestyle_on_overview_fallback" else 5
            if shown[lbl] >= cap:
                continue
            shown[lbl] += 1
            f = r["frame"]
            print(
                f"[{lbl}] {r['question']!r} | rule={r['rule_query_type']}/{r['rule_domain']} "
                f"| frame={f['ask_kind']}/{f['lifestyle_item']}/{f['answer_shape']} "
                f"'{f['topic_object']}'"
            )
    print(f"\nJSONL → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
