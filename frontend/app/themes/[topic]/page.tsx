"use client";

// 테마별 시작 — 사주(+동반자) 선택 게이트웨이 → 리포트 잡 생성 → 폴링 페이지로 이동.

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { SubjectGateway } from "@/components/subject/SubjectGateway";
import { buildReportSpec, themeBySlug } from "@/lib/themes";
import { createReportJob } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

export default function ThemeStartPage() {
  const router = useRouter();
  const params = useParams<{ topic: string }>();
  const theme = themeBySlug(params.topic);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!theme) {
    return <p className="text-sm text-red-500">알 수 없는 테마입니다.</p>;
  }

  async function start(primary: SubjectSummary, companion?: SubjectSummary) {
    if (!theme) return;
    setBusy(true);
    setError(null);
    try {
      const spec = buildReportSpec(theme, primary, companion);
      const { job_id } = await createReportJob(primary.subject_id, spec);
      router.push(`/reports/${job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성 요청 실패");
      setBusy(false);
    }
  }

  if (busy) return <p className="text-sm text-gray-500">풀이 생성을 시작하는 중…</p>;

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-bold">
          {theme.title} <span className="text-sm font-normal text-gray-400">{theme.scope}</span>
        </h1>
        <p className="mt-1 text-sm text-gray-500">{theme.desc}</p>
      </div>
      <SubjectGateway
        title="사주 선택"
        returnTo={`/themes/${theme.slug}`}
        companionMode={theme.companionMode}
        onResolved={start}
      />
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
