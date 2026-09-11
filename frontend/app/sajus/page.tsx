"use client";

// 사주목록(관리) — 별명·생년월일시·용신/물상 등록여부 표시, 추가/수정/삭제.
// 삭제는 스낵바 '되돌리기'로 취소 가능(미취소 시 일정 시간 후 실제 삭제 반영).
// 비로그인 진입은 안내 페이지를 보여주지 않고 홈으로 돌려보내며 사이드바(계정 패널)를 연다.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useGnb } from "@/components/providers/GnbProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { SubjectCard } from "@/components/subject/SubjectCard";
import { deleteSubject, listSubjects } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

const UNDO_MS = 5000;

export default function SajusPage() {
  const router = useRouter();
  const { ready, isLoggedIn } = useAuth();
  const { openGnb } = useGnb();
  const { selected, setSelected, reconcile } = useSelectedSubject();
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<SubjectSummary | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    listSubjects()
      .then((list) => {
        setSubjects(list);
        // 서버 진실과 대조 — 목록에 없는(삭제됐거나 이전 로그인의) 선택을 정리한다.
        reconcile(list.map((s) => s.subject_id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "목록을 불러오지 못했습니다."));
  }, [reconcile]);

  useEffect(() => {
    if (isLoggedIn) load();
    else setSubjects([]);
  }, [isLoggedIn, load]);

  // 비로그인 확정 시 홈으로 이동 + 사이드바 열기(로그인 항목이 바로 보이도록).
  useEffect(() => {
    if (ready && !isLoggedIn) {
      router.replace("/");
      openGnb();
    }
  }, [ready, isLoggedIn, router, openGnb]);

  // 실제 삭제 커밋(타이머 만료 또는 다른 삭제 시작 시).
  const commitDelete = useCallback((s: SubjectSummary) => {
    deleteSubject(s.subject_id).catch(() => load());
    if (selected?.subjectId === s.subject_id) setSelected(null);
  }, [load, selected, setSelected]);

  const startDelete = useCallback(
    (s: SubjectSummary) => {
      if (timer.current) clearTimeout(timer.current);
      if (pending) commitDelete(pending); // 직전 보류 건 즉시 확정
      setSubjects((prev) => (prev ? prev.filter((x) => x.subject_id !== s.subject_id) : prev));
      setPending(s);
      timer.current = setTimeout(() => {
        commitDelete(s);
        setPending(null);
      }, UNDO_MS);
    },
    [pending, commitDelete],
  );

  const undo = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    if (pending) setSubjects((prev) => (prev ? [...prev, pending] : [pending]));
    setPending(null);
  }, [pending]);

  if (!ready || !isLoggedIn) return <p className="text-sm text-gray-500">확인 중…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">사주목록</h1>
        <Link
          href="/onboarding?mode=add&next=/sajus"
          className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white"
        >
          + 사주 추가
        </Link>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {subjects === null ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : subjects.length === 0 ? (
        <p className="rounded-lg bg-white p-6 text-sm text-gray-500 shadow-sm">
          등록된 사주가 없어요. 위 &lsquo;사주 추가&rsquo;로 시작해 보세요.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {subjects.map((s) => (
            <SubjectCard
              key={s.subject_id}
              subject={s}
              active={selected?.subjectId === s.subject_id}
              onSelect={(picked) => setSelected({ subjectId: picked.subject_id, label: picked.label })}
              onEdit={(x) =>
                router.push(`/onboarding?mode=edit&subject=${x.subject_id}&next=/sajus`)
              }
              onDelete={startDelete}
            />
          ))}
        </div>
      )}

      {pending && (
        <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg">
          <span>&lsquo;{pending.label}&rsquo; 삭제됨</span>
          <button onClick={undo} className="font-semibold text-blue-300 hover:underline">
            되돌리기
          </button>
        </div>
      )}
    </div>
  );
}
