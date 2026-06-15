"use client";

// 시스템 에러 모니터링 — 미처리 5xx(http)·LLM 실패(llm)·리포트 잡 실패(report_job)를 한 곳에서 본다.
// 묶음(fingerprint별 빈도)/전체(개별) 토글, 출처·심각도·미해결 필터, 해결 처리(행/묶음 단위).

import { useCallback, useEffect, useState } from "react";
import {
  getErrorGroups,
  getErrors,
  resolveErrors,
  type ErrorGroup,
  type ErrorRow,
} from "@/lib/admin";

const SOURCES = ["", "http", "llm", "report_job", "background"];
const SOURCE_KO: Record<string, string> = {
  http: "HTTP 5xx", llm: "LLM 호출", report_job: "리포트 잡", background: "백그라운드",
};
const SEVERITIES = ["", "error", "warning"];
const SRC_BADGE: Record<string, string> = {
  http: "bg-rose-100 text-rose-700",
  llm: "bg-violet-100 text-violet-700",
  report_job: "bg-amber-100 text-amber-700",
  background: "bg-slate-100 text-slate-600",
};

function ts(s: string | null): string {
  return s ?? "-";
}

export default function AdminErrorsPage() {
  const [mode, setMode] = useState<"groups" | "flat">("groups");
  const [source, setSource] = useState("");
  const [severity, setSeverity] = useState("");
  const [unresolved, setUnresolved] = useState(true);
  const [days, setDays] = useState(7);

  const [groups, setGroups] = useState<ErrorGroup[]>([]);
  const [counts, setCounts] = useState<{ total: number; unresolved: number }>({ total: 0, unresolved: 0 });
  const [rows, setRows] = useState<ErrorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Record<string, ErrorRow[] | null>>({});

  const load = useCallback(() => {
    setLoading(true);
    setOpen({});
    if (mode === "groups") {
      getErrorGroups(days, unresolved)
        .then((d) => {
          let g = d.groups;
          if (source) g = g.filter((x) => x.source === source);
          if (severity) g = g.filter((x) => x.severity === severity);
          setGroups(g);
          setCounts(d.counts);
        })
        .finally(() => setLoading(false));
    } else {
      getErrors({ source: source || undefined, severity: severity || undefined, unresolved, limit: 300 })
        .then((d) => setRows(d.errors))
        .finally(() => setLoading(false));
    }
  }, [mode, source, severity, unresolved, days]);

  useEffect(() => {
    load();
  }, [load]);

  // 묶음 펼침 — 해당 fingerprint의 최근 발생 개별 건을 불러온다.
  const toggle = useCallback(
    (fp: string) => {
      setOpen((cur) => {
        if (fp in cur) {
          const next = { ...cur };
          delete next[fp];
          return next;
        }
        return { ...cur, [fp]: null };
      });
      getErrors({ fingerprint: fp, limit: 20 }).then((d) =>
        setOpen((cur) => (fp in cur ? { ...cur, [fp]: d.errors } : cur)),
      );
    },
    [],
  );

  async function resolveGroup(fp: string) {
    await resolveErrors({ fingerprint: fp });
    load();
  }
  async function resolveOne(id: number) {
    await resolveErrors({ ids: [id] });
    load();
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded border text-sm">
          {(["groups", "flat"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 ${mode === m ? "bg-indigo-500 text-white" : "text-gray-600"}`}
            >
              {m === "groups" ? "묶음" : "전체"}
            </button>
          ))}
        </div>
        <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border px-2 py-1 text-sm">
          {SOURCES.map((s) => (
            <option key={s} value={s}>{s ? SOURCE_KO[s] : "모든 출처"}</option>
          ))}
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded border px-2 py-1 text-sm">
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s || "모든 심각도"}</option>
          ))}
        </select>
        {mode === "groups" && (
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
            {[1, 7, 30, 90].map((d) => (
              <option key={d} value={d}>최근 {d}일</option>
            ))}
          </select>
        )}
        <label className="flex items-center gap-1 text-sm text-gray-600">
          <input type="checkbox" checked={unresolved} onChange={(e) => setUnresolved(e.target.checked)} />
          미해결만
        </label>
        {mode === "groups" && (
          <span className="ml-auto text-xs text-gray-400">
            최근 {days}일 · 총 {counts.total}건 · 미해결 {counts.unresolved}건
          </span>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : mode === "groups" ? (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">출처</th>
                <th className="px-3 py-2 text-left">종류·메시지</th>
                <th className="px-3 py-2 text-right">발생</th>
                <th className="px-3 py-2 text-right">미해결</th>
                <th className="px-3 py-2 text-left">최종 발생(KST)</th>
                <th className="px-3 py-2 text-right">처리</th>
              </tr>
            </thead>
            <tbody>
              {groups.flatMap((g) => {
                const isOpen = g.fingerprint in open;
                const head = (
                  <tr key={g.fingerprint} className="cursor-pointer border-t hover:bg-gray-50" onClick={() => toggle(g.fingerprint)}>
                    <td className="px-3 py-2">
                      <span className={`rounded px-2 py-0.5 text-xs ${SRC_BADGE[g.source] ?? "bg-gray-100"}`}>
                        {SOURCE_KO[g.source] ?? g.source}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="mr-1 text-gray-400">{isOpen ? "▼" : "▶"}</span>
                      <span className="font-medium">{g.kind}</span>
                      <span className="ml-2 text-gray-500">{g.message}</span>
                      {g.path && <span className="ml-2 text-xs text-gray-400">{g.path}</span>}
                    </td>
                    <td className="px-3 py-2 text-right font-medium">{g.count}</td>
                    <td className={`px-3 py-2 text-right ${g.unresolved ? "text-rose-600" : "text-gray-400"}`}>{g.unresolved}</td>
                    <td className="px-3 py-2 text-gray-500">{ts(g.last_seen)}</td>
                    <td className="px-3 py-2 text-right">
                      {g.unresolved > 0 && (
                        <button
                          onClick={(e) => { e.stopPropagation(); resolveGroup(g.fingerprint); }}
                          className="rounded bg-gray-800 px-2 py-0.5 text-xs text-white hover:bg-gray-700"
                        >
                          해결
                        </button>
                      )}
                    </td>
                  </tr>
                );
                const detail = isOpen
                  ? [
                      <tr key={`${g.fingerprint}-d`} className="border-t bg-gray-50/40">
                        <td colSpan={6} className="px-3 py-2">
                          {open[g.fingerprint] === null ? (
                            <span className="text-xs text-gray-400">불러오는 중…</span>
                          ) : (
                            <div className="space-y-1">
                              {(open[g.fingerprint] ?? []).map((r) => (
                                <div key={r.id} className="rounded border bg-white px-2 py-1 text-xs">
                                  <span className="text-gray-400">{ts(r.created_at)}</span>
                                  {r.owner_id && <span className="ml-2 text-gray-500">{r.owner_id}</span>}
                                  {r.ref_id && <span className="ml-2 text-gray-400">ref:{r.ref_id}</span>}
                                  {r.resolved && <span className="ml-2 text-emerald-600">해결됨</span>}
                                  {r.detail && (
                                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[11px] text-gray-500">
                                      {r.detail}
                                    </pre>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>,
                    ]
                  : [];
                return [head, ...detail];
              })}
              {groups.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">에러 없음</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">발생(KST)</th>
                <th className="px-3 py-2 text-left">출처</th>
                <th className="px-3 py-2 text-left">종류·메시지</th>
                <th className="px-3 py-2 text-left">사용자/ref</th>
                <th className="px-3 py-2 text-right">처리</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t align-top">
                  <td className="px-3 py-2 text-gray-500">{ts(r.created_at)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs ${SRC_BADGE[r.source] ?? "bg-gray-100"}`}>
                      {SOURCE_KO[r.source] ?? r.source}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-medium">{r.kind}</span>
                    <span className="ml-2 text-gray-500">{r.message}</span>
                    {r.path && <span className="ml-2 text-xs text-gray-400">{r.path}</span>}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {r.owner_id ?? "-"}{r.ref_id ? ` · ${r.ref_id}` : ""}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.resolved ? (
                      <span className="text-xs text-emerald-600">해결됨</span>
                    ) : (
                      <button
                        onClick={() => resolveOne(r.id)}
                        className="rounded bg-gray-800 px-2 py-0.5 text-xs text-white hover:bg-gray-700"
                      >
                        해결
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">에러 없음</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
