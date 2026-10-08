"use client";

// 내 풀이 내역(로그인 전용) — 생성한 테마사주 풀이(구매·결과)를 다시 보고 PDF로 출력한다.
// 각 항목은 상세 뷰어(/reports/[jobId])로 연결되며, 거기서 페이지 열람·PDF 인쇄가 가능하다.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useReportNotifications } from "@/components/providers/ReportNotificationsProvider";
import { listReportJobs } from "@/lib/subjects";
import { themeLabel } from "@/lib/themes";
import type { ReportJobSummary } from "@/lib/types";

const STATUS_KO: Record<ReportJobSummary["status"], { label: string; cls: string }> = {
  queued: { label: "대기 중", cls: "bg-gray-100 text-gray-500" },
  running: { label: "작성 중", cls: "bg-blue-50 text-blue-600" },
  completed: { label: "완료", cls: "bg-emerald-50 text-emerald-600" },
  on_hold: { label: "보완 중", cls: "bg-amber-50 text-amber-600" },
  failed: { label: "실패", cls: "bg-red-50 text-red-500" },
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 16).replace("T", " ");
}

/** 기간 표시 — 한해풀이는 연도만('2027년, 입춘~입춘'), 그 외는 'YYYY-MM~YYYY-MM'. */
function periodLabel(j: ReportJobSummary): string {
  const s = j.period_start ?? null;
  const e = j.period_end ?? null;
  if (!s) return "";
  if (j.product_code === "RPT_YEAR") return `${s.slice(0, 4)}년`;
  if (j.product_code === "RPT_FULL") return "인생 전반";
  return e ? `${s}~${e}` : s;
}

/** 대상 표시 — '데굴(본인) · 민수(연인)'. 구 저장분(subjects 없음)은 라벨만. */
function subjectsLabel(j: ReportJobSummary): string {
  if (j.subjects && j.subjects.length > 0) {
    return j.subjects.map((s) => `${s.label}(${s.relation_label})`).join(" · ");
  }
  return j.subject_labels.join(", ");
}

export default function ReportsHistoryPage() {
  const { ready, isLoggedIn } = useAuth();
  const { markReportsSeen } = useReportNotifications();
  const [jobs, setJobs] = useState<ReportJobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn) {
      setJobs([]);
      return;
    }
    listReportJobs()
      .then(setJobs)
      .catch((e) => setError(e instanceof Error ? e.message : "내역을 불러오지 못했습니다."));
    // 내역을 열람하면 완료 알림 뱃지를 해제한다.
    markReportsSeen();
  }, [isLoggedIn, markReportsSeen]);

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;
  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">내 풀이 내역</h1>
        <p className="mt-2 text-sm text-gray-600">
          로그인하면 구매·생성한 풀이를 다시 보고 PDF로 저장할 수 있어요. 좌측 메뉴(☰)에서 로그인해
          주세요.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">내 풀이 내역</h1>
        <Link href="/themes" className="text-sm text-blue-600 hover:underline">
          + 새 풀이
        </Link>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {jobs === null ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : jobs.length === 0 ? (
        <p className="rounded-lg bg-white p-6 text-sm text-gray-500 shadow-sm">
          아직 생성한 풀이가 없어요.{" "}
          <Link href="/themes" className="text-blue-600 hover:underline">
            테마사주에서 시작하기
          </Link>
        </p>
      ) : (
        <ul className="space-y-2">
          {jobs.map((j) => {
            const st = STATUS_KO[j.status];
            return (
              <li key={j.job_id}>
                {/* 완료=열람/PDF, 진행 중=폴링, 실패=사유 — 모두 상세 페이지에서 처리. */}
                <Link
                  href={`/reports/${j.job_id}`}
                  className="block transition hover:opacity-90"
                >
                  <div className="flex items-center justify-between gap-3 rounded-lg border bg-white p-4 shadow-sm">
                    <div className="min-w-0">
                      <p className="font-semibold">
                        {themeLabel(j.product_code, j.topic)}
                        {periodLabel(j) && (
                          <span className="ml-1 text-sm font-normal text-gray-600">· {periodLabel(j)}</span>
                        )}
                      </p>
                      {/* 선택값(대상·관계) — 같은 테마가 여러 건일 때 구분용(2026-10-08). */}
                      <p className="mt-0.5 truncate text-sm text-gray-500">{subjectsLabel(j)}</p>
                      <p className="mt-0.5 text-xs text-gray-400">{formatDate(j.created_at)}</p>
                    </div>
                    <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${st.cls}`}>
                      {st.label}
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
