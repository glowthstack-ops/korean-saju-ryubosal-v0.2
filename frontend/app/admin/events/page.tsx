"use client";

// 서버 이벤트 — 리포트(테마사주) 잡 목록(상태 필터).

import { useEffect, useState } from "react";
import { getEvents, type JobRow } from "@/lib/admin";

const STATUSES = ["", "queued", "running", "completed", "on_hold", "failed"];
const BADGE: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  on_hold: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  running: "bg-blue-100 text-blue-700",
  queued: "bg-gray-100 text-gray-600",
};

export default function AdminEventsPage() {
  const [status, setStatus] = useState("");
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getEvents(status || undefined, 200)
      .then((d) => setJobs(d.jobs))
      .finally(() => setLoading(false));
  }, [status]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500">상태</span>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded border px-2 py-1 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "전체"}
            </option>
          ))}
        </select>
      </div>
      {loading ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">생성</th>
                <th className="px-3 py-2 text-left">상품</th>
                <th className="px-3 py-2 text-left">사용자</th>
                <th className="px-3 py-2 text-left">상태</th>
                <th className="px-3 py-2 text-right">진행</th>
                <th className="px-3 py-2 text-left">오류</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="border-t">
                  <td className="px-3 py-2 text-gray-500">
                    {j.created_at?.slice(0, 16).replace("T", " ")}
                  </td>
                  <td className="px-3 py-2">{j.product_code ?? "-"}</td>
                  <td className="px-3 py-2 text-gray-600">{j.owner_id}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs ${BADGE[j.status] ?? ""}`}>
                      {j.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-gray-500">
                    {j.sections_done}/{j.sections_total}
                  </td>
                  <td className="max-w-xs truncate px-3 py-2 text-red-500">{j.error ?? ""}</td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-gray-400">
                    잡 없음
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
