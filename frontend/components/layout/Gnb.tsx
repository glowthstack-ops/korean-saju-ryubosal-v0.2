"use client";

// GNB — 햄버거 버튼 → 좌측 슬라이드 드로어. 현재 선택 사주 칩, 서비스 메뉴(무료/유료),
// 사주목록·설정, 계정(ID+PIN) 패널을 담는다. 유료 항목은 비로그인 시 안내 뱃지를 단다.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthPanel } from "@/components/layout/AuthPanel";
import { useAuth } from "@/components/providers/AuthProvider";
import { useReportNotifications } from "@/components/providers/ReportNotificationsProvider";
import { useSelectedSubject } from "@/components/providers/SelectedSubjectProvider";
import { getSubject } from "@/lib/subjects";
import type { SubjectSummary } from "@/lib/types";

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

// 경로 → 페이지 타이틀(메인 외 모든 페이지). 헤더의 '류보살 v2'를 대체 표시. 긴 접두사 우선.
const PAGE_TITLES: [string, string][] = [
  ["/manse", "만세력"],
  ["/calendar", "간지달력"],
  ["/themes", "테마사주"],
  ["/chat", "AI채팅상담"],
  ["/sajus", "사주목록"],
  ["/onboarding", "사주 등록"],
  ["/settings", "설정"],
  ["/reports", "내 풀이"],
  ["/reality-calibration", "용신 검증"],
  ["/admin", "관리자"],
];

export function Gnb() {
  const [open, setOpen] = useState(false);
  // 스크롤 방향에 따라 top bar 숨김/표시(아래로 스크롤=숨김, 위로 스크롤=표시).
  const [hidden, setHidden] = useState(false);
  const pathname = usePathname();
  // 현재 페이지 타이틀 — 메인('/') 외에는 '류보살 v2' 자리를 페이지 타이틀로 대체.
  const pageTitle =
    pathname === "/"
      ? undefined
      : PAGE_TITLES.find(([href]) => pathname === href || pathname.startsWith(`${href}/`))?.[1];
  const { isLoggedIn } = useAuth();
  const { selected } = useSelectedSubject();
  const { badgeCount } = useReportNotifications();
  // 선택 사주의 출생정보 — '데굴 기준' 칩 클릭 시 확인용 툴팁으로 표시.
  const [info, setInfo] = useState<SubjectSummary["birth"] | null>(null);
  const [showInfo, setShowInfo] = useState(false);

  // 라우트 이동 시 자동으로 닫고, 헤더를 다시 보이게 한다.
  useEffect(() => {
    setOpen(false);
    setHidden(false);
    setShowInfo(false);
  }, [pathname]);

  // 선택 사주의 출생정보 로드(로그인 + 선택 시). 실패는 조용히 무시(툴팁 미표시).
  useEffect(() => {
    if (!isLoggedIn || !selected) {
      setInfo(null);
      return;
    }
    getSubject(selected.subjectId)
      .then((s) => setInfo(s.birth))
      .catch(() => setInfo(null));
  }, [isLoggedIn, selected]);

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
            aria-label={badgeCount > 0 ? `메뉴 열기 (새 풀이 알림 ${badgeCount}건)` : "메뉴 열기"}
            onClick={() => setOpen(true)}
            className="relative rounded p-1 text-gray-700 hover:bg-gray-100"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeWidth="2" strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
            {badgeCount > 0 && (
              <span className="absolute right-0 top-0 h-2.5 w-2.5 rounded-full bg-rose-500 ring-2 ring-white" />
            )}
          </button>
          <Link href="/" className="text-lg font-bold" aria-label="홈">
            {pageTitle ?? (
              <>
                류보살 <span className="text-gray-400">v2</span>
              </>
            )}
          </Link>
          {selected && (
            <div className="relative ml-auto">
              <button
                type="button"
                onClick={() => setShowInfo((v) => !v)}
                className="flex items-center gap-1 truncate rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600 hover:bg-gray-200"
                aria-label="선택 사주 정보"
              >
                <span className="truncate">{selected.label} 기준</span>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  className="shrink-0 text-gray-400">
                  <circle cx="12" cy="12" r="9" strokeWidth="2" />
                  <path strokeWidth="2" strokeLinecap="round" d="M12 11v5M12 8h.01" />
                </svg>
              </button>
              {showInfo && (
                <>
                  <button
                    type="button"
                    aria-label="닫기"
                    className="fixed inset-0 z-30 cursor-default"
                    onClick={() => setShowInfo(false)}
                  />
                  <div className="absolute right-0 top-full z-40 mt-1 w-56 rounded-lg border bg-white p-3 text-xs text-gray-700 shadow-lg">
                    <p className="mb-1 font-semibold text-gray-800">{selected.label}</p>
                    {info ? (
                      <ul className="space-y-0.5 text-gray-600">
                        <li>
                          생년월일: {info.birth_date}
                          {info.calendar_type === "lunar" ? " (음력)" : ""}
                        </li>
                        <li>출생시각: {info.birth_time ?? "시간 모름"}</li>
                        {info.birth_place_name && <li>출생지: {info.birth_place_name}</li>}
                      </ul>
                    ) : (
                      <p className="text-gray-400">출생정보를 불러올 수 없어요.</p>
                    )}
                  </div>
                </>
              )}
            </div>
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
                  className="flex items-center justify-between rounded px-2 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <span>내 풀이 내역</span>
                  {badgeCount > 0 && (
                    <span className="rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] font-medium text-white">
                      {badgeCount}
                    </span>
                  )}
                </Link>
              )}
              <Link
                href="/settings"
                className="block rounded px-2 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                설정
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
