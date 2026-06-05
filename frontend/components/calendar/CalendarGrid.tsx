"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CalendarMonth } from "@/lib/types";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function localTodayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// backend weekday: Mon=0..Sun=6 → 일요일 시작 컬럼(Sun=0).
const sunFirstCol = (weekday: number) => (weekday + 1) % 7;

export function MonthNav({ year, month }: { year: number; month: number }) {
  const prev = month === 1 ? { y: year - 1, m: 12 } : { y: year, m: month - 1 };
  const next = month === 12 ? { y: year + 1, m: 1 } : { y: year, m: month + 1 };
  return (
    <div className="flex items-center justify-between">
      <Link href={`/calendar/${prev.y}/${prev.m}`} className="rounded border px-3 py-1 text-sm hover:bg-gray-100">
        ← {prev.y}.{prev.m}
      </Link>
      <h2 className="text-lg font-bold">{year}년 {month}월</h2>
      <Link href={`/calendar/${next.y}/${next.m}`} className="rounded border px-3 py-1 text-sm hover:bg-gray-100">
        {next.y}.{next.m} →
      </Link>
    </div>
  );
}

export function DateJump() {
  const router = useRouter();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  return (
    <form
      className="flex items-center gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(`/calendar/${year}/${month}`);
      }}
    >
      <input
        type="number" value={year} onChange={(e) => setYear(Number(e.target.value))}
        className="w-20 rounded border px-2 py-1" aria-label="연도"
      />
      <span>년</span>
      <input
        type="number" min={1} max={12} value={month}
        onChange={(e) => setMonth(Number(e.target.value))}
        className="w-16 rounded border px-2 py-1" aria-label="월"
      />
      <span>월</span>
      <button type="submit" className="rounded bg-gray-800 px-3 py-1 text-white">이동</button>
    </form>
  );
}

export function CalendarGrid({ data }: { data: CalendarMonth }) {
  const today = localTodayISO();
  const lead = data.days.length ? sunFirstCol(data.days[0].weekday) : 0;
  return (
    <div>
      <div className="grid grid-cols-7 text-center text-xs font-semibold text-gray-500">
        {WEEKDAYS.map((w, i) => (
          <div key={w} className={i === 0 ? "text-red-500" : i === 6 ? "text-blue-500" : ""}>{w}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {Array.from({ length: lead }).map((_, i) => <div key={`b${i}`} />)}
        {data.days.map((d) => {
          const isToday = d.date === today;
          return (
            <div
              key={d.date}
              className={`min-h-[64px] rounded border p-1 text-center ${
                isToday ? "border-gray-800 bg-yellow-50" : "border-gray-200 bg-white"
              }`}
            >
              <div className="text-sm font-semibold">{Number(d.date.slice(8, 10))}</div>
              <div className="text-[11px] leading-tight">
                {d.day_ganji}
                <span className="block text-gray-500">{d.day_ganji_ko}</span>
              </div>
              {d.solar_term && (
                <div className="mt-0.5 rounded bg-emerald-100 text-[10px] text-emerald-700">
                  {d.solar_term}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
