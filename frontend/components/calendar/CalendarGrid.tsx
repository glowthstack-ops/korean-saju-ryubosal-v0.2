"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CalendarDay, CalendarMonth } from "@/lib/types";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function localTodayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// backend weekday: Mon=0..Sun=6 → 일요일 시작 컬럼(Sun=0).
const sunFirstCol = (weekday: number) => (weekday + 1) % 7;

function lunarShort(iso: string | undefined, leap: boolean): string {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${leap ? "윤" : "음"}${Number(m)}.${Number(d)}`;
}

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
      <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))}
        className="w-20 rounded border px-2 py-1" aria-label="연도" />
      <span>년</span>
      <input type="number" min={1} max={12} value={month}
        onChange={(e) => setMonth(Number(e.target.value))}
        className="w-16 rounded border px-2 py-1" aria-label="월" />
      <span>월</span>
      <button type="submit" className="rounded bg-gray-800 px-3 py-1 text-white">이동</button>
    </form>
  );
}

function DayDetail({ d, onClose }: { d: CalendarDay; onClose: () => void }) {
  const row = (label: string, value: string) => (
    <div className="flex justify-between gap-4 py-0.5">
      <span className="text-gray-400">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
  return (
    <div className="mt-3 rounded-lg border-2 border-gray-300 bg-white p-4 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-bold">{d.date} ({WEEKDAYS[(d.weekday + 1) % 7]})</h3>
        <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-700">닫기 ✕</button>
      </div>
      {row("음력", `${d.lunar_date}${d.is_leap_month ? " (윤달)" : ""}`)}
      {row("년주", `${d.year_ganji} (${d.year_ganji_ko}) · ${d.year_zodiac}띠`)}
      {row("월주", `${d.month_ganji} (${d.month_ganji_ko})`)}
      {row("일주", `${d.day_ganji} (${d.day_ganji_ko})`)}
      {d.naeum && row("납음(일주)", d.naeum)}
      {d.solar_term && row("절기", d.solar_term)}
    </div>
  );
}

export function CalendarGrid({ data }: { data: CalendarMonth }) {
  const today = localTodayISO();
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  const lead = data.days.length ? sunFirstCol(data.days[0].weekday) : 0;
  // 월 헤더 요약(중순 기준 — 입춘 경계로 월초/월말 간지가 바뀔 수 있어 대표값).
  const mid = data.days[Math.min(14, data.days.length - 1)];

  return (
    <div>
      {mid && (
        <p className="mb-2 text-xs text-gray-500">
          {mid.year_ganji}({mid.year_ganji_ko})년 · {mid.year_zodiac}띠 · 월건 {mid.month_ganji}({mid.month_ganji_ko})
        </p>
      )}
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
            <button
              key={d.date}
              onClick={() => setSelected(d)}
              className={`min-h-[72px] rounded border p-1 text-center transition hover:bg-gray-50 ${
                isToday ? "border-gray-800 bg-yellow-50" : "border-gray-200 bg-white"
              } ${selected?.date === d.date ? "ring-2 ring-gray-400" : ""}`}
            >
              <div className="text-sm font-semibold">{Number(d.date.slice(8, 10))}</div>
              <div className="text-[11px] leading-tight">
                {d.day_ganji}
                <span className="block text-gray-500">{d.day_ganji_ko}</span>
              </div>
              <div className="text-[10px] text-gray-400">{lunarShort(d.lunar_date, d.is_leap_month)}</div>
              {d.solar_term && (
                <div className="mt-0.5 rounded bg-emerald-100 text-[10px] text-emerald-700">{d.solar_term}</div>
              )}
            </button>
          );
        })}
      </div>
      {selected && <DayDetail d={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
