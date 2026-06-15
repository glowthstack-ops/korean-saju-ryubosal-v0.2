"""LLM 사용량·비용 영속 저장소 + 관리자 등록 단가/환율 (운영 콘솔 Phase A — saju-v2-db 전용).

기존 in-memory COST_LEDGER는 재시작 시 소실되어 집계·BI가 불가하므로, 호출 1건당 사용량·비용을
DB에 영속한다. 단가(model_pricing)·환율(admin_settings)은 관리자가 페이지에서 직접 등록·변경하며,
비용은 '로그 시점 단가'로 계산해 cost_usd에 스냅샷한다(단가가 바뀌어도 과거 비용 불변).
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "009_admin_usage.sql"
_MODEL_PRICES = Path(__file__).resolve().parents[3] / "config" / "model_prices.json"
_DEFAULT_USD_KRW = "1350"  # 기본 환율(관리자가 변경) — USD→KRW


def compute_cost_usd(
    input_tokens: int, output_tokens: int, cached_tokens: int,
    input_per_1m: float, output_per_1m: float, cached_per_1m: float,
) -> float:
    """토큰·단가($/1M)로 비용($)을 계산한다. 캐시된 입력은 cached 단가로(할인) 분리 과금."""
    billable_input = max(input_tokens - cached_tokens, 0)
    cost = (
        billable_input * input_per_1m
        + cached_tokens * cached_per_1m
        + output_tokens * output_per_1m
    ) / 1_000_000
    return round(cost, 6)


class _DsnStore:
    """공통 — DSN 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등)."""
        with self._connect() as conn:
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))


class PricingStore(_DsnStore):
    """model_pricing(단가) + admin_settings(환율 등) 관리. 관리자 페이지에서 등록·변경."""

    def seed_defaults(self) -> None:
        """단가 미등록 모델을 model_prices.json 기본값으로 채우고, 환율 기본값을 보장한다(멱등)."""
        try:
            prices = json.loads(_MODEL_PRICES.read_text(encoding="utf-8")).get("prices", {})
        except (OSError, ValueError):
            prices = {}
        with self._connect() as conn:
            for model, p in prices.items():
                conn.execute(
                    "INSERT INTO model_pricing (model, input_per_1m, output_per_1m, "
                    "cached_per_1m, updated_by) VALUES (%s, %s, %s, %s, 'seed') "
                    "ON CONFLICT (model) DO NOTHING",
                    (model, p.get("input", 0), p.get("output", 0),
                     round(float(p.get("input", 0)) * 0.25, 4)),
                )
            conn.execute(
                "INSERT INTO admin_settings (key, value) VALUES ('usd_krw', %s) "
                "ON CONFLICT (key) DO NOTHING",
                (_DEFAULT_USD_KRW,),
            )

    def list_pricing(self) -> list[dict]:
        """등록된 모델 단가 전체."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT model, input_per_1m, output_per_1m, cached_per_1m, updated_at, "
                "updated_by FROM model_pricing ORDER BY model"
            ).fetchall()
        return [
            {
                "model": r[0], "input_per_1m": float(r[1]), "output_per_1m": float(r[2]),
                "cached_per_1m": float(r[3]), "updated_at": r[4], "updated_by": r[5],
            }
            for r in rows
        ]

    def upsert_pricing(
        self, model: str, input_per_1m: float, output_per_1m: float,
        cached_per_1m: float = 0.0, updated_by: str | None = None,
    ) -> None:
        """모델 단가 등록·수정(관리자)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO model_pricing (model, input_per_1m, output_per_1m, "
                "cached_per_1m, updated_at, updated_by) VALUES (%s, %s, %s, %s, now(), %s) "
                "ON CONFLICT (model) DO UPDATE SET input_per_1m = EXCLUDED.input_per_1m, "
                "output_per_1m = EXCLUDED.output_per_1m, cached_per_1m = EXCLUDED.cached_per_1m, "
                "updated_at = now(), updated_by = EXCLUDED.updated_by",
                (model, input_per_1m, output_per_1m, cached_per_1m, updated_by),
            )

    def price_for(self, model: str) -> tuple[float, float, float]:
        """모델 단가(input, output, cached) — 미등록 시 (0,0,0)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT input_per_1m, output_per_1m, cached_per_1m FROM model_pricing "
                "WHERE model = %s", (model,),
            ).fetchone()
        return (float(row[0]), float(row[1]), float(row[2])) if row else (0.0, 0.0, 0.0)

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM admin_settings WHERE key = %s", (key,)
            ).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO admin_settings (key, value, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, value),
            )

    def usd_krw(self) -> float:
        """현재 환율(USD→KRW)."""
        try:
            return float(self.get_setting("usd_krw", _DEFAULT_USD_KRW))
        except ValueError:
            return float(_DEFAULT_USD_KRW)


