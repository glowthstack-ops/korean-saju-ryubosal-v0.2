"use client";

// 테마별 시작 — 사주(+동반자) 선택 게이트웨이 → 리포트 잡 생성 → 폴링 페이지로 이동.

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { SubjectGateway } from "@/components/subject/SubjectGateway";
import { buildReportSpec, themeBySlug, type CompanionChoice } from "@/lib/themes";
import { createReportJob } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

export default function ThemeStartPage() {
  const router = useRouter();
  const params = useParams<{ topic: string }>();
  const theme = themeBySlug(params.topic);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 한해풀이 진입 시 년도 선택 — 기본값 올해, 선택 범위 올해~+5년.
  const thisYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 6 }, (_, i) => thisYear + i);
  const [year, setYear] = useState(thisYear);

  if (!theme) {
    return <p className="text-sm text-red-500">알 수 없는 테마입니다.</p>;
  }

  async function start(primary: SubjectSummary, companion?: CompanionChoice) {
    if (!theme) return;
    setBusy(true);
    setError(null);
    try {
      const spec = buildReportSpec(theme, primary, companion, year);
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
      {theme.needsYear && (
        <label className="flex items-center gap-2 rounded-lg border bg-white p-4 shadow-sm">
          <span className="text-sm font-medium">풀이할 해</span>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded border px-2 py-1 text-sm"
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>
                {y}년{y === thisYear ? " (올해)" : ""}
              </option>
            ))}
          </select>
        </label>
      )}
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
