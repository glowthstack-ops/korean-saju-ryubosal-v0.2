"use client";

// 운영 관리자 콘솔 레이아웃 — 로그인 + 관리자 권한 가드, 좌측 탭 네비.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { getOverview } from "@/lib/admin";

const TABS = [
  { href: "/admin", label: "개요" },
  { href: "/admin/usage", label: "사용량·비용" },
  { href: "/admin/events", label: "이벤트(잡)" },
  { href: "/admin/errors", label: "에러 로그" },
  { href: "/admin/pricing", label: "단가·환율" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { ready, isLoggedIn } = useAuth();
  const pathname = usePathname();
  const [access, setAccess] = useState<"checking" | "ok" | "denied">("checking");

  useEffect(() => {
    if (!ready || !isLoggedIn) return;
    getOverview()
      .then(() => setAccess("ok"))
      .catch(() => setAccess("denied"));
  }, [ready, isLoggedIn]);

  if (!ready) return <p className="text-sm text-gray-500">확인 중…</p>;
  if (!isLoggedIn) {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">운영 콘솔</h1>
        <p className="mt-2 text-sm text-gray-600">
          관리자 로그인이 필요해요. 좌측 메뉴(☰)에서 로그인해 주세요.
        </p>
      </section>
    );
  }
  if (access === "denied") {
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">운영 콘솔</h1>
        <p className="mt-2 text-sm text-red-500">관리자 권한이 없는 계정이에요.</p>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">운영 콘솔</h1>
      <nav className="flex gap-1 border-b">
        {TABS.map((t) => {
          const active = pathname === t.href;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`px-3 py-2 text-sm ${
                active
                  ? "border-b-2 border-indigo-500 font-semibold text-indigo-600"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {access === "checking" ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : (
        children
      )}
    </div>
  );
}
