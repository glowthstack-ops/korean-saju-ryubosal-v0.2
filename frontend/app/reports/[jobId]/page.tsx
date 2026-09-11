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

/** PDF 저장 파일명 — 내용 식별용: 테마·대상·작성시점·짧은 코드 (2026-08-24 사용자 요청). */
function reportFileName(
  heading: string,
  who: string | undefined,
  createdAt: string | null | undefined,
  jobId: string,
): string {
  const dt = createdAt ? new Date(createdAt) : new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${String(dt.getFullYear()).slice(2)}${p(dt.getMonth() + 1)}${p(
    dt.getDate(),
  )}-${p(dt.getHours())}${p(dt.getMinutes())}`;
  const code = jobId.replace(/-/g, "").slice(0, 6).toUpperCase();
  return ["테마사주", heading, who, stamp, code]
    .filter(Boolean)
    .join("_")
    .replace(/[\\/:*?"<>|]/g, "")
    .replace(/\s+/g, "");
}

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

  // 완료 시 탭 제목 = 파일명 — 버튼 없이 Ctrl+P 로 저장해도 같은 이름이 되게 한다.
  useEffect(() => {
    if (job?.status !== "completed") return;
    const r = (job.result ?? {}) as ReportResultLike;
    const h = r.spec ? themeLabel(r.spec.product_code ?? "", r.spec.topic ?? null) : "풀이 결과";
    const w = r.spec?.subjects?.map((s) => s.label).filter(Boolean).join(",");
    document.title = reportFileName(h, w, job.created_at, jobId);
  }, [job, jobId]);

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
        <p className="mt-2 text-xs text-gray-400">
          이 페이지를 닫아도 작성은 계속돼요. 완료되면 알림으로 알려드리고, 언제든
          <span className="font-medium"> 내 풀이 내역</span>에서 다시 볼 수 있어요.
        </p>
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
        <PdfExportButton filename={reportFileName(heading, who, job.created_at, jobId)} />
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
