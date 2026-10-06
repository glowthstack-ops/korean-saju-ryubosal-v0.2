"use client";

// 운영 콘솔 개요 — 토큰·비용 KPI(USD·KRW), 월 예상, 단위 비용, 리포트 잡 상태.

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  getLlmState,
  getOverview,
  postLlmResume,
  postLlmSuspend,
  type AdminOverview,
  type LlmServiceState,
  type UsageTotals,
} from "@/lib/admin";

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

// LLM 서비스 상태 카드 — 비용 소진 일시 중단 표시·프로브 재개·수동 중단(2026-10-06).
function LlmServiceCard() {
  const [s, setS] = useState<LlmServiceState | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => getLlmState().then(setS).catch((e) => setMsg(String(e)));
  useEffect(() => {
    void load();
  }, []);

  async function resume() {
    if (!confirm("공급자별 소액 프로브 호출 후 재개합니다. 결제가 완료됐나요?")) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await postLlmResume();
      const failed = r.probes.filter((p) => !p.ok).map((p) => `${p.provider}(${p.kind})`);
      setMsg(
        r.resumed
          ? `재개 완료 · 리포트 재개 ${r.requeued_reports}건 · 일운 교정 ${r.daily_polish_scheduled ? "예약" : "없음"}` +
              (failed.length ? ` · 쿨다운 유지: ${failed.join(", ")}` : "")
          : "이미 운영 중 — 프로브만 갱신했어요.",
      );
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      void load();
    }
  }

  async function suspend() {
    if (!confirm("모든 LLM 호출을 중단합니다(점검용). 계속할까요?")) return;
    setBusy(true);
    try {
      await postLlmSuspend("manual");
    } finally {
      setBusy(false);
      void load();
    }
  }

  if (!s) return <div className="rounded-lg border bg-white p-4 shadow-sm text-xs text-gray-400">LLM 상태 불러오는 중…</div>;
  const suspended = s.state === "suspended";
  const providers = Object.values(s.providers);
  return (
    <div className={`rounded-lg border p-4 shadow-sm ${suspended ? "border-rose-200 bg-rose-50" : "bg-white"}`}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">LLM 서비스</p>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${suspended ? "bg-rose-100 text-rose-700" : "bg-emerald-50 text-emerald-600"}`}>
          {suspended ? "일시 중단" : "운영 중"}
        </span>
      </div>
      {suspended && (
        <p className="mt-1 text-xs text-rose-700">
          사유 {s.reason ?? "-"} · {s.suspended_at ? s.suspended_at.slice(0, 16).replace("T", " ") : ""}
        </p>
      )}
      {providers.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-gray-600">
          {providers.map((p) => (
            <li key={p.provider}>
              {p.provider} {p.model} · {p.kind === "quota" ? "비용 소진" : "쿨다운"}
              {p.until ? ` · ${p.until.slice(11, 16)}까지 건너뜀` : ""}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-gray-500">
        재개 대기 리포트 {s.pending.suspended_report_jobs}건
        {s.pending.daily_board ? ` · 일운 ${s.pending.daily_board.date} ${s.pending.daily_board.polish_status ?? "없음"}` : ""}
      </p>
      {s.last_probe && (
        <p className="mt-1 text-[11px] text-gray-400">
          마지막 프로브 {s.last_probe.at.slice(0, 16).replace("T", " ")} ·{" "}
          {s.last_probe.results.map((r) => `${r.provider} ${r.ok ? "OK" : r.kind}`).join(" / ")}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        {suspended ? (
          <button
            onClick={resume}
            disabled={busy}
            className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "프로브 중…" : "결제 완료 — 재개"}
          </button>
        ) : (
          <button
            onClick={suspend}
            disabled={busy}
            className="rounded border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            수동 중단
          </button>
        )}
      </div>
      {msg && <p className="mt-2 text-xs text-gray-600">{msg}</p>}
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
      <LlmServiceCard />
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
