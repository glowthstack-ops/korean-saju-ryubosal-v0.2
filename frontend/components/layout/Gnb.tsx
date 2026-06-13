"use client";

// GNB — 햄버거 버튼 → 좌측 슬라이드 드로어. 현재 선택 사주 칩, 서비스 메뉴(무료/유료),
// 사주목록·설정, 계정(ID+PIN) 패널을 담는다. 유료 항목은 비로그인 시 안내 뱃지를 단다.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthPanel } from "@/components/layout/AuthPanel";
import { useAuth } from "@/components/providers/AuthProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";

interface NavItem {
  href: string;
  label: string;
  desc: string;
  paid?: boolean;
}

const FREE: NavItem[] = [
  { href: "/manse", label: "만세력", desc: "원국·대운·세운·용신" },
  { href: "/calendar", label: "간지달력", desc: "날짜별 간지·절기" },
];
const PAID: NavItem[] = [
  { href: "/themes", label: "테마사주", desc: "총운·궁합·직장·금전 풀이" },
  { href: "/chat", label: "AI채팅상담", desc: "대화형 통변" },
];

export function Gnb() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { isLoggedIn } = useAuth();
  const { selected } = useSelectedSubject();

  // 라우트 이동 시 자동으로 닫는다.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <>
      <header className="sticky top-0 z-30 border-b bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <button
            aria-label="메뉴 열기"
            onClick={() => setOpen(true)}
            className="rounded p-1 text-gray-700 hover:bg-gray-100"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeWidth="2" strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <Link href="/" className="text-lg font-bold">
            류보살 <span className="text-gray-400">v2</span>
          </Link>
          {selected && (
            <span className="ml-auto truncate rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">
              {selected.label} 기준
            </span>
          )}
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-80 max-w-[85vw] overflow-y-auto bg-white shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <span className="font-semibold">메뉴</span>
              <button
                aria-label="메뉴 닫기"
                onClick={() => setOpen(false)}
                className="rounded p-1 text-gray-500 hover:bg-gray-100"
              >
                ✕
              </button>
            </div>

            <div className="border-b px-4 py-3">
              <p className="mb-1 text-xs font-medium text-gray-400">현재 선택된 사주</p>
              {selected ? (
                <p className="text-sm font-medium">{selected.label}</p>
              ) : (
                <p className="text-sm text-gray-400">선택된 사주 없음</p>
              )}
              <Link href="/sajus" className="mt-2 inline-block text-xs text-blue-600 hover:underline">
                사주목록 관리 →
              </Link>
            </div>

            <nav className="px-2 py-2">
              <p className="px-2 py-1 text-xs font-medium text-gray-400">무료</p>
              {FREE.map((it) => (
                <DrawerLink key={it.href} item={it} loggedIn={isLoggedIn} />
              ))}
              <p className="mt-2 px-2 py-1 text-xs font-medium text-gray-400">로그인 전용</p>
              {PAID.map((it) => (
                <DrawerLink key={it.href} item={it} loggedIn={isLoggedIn} />
              ))}
            </nav>

            <div className="border-t px-4 py-3">
              <Link
                href="/settings"
                className="block rounded px-2 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                설정(페르소나·물상해석)
              </Link>
            </div>

            <div className="border-t px-4 py-4">
              <AuthPanel />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

function DrawerLink({ item, loggedIn }: { item: NavItem; loggedIn: boolean }) {
  const locked = item.paid && !loggedIn;
  return (
    <Link
      href={item.href}
      className="flex items-center justify-between rounded px-2 py-2 hover:bg-gray-50"
    >
      <span>
        <span className="block text-sm font-medium">{item.label}</span>
        <span className="block text-xs text-gray-400">{item.desc}</span>
      </span>
      {locked && (
        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-600">
          로그인 필요
        </span>
      )}
    </Link>
  );
}
