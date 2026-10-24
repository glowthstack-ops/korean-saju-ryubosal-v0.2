"use client";

// 현실 신호 캘리브레이션 — 과거 실제 사건 수집(LEI §5). 온보딩 외에 설정·결과 페이지에서 재진입.

import Link from "next/link";
import { useEffect, useState } from "react";

import { EmploymentHistoryForm } from "@/components/onboarding/EmploymentHistoryForm";
import { StepRealityCalibration } from "@/components/onboarding/StepRealityCalibration";
import { useAuth } from "@/components/providers/AuthProvider";
import { type CalibrationMode, listSubjects } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

export default function RealityCalibrationPage() {
  const { ready, isLoggedIn } = useAuth();
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [summary, setSummary] = useState<string[]>([]);
  // 탭: 연도별 사건(캘리브레이션) | 직장 이력(자격득실 수준 입퇴사 — 정본)
  const [tab, setTab] = useState<"events" | "employment">("events");
  // 연 1회 갱신 설문(2026-10-24): ?mode=refresh 면 마지막 입력 이후 해만 묻는다.
  const [mode, setMode] = useState<CalibrationMode>("full");

  useEffect(() => {
    if (!isLoggedIn) return;
    listSubjects()
      .then((s) => {
        setSubjects(s);
        const qs = new URLSearchParams(window.location.search);
        const param = qs.get("subject");
        setActiveId(param || s[0]?.subject_id || null);
        if (qs.get("mode") === "refresh") setMode("refresh");
      })
      .catch(() => {});
  }, [isLoggedIn]);

  if (!ready) return null;
  if (!isLoggedIn) {
    return <main className="mx-auto max-w-xl p-6 text-sm">로그인이 필요합니다.</main>;
  }

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-lg font-semibold">
        현실 신호 캘리브레이션{mode === "refresh" ? " — 최근 해 추가" : ""}
      </h1>
      {mode === "refresh" && (
        <button
          type="button"
          onClick={() => setMode("full")}
          className="text-xs text-zinc-500 underline"
        >
          전체 연도 보기·수정
        </button>
      )}
      <p className="text-sm text-zinc-600">
        과거에 실제로 있었던 일을 알려주시면 그 사주에 맞춰 풀이 정확도가 올라갑니다. 전부 선택 사항입니다.
      </p>
      {subjects.length > 1 && (
        <select
          aria-label="사주 선택"
          className="rounded border px-2 py-1.5 text-sm"
          value={activeId ?? ""}
          onChange={(e) => {
            setActiveId(e.target.value);
            setDone(false);
          }}
        >
          {subjects.map((s) => (
            <option key={s.subject_id} value={s.subject_id}>
              {s.label}
            </option>
          ))}
        </select>
      )}
      <div className="flex gap-1 text-sm" role="tablist" aria-label="입력 종류">
        {(
          [
            ["events", "연도별 사건"],
            ["employment", "직장 이력"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key);
              setDone(false);
            }}
            className={`rounded px-3 py-1.5 ${
              tab === key ? "bg-zinc-900 text-white" : "border border-zinc-300 text-zinc-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {done ? (
        <div className="space-y-3 text-sm">
          <p className="text-green-700">저장됐습니다. 풀이에 반영됩니다.</p>
          {summary.length > 0 && (
            <ul className="space-y-1 rounded bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
              {summary.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-3">
            {/* 재편집 — 다시 열면 이전 입력이 그대로 채워진 상태로 수정할 수 있다(prior 프리필). */}
            <button
              type="button"
              onClick={() => setDone(false)}
              className="rounded border border-zinc-300 px-3 py-1.5 text-zinc-700 hover:bg-zinc-50"
            >
              수정하기
            </button>
            <Link href="/chat" className="underline">
              채팅으로 가기
            </Link>
          </div>
        </div>
      ) : activeId && tab === "employment" ? (
        <EmploymentHistoryForm
          key={`eh-${activeId}`}
          subjectId={activeId}
          onDone={(r) => {
            setSummary(r?.summary ?? []);
            setDone(true);
          }}
        />
      ) : activeId ? (
        <StepRealityCalibration
          key={`${activeId}-${mode}`}
          subjectId={activeId}
          mode={mode}
          onDone={(r) => {
            setSummary(r?.summary ?? []);
            setDone(true);
          }}
        />
      ) : (
        <p className="text-sm text-zinc-500">등록된 사주가 없습니다.</p>
      )}
    </main>
  );
}
