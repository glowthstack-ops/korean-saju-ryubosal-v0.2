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
  // 스크롤 방향에 따라 top bar 숨김/표시(아래로 스크롤=숨김, 위로 스크롤=표시).
  const [hidden, setHidden] = useState(false);
  const pathname = usePathname();
  const { isLoggedIn } = useAuth();
  const { selected } = useSelectedSubject();

  // 라우트 이동 시 자동으로 닫고, 헤더를 다시 보이게 한다.
  useEffect(() => {
    setOpen(false);
    setHidden(false);
  }, [pathname]);

  // 스크롤 방향 감지 — 일정 거리 아래로 내려가면 숨기고, 위로 올리면 즉시 표시.
  useEffect(() => {
    let last = window.scrollY;
    let ticking = false;
    const THRESHOLD = 8; // 미세 떨림 무시
    const TOP_GUARD = 64; // 최상단 근처에서는 항상 표시
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        if (Math.abs(y - last) > THRESHOLD) {
          setHidden(y > last && y > TOP_GUARD);
          last = y;
        }
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header
        className={`sticky top-0 z-30 border-b bg-white transition-transform duration-300 ${
          hidden && !open ? "-translate-y-full" : "translate-y-0"
        }`}
      >
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
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

      {/* 드로어는 항상 마운트하고 클래스로 전환 — 열림/닫힘 모두 슬라이드 애니메이션. */}
      <div
        className={`fixed inset-0 z-40 ${open ? "" : "pointer-events-none"}`}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
      >
        <div
          className={`absolute inset-0 bg-black/40 transition-opacity duration-300 ${
            open ? "opacity-100" : "opacity-0"
          }`}
          onClick={() => setOpen(false)}
        />
        <aside
          className={`absolute left-0 top-0 flex h-full w-80 max-w-[85vw] flex-col bg-white shadow-xl transition-transform duration-300 ease-out ${
            open ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {/* 스크롤 영역(메뉴) — 카피라이트는 아래 고정 */}
          <div className="flex-1 overflow-y-auto">
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

            <div className="border-t px-2 py-2">
              {isLoggedIn && (
                <Link
                  href="/reports"
                  className="block rounded px-2 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  내 풀이 내역
                </Link>
              )}
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
          </div>

          {/* 카피라이트 — 드로어 최하단 고정 */}
          <div className="shrink-0 border-t bg-white px-4 py-3 text-center text-[11px] text-gray-400">
            © 류보살
          </div>
        </aside>
      </div>
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
