"use client";

// 현실 신호 캘리브레이션 — 과거 실제 사건 수집(LEI §5). 온보딩 외에 설정·결과 페이지에서 재진입.

import Link from "next/link";
import { useEffect, useState } from "react";

import { StepRealityCalibration } from "@/components/onboarding/StepRealityCalibration";
import { useAuth } from "@/components/providers/AuthProvider";
import { listSubjects } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

export default function RealityCalibrationPage() {
  const { ready, isLoggedIn } = useAuth();
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isLoggedIn) return;
    listSubjects()
      .then((s) => {
        setSubjects(s);
        const param = new URLSearchParams(window.location.search).get("subject");
        setActiveId(param || s[0]?.subject_id || null);
      })
      .catch(() => {});
  }, [isLoggedIn]);

  if (!ready) return null;
  if (!isLoggedIn) {
    return <main className="mx-auto max-w-xl p-6 text-sm">로그인이 필요합니다.</main>;
  }

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-lg font-semibold">현실 신호 캘리브레이션</h1>
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
      {done ? (
        <div className="space-y-3 text-sm">
          <p className="text-green-700">저장됐습니다. 풀이에 반영됩니다.</p>
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
      ) : activeId ? (
        <StepRealityCalibration
          key={activeId}
          subjectId={activeId}
          onDone={() => setDone(true)}
        />
      ) : (
        <p className="text-sm text-zinc-500">등록된 사주가 없습니다.</p>
      )}
    </main>
  );
}
