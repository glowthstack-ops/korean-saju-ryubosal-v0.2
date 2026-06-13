"use client";

// 리포트 완료 알림 — 로그인 시 백그라운드로 풀이 잡 목록을 폴링해, 새로 완료(또는 보완/실패)된
// 풀이를 토스트로 알리고 GNB 뱃지 카운트를 노출한다. 페이지를 이탈해도(다른 화면에 있어도)
// 완료를 놓치지 않게 하는 것이 목적. '본 상태'는 브라우저(localStorage)별로 추적한다.

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { listReportJobs } from "@/lib/subjects";
import { themeLabel } from "@/lib/themes";
import type { ReportJobSummary } from "@/lib/types";

const POLL_MS = 20_000;
const TERMINAL = new Set(["completed", "on_hold", "failed"]);
const NOTIFIED_KEY = "ryubosal:reportNotified"; // 이미 토스트한 잡(재토스트 방지)
const SEEN_KEY = "ryubosal:reportSeen"; // 사용자가 '내 풀이 내역'에서 확인한 잡(뱃지 해제)

interface Toast {
  id: string;
  text: string;
  href: string;
  tone: "ok" | "warn" | "err";
}

interface NotifState {
  badgeCount: number;
  markReportsSeen: () => void;
}

const Ctx = createContext<NotifState>({ badgeCount: 0, markReportsSeen: () => {} });
export const useReportNotifications = () => useContext(Ctx);

function loadSet(key: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) || "[]") as string[]);
  } catch {
    return new Set();
  }
}
function saveSet(key: string, s: Set<string>): void {
  try {
    localStorage.setItem(key, JSON.stringify([...s]));
  } catch {
    /* 저장 실패는 무시(알림은 best-effort) */
  }
}

function toastFor(j: ReportJobSummary): Toast {
  const name = themeLabel(j.product_code, j.topic);
  const href = `/reports/${j.job_id}`;
  if (j.status === "completed") {
    return { id: j.job_id, text: `${name} 풀이가 완성됐어요`, href, tone: "ok" };
  }
  if (j.status === "on_hold") {
    return { id: j.job_id, text: `${name} 풀이가 일부 보완 중이에요`, href, tone: "warn" };
  }
  return { id: j.job_id, text: `${name} 풀이 생성에 실패했어요`, href, tone: "err" };
}

export function ReportNotificationsProvider({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useAuth();
  const [badgeCount, setBadgeCount] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const terminalIds = useRef<string[]>([]); // 최근 폴링 기준 종료 잡 id(markSeen용)

  const pushToast = useCallback((t: Toast) => {
    setToasts((prev) => (prev.some((x) => x.id === t.id) ? prev : [...prev, t]));
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== t.id)), 8_000);
  }, []);

  useEffect(() => {
    if (!isLoggedIn) {
      setBadgeCount(0);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const jobs = await listReportJobs();
        if (!alive) return;
        const terminal = jobs.filter((j) => TERMINAL.has(j.status));
        terminalIds.current = terminal.map((j) => j.job_id);

        if (localStorage.getItem(NOTIFIED_KEY) === null) {
          // 최초 실행 — 기존 완료분은 과거 것으로 보고 토스트·뱃지에서 제외.
          saveSet(NOTIFIED_KEY, new Set(terminalIds.current));
          saveSet(SEEN_KEY, new Set(terminalIds.current));
          setBadgeCount(0);
        } else {
          const notified = loadSet(NOTIFIED_KEY);
          const fresh = terminal.filter((j) => !notified.has(j.job_id));
          for (const j of fresh) {
            pushToast(toastFor(j));
            notified.add(j.job_id);
          }
          if (fresh.length) saveSet(NOTIFIED_KEY, notified);
          const seen = loadSet(SEEN_KEY);
          setBadgeCount(terminal.filter((j) => !seen.has(j.job_id)).length);
        }
      } catch {
        /* 폴링 실패는 다음 주기에 재시도 */
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [isLoggedIn, pushToast]);

  const markReportsSeen = useCallback(() => {
    saveSet(SEEN_KEY, new Set(terminalIds.current));
    setBadgeCount(0);
  }, []);

  return (
    <Ctx.Provider value={{ badgeCount, markReportsSeen }}>
      {children}
      <Toaster toasts={toasts} onClose={(id) => setToasts((p) => p.filter((x) => x.id !== id))} />
    </Ctx.Provider>
  );
}

const TONE_CLS: Record<Toast["tone"], string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  err: "border-red-200 bg-red-50 text-red-700",
};

function Toaster({ toasts, onClose }: { toasts: Toast[]; onClose: (id: string) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-[min(20rem,90vw)] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-2 rounded-lg border p-3 shadow-lg ${TONE_CLS[t.tone]}`}
        >
          <Link href={t.href} onClick={() => onClose(t.id)} className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{t.text}</span>
            <span className="block text-xs opacity-70">눌러서 확인하기 →</span>
          </Link>
          <button
            aria-label="알림 닫기"
            onClick={() => onClose(t.id)}
            className="shrink-0 rounded px-1 text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
