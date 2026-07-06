"use client";

// 테마사주 서브메인 — 초기 4종(총운·궁합·직장운·금전/횡재운). 로그인 전용.

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { THEMES } from "@/lib/themes";

export default function ThemesPage() {
  const { ready, isLoggedIn } = useAuth();

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;
  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">테마사주</h1>
        <p className="mt-2 text-sm text-gray-600">
          테마사주는 로그인 후 이용할 수 있어요. 좌측 메뉴(☰)에서 아이디·PIN으로 로그인해 주세요.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">테마사주</h1>
        <p className="mt-1 text-sm text-gray-500">
          궁금한 주제를 고르면 내 사주로 깊이 있는 풀이를 만들어 드려요. 완성된 풀이는 목차별로
          차근차근 읽고, PDF로 저장해 두고두고 볼 수 있어요.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {THEMES.map((t) => (
          <Link
            key={t.slug}
            href={`/themes/${t.slug}`}
            className="rounded-lg border bg-white p-6 shadow-sm transition hover:shadow"
          >
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold">{t.title}</h2>
              <span className="text-xs text-gray-400">{t.scope}</span>
            </div>
            <p className="mt-1 text-sm text-gray-500">{t.desc}</p>
            {t.companionMode !== "none" && (
              <p className="mt-2 text-xs text-gray-400">
                {t.companionMode === "required" ? "동반자 필요" : "상대 추가 선택 가능"}
              </p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
