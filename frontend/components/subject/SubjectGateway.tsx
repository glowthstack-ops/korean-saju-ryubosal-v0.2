"use client";

// 대상 선택 게이트웨이 — 모든 서비스(만세력·테마·채팅)가 "누구의 사주인가"를 확정하는 1차 관문.
// 로그인 사용자의 사주목록에서 선택하거나 새 사주를 추가하고, 필요 시 동반자(궁합/관계)를 함께
// 고른다. 선택 결과는 전역 컨텍스트에 반영하고 onResolved로 호출자에게 전달한다.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { SubjectCard } from "@/components/subject/SubjectCard";
import { listSubjects } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

// 동반자 선택 정책: none=단독 / optional=상대 추가 선택 가능(내 명식만도 가능) / required=상대 필수.
type CompanionMode = "none" | "optional" | "required";

interface Props {
  /** 동반자(2번째 사주) 선택 정책. 미지정 시 requireCompanion로 호환. */
  companionMode?: CompanionMode;
  /** (레거시) 동반자 선택 강제 — companionMode 미지정 시 사용. */
  requireCompanion?: boolean;
  /** 추가 완료 후 돌아올 경로(온보딩 next). */
  returnTo: string;
  title?: string;
  onResolved: (primary: SubjectSummary, companion?: SubjectSummary) => void;
}

export function SubjectGateway({
  companionMode, requireCompanion, returnTo, title, onResolved,
}: Props) {
  const mode: CompanionMode = companionMode ?? (requireCompanion ? "required" : "none");
  const { ready, isLoggedIn } = useAuth();
  const { setSelected, setCompanion } = useSelectedSubject();
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [primary, setPrimary] = useState<SubjectSummary | null>(null);

  useEffect(() => {
    if (!isLoggedIn) {
      setSubjects([]);
      return;
    }
    listSubjects()
      .then(setSubjects)
      .catch((e) => setError(e instanceof Error ? e.message : "목록을 불러오지 못했습니다."));
  }, [isLoggedIn]);

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;

  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">{title ?? "사주 선택"}</h2>
        <p className="mt-2 text-sm text-gray-600">
          이 서비스는 로그인 후 이용할 수 있어요. 좌측 메뉴(☰)에서 아이디·PIN으로 로그인하거나 새
          계정을 만들어 주세요. 같은 아이디·PIN이면 어느 기기에서나 사주목록이 이어집니다.
        </p>
      </section>
    );
  }

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (subjects === null) return <p className="text-sm text-gray-500">사주목록 불러오는 중…</p>;

  const addHref = `/onboarding?mode=add&next=${encodeURIComponent(returnTo)}`;

  // 동반자 선택 단계(optional·required).
  if (mode !== "none" && primary) {
    const others = subjects.filter((s) => s.subject_id !== primary.subject_id);
    const optional = mode === "optional";
    return (
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">
          {optional ? "상대 선택 (선택)" : "동반자 선택"}
        </h2>
        <p className="text-sm text-gray-600">
          <span className="font-medium">{primary.label}</span>님과 함께 볼 상대를 골라 주세요.
          {optional && " 상대를 더하면 두 사람의 궁합·극복 전략까지 풀이합니다."}
        </p>
        {optional && (
          <button
            onClick={() => {
              setCompanion(null);
              onResolved(primary);
            }}
            className="w-full rounded-lg border border-indigo-300 bg-indigo-50 px-4 py-3 text-left text-sm font-medium text-indigo-700 hover:bg-indigo-100"
          >
            상대 없이 내 명식만으로 보기 →
          </button>
        )}
        {others.length === 0 ? (
          <p className="text-sm text-gray-500">
            등록된 다른 사주가 없어요.{" "}
            <Link href={addHref} className="text-blue-600 hover:underline">
              동반자 사주 추가
            </Link>
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {others.map((s) => (
              <SubjectCard
                key={s.subject_id}
                subject={s}
                onSelect={(comp) => {
                  setCompanion({ subjectId: comp.subject_id, label: comp.label });
                  onResolved(primary, comp);
                }}
              />
            ))}
          </div>
        )}
        <button
          onClick={() => setPrimary(null)}
          className="text-xs text-gray-500 hover:underline"
        >
          ← 본인 사주 다시 선택
        </button>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title ?? "사주 선택"}</h2>
        <Link href={addHref} className="text-sm text-blue-600 hover:underline">
          + 새 사주
        </Link>
      </div>
      {subjects.length === 0 ? (
        <p className="rounded-lg bg-white p-6 text-sm text-gray-500 shadow-sm">
          등록된 사주가 없어요.{" "}
          <Link href={addHref} className="text-blue-600 hover:underline">
            새 사주 추가하기
          </Link>
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {subjects.map((s) => (
            <SubjectCard
              key={s.subject_id}
              subject={s}
              onSelect={(picked) => {
                setSelected({ subjectId: picked.subject_id, label: picked.label });
                if (mode !== "none") setPrimary(picked);
                else onResolved(picked);
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