class UsageStore(_DsnStore):
    """llm_usage(호출별 사용량·비용) 기록·집계."""

    def record(
        self, *, surface: str, model: str, provider: str,
        input_tokens: int, output_tokens: int, cached_tokens: int, cost_usd: float,
        owner_id: str | None = None, product_code: str | None = None,
        call_type: str | None = None, is_fallback: bool = False, ref_id: str | None = None,
    ) -> None:
        """호출 1건 기록(best-effort — 호출 측에서 예외를 삼킨다)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO llm_usage (owner_id, surface, product_code, call_type, model, "
                "provider, is_fallback, input_tokens, output_tokens, cached_tokens, cost_usd, "
                "ref_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (owner_id, surface, product_code, call_type, model, provider, is_fallback,
                 input_tokens, output_tokens, cached_tokens, cost_usd, ref_id),
            )

    def summary(
        self, *, start: str | None = None, end: str | None = None, group_by: str = "day",
    ) -> list[dict]:
        """기간 집계 — group_by: day | surface | product | model | owner."""
        # 일자 집계는 KST 기준(한국 운영) — UTC 경계로 끊지 않는다.
        _day = "to_char(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD')"
        col = {
            "day": _day, "surface": "surface", "product": "product_code",
            "model": "model", "owner": "owner_id",
        }.get(group_by, _day)
        where, params = self._range(start, end)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {col} AS k, COUNT(*) calls, SUM(input_tokens), SUM(output_tokens), "
                f"SUM(cached_tokens), SUM(cost_usd) FROM llm_usage {where} "
                f"GROUP BY k ORDER BY k",
                params,
            ).fetchall()
        return [
            {
                "key": r[0], "calls": r[1], "input_tokens": int(r[2] or 0),
                "output_tokens": int(r[3] or 0), "cached_tokens": int(r[4] or 0),
                "cost_usd": float(r[5] or 0),
            }
            for r in rows
        ]

    def totals(self, *, start: str | None = None, end: str | None = None) -> dict:
        """기간 총합(KPI)."""
        where, params = self._range(start, end)
        with self._connect() as conn:
            r = conn.execute(
                f"SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd), "
                f"COUNT(*) FILTER (WHERE surface='chat'), "
                f"COUNT(*) FILTER (WHERE surface='report') FROM llm_usage {where}",
                params,
            ).fetchone() or (0, 0, 0, 0, 0, 0)
        return {
            "calls": r[0] or 0, "input_tokens": int(r[1] or 0),
            "output_tokens": int(r[2] or 0), "cost_usd": float(r[3] or 0),
            "chat_calls": r[4] or 0, "report_calls": r[5] or 0,
        }

    @staticmethod
    def _range(start: str | None, end: str | None) -> tuple[str, list]:
        clauses, params = [], []
        if start:
            clauses.append("created_at >= %s")
            params.append(start)
        if end:
            clauses.append("created_at < %s")
            params.append(end)
        return ("WHERE " + " AND ".join(clauses) if clauses else "", params)
