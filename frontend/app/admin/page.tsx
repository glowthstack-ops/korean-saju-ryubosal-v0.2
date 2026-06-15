"use client";

// 운영 콘솔 개요 — 토큰·비용 KPI(USD·KRW), 월 예상, 단위 비용, 리포트 잡 상태.

import Link from "next/link";
import { useEffect, useState } from "react";
import { getOverview, type AdminOverview, type UsageTotals } from "@/lib/admin";

const won = (n: number) => `₩${n.toLocaleString()}`;
const usd = (n: number) => `$${n.toFixed(4)}`;

function CostCard({ title, t }: { title: string; t: UsageTotals }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-xs text-gray-400">{title}</p>
      <p className="mt-1 text-lg font-bold">{won(t.cost_krw)}</p>
      <p className="text-xs text-gray-500">{usd(t.cost_usd)}</p>
      <p className="mt-2 text-xs text-gray-400">
        호출 {t.calls} · 채팅 {t.chat_calls} · 리포트 {t.report_calls}
      </p>
      <p className="text-xs text-gray-400">
        토큰 입력 {t.input_tokens.toLocaleString()} / 출력{" "}
        {t.output_tokens.toLocaleString()}
      </p>
    </div>
  );
}

export default function AdminOverviewPage() {
  const [o, setO] = useState<AdminOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getOverview().then(setO).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-sm text-red-500">{err}</p>;
  if (!o) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">환율 1 USD = ₩{o.exchange_rate_usd_krw.toLocaleString()}</p>
        <Link
          href="/admin/errors"
          className={`rounded-full px-3 py-1 text-xs ${
            o.unresolved_errors > 0
              ? "bg-rose-100 font-medium text-rose-700"
              : "bg-emerald-50 text-emerald-600"
          }`}
        >
          미해결 에러 {o.unresolved_errors}건
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <CostCard title="오늘" t={o.today} />
        <CostCard title="최근 7일" t={o.last_7d} />
        <CostCard title="최근 30일" t={o.last_30d} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">이번 달 예상 비용(30일 평균 기준)</p>
          <p className="mt-1 text-lg font-bold">{won(o.projection_month_krw)}</p>
          <p className="text-xs text-gray-500">{usd(o.projection_month_usd)}</p>
        </div>
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">단위 비용(최근 30일)</p>
          <p className="mt-1 text-sm">채팅 1질의 · {usd(o.unit_cost_chat_usd)}</p>
          <p className="text-sm">리포트 1섹션 · {usd(o.unit_cost_report_section_usd)}</p>
        </div>
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs text-gray-400">리포트 잡 상태</p>
          <ul className="mt-1 text-sm">
            {Object.entries(o.job_status_counts).map(([s, n]) => (
              <li key={s} className="flex justify-between">
                <span className="text-gray-600">{s}</span>
                <span className="font-medium">{n}</span>
              </li>
            ))}
            {Object.keys(o.job_status_counts).length === 0 && (
              <li className="text-gray-400">잡 없음</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
