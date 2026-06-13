"use client";

// 온보딩 호스트 — ?mode=add|edit|oneoff&subject=&next= 로 위저드를 구동한다.
// useSearchParams는 Suspense 경계가 필요(Next 14)하므로 내부 컴포넌트를 감싼다.

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Wizard } from "@/components/onboarding/Wizard";

function OnboardingInner() {
  const params = useSearchParams();
  const { ready, isLoggedIn } = useAuth();
  const router = useRouter();

  const rawMode = params.get("mode");
  const next = params.get("next") ?? "/sajus";
  const subject = params.get("subject") ?? undefined;
  // 비로그인은 add/edit 불가 → oneoff(IndexedDB 1회성)로 강등.
  const mode = (rawMode === "edit" || rawMode === "oneoff" ? rawMode : "add") as
    | "add"
    | "edit"
    | "oneoff";

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;

  if (!isLoggedIn && mode !== "oneoff") {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">사주 등록</h1>
        <p className="mt-2 text-sm text-gray-600">
          사주를 저장해 여러 개를 관리하려면 로그인이 필요해요. 좌측 메뉴(☰)에서 아이디·PIN으로
          로그인하거나, 비회원으로 한 번만 보려면 만세력에서 시작해 주세요.
        </p>
        <button
          onClick={() => router.push("/manse")}
          className="mt-3 rounded border px-3 py-1.5 text-sm"
        >
          만세력으로 가기
        </button>
      </section>
    );
  }

  return <Wizard mode={mode} subjectId={subject} next={next} />;
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<p className="text-sm text-gray-500">불러오는 중…</p>}>
      <OnboardingInner />
    </Suspense>
  );
}
