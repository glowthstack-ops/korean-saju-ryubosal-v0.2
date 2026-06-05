"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// 오늘(클라이언트 로컬) 기준 달로 이동.
export default function CalendarTodayPage() {
  const router = useRouter();
  useEffect(() => {
    const d = new Date();
    router.replace(`/calendar/${d.getFullYear()}/${d.getMonth() + 1}`);
  }, [router]);
  return <p className="text-sm text-gray-500">오늘 날짜 달력으로 이동 중…</p>;
}
