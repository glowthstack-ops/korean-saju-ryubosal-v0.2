"use client";

// 리포트 폴링 + 열람 — 잡 상태를 주기적으로 조회하고, 완료 시 페이지 단위 뷰어로 표시한다.

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PdfExportButton } from "@/components/reports/PdfExportButton";
import { ReportPager, type ReportSection } from "@/components/reports/ReportPager";
import { getReportJob } from "@/lib/subjects";
import { themeLabel } from "@/lib/themes";
import type { ReportJobStatus } from "@/lib/types";

const POLL_MS = 3000;

interface ReportResultLike {
  sections?: ReportSection[];
  status?: string;
  meta?: Record<string, unknown>;
  spec?: { product_code?: string; topic?: string | null; subjects?: { label?: string }[] };
}

export default function ReportJobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const [job, setJob] = useState<ReportJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const j = await getReportJob(jobId);
        if (!alive) return;
        setJob(j);
        if (j.status === "completed" || j.status === "failed" || j.status === "on_hold") return;
        timer.current = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "상태 조회 실패");
      }
    }
    poll();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [jobId]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!job) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  if (job.status === "failed") {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-lg font-bold">생성에 실패했어요</h1>
        <p className="mt-2 text-sm text-gray-600">{job.error ?? "알 수 없는 오류"}</p>
        <p className="mt-2 text-xs text-gray-400">
          풀이 엔진(LLM) 설정이 필요한 경우일 수 있어요. 잠시 후 다시 시도하거나 관리자에게 문의해
          주세요.
        </p>
      </section>
    );
  }

  if (job.status !== "completed") {
    const pct =
      job.sections_total > 0 ? Math.round((job.sections_done / job.sections_total) * 100) : 0;
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-lg font-bold">풀이를 작성하고 있어요</h1>
        <p className="mt-1 text-sm text-gray-500">
          {job.status === "queued" ? "대기 중" : "작성 중"} · {job.sections_done}/
          {job.sections_total} 장
        </p>
        <div className="mt-3 h-2 w-full overflow-hidden rounded bg-gray-100">
          <div className="h-full bg-gray-800 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-2 text-xs text-gray-400">완료되면 자동으로 표시됩니다(닫지 마세요).</p>
      </section>
    );
  }

  const result = (job.result ?? {}) as ReportResultLike;
  const sections = result.sections ?? [];
  const spec = result.spec;
  const heading = spec ? themeLabel(spec.product_code ?? "", spec.topic ?? null) : "풀이 결과";
  const who = spec?.subjects?.map((s) => s.label).filter(Boolean).join(", ");
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between print:hidden">
        <div>
          <h1 className="text-xl font-bold">
            {heading}
            {who && <span className="ml-2 text-sm font-normal text-gray-500">· {who}</span>}
          </h1>
        </div>
        <PdfExportButton />
      </div>
      {result.status === "on_hold" && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-700">
          현재 준비 중인 내용이 있어 일부만 표시됩니다. 곧 완성된 풀이로 업데이트돼요.
        </p>
      )}
      <ReportPager sections={sections} title="테마사주 풀이" />
    </div>
  );
}
