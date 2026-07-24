"use client";

// 일주 1개의 오늘 운세 카드 — 헤드라인·사건 3개(%게이지)·오늘의 연애(강한 신호 시)·행운 장소·로또 문구.

import type { DailyIljuFortune } from "@/lib/daily-fortune";

const SLOT_ICON: Record<string, string> = { good: "🌟", caution: "⚠️", support: "🍀" };

export function DailyFortuneCard({
  fortune,
  highlight = false,
}: {
  fortune: DailyIljuFortune;
  highlight?: boolean;
}) {
  return (
    <article
      id={`ilju-${fortune.ilju}`}
      className={`rounded-lg border bg-white p-5 shadow-sm ${
        highlight ? "border-gray-800" : ""
      }`}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-semibold">
          {fortune.ilju_ko}일주 <span className="text-xs text-gray-400">{fortune.ilju}</span>
        </h3>
      </div>
      <p className="mt-2 whitespace-pre-line text-sm font-medium leading-relaxed">
        {fortune.headline}
      </p>

      <ul className="mt-3 space-y-2">
        {fortune.events.map((e) => (
          <li key={e.event_key} className="text-xs text-gray-600">
            <div className="flex items-center justify-between gap-2">
              <span>
                {SLOT_ICON[e.slot] ?? ""} {e.phrase}
              </span>
              <span className="shrink-0 font-semibold text-gray-800">{e.probability}%</span>
            </div>
            <div className="mt-1 h-1 rounded bg-gray-100">
              <div
                className={`h-1 rounded ${e.slot === "caution" ? "bg-amber-400" : "bg-gray-700"}`}
                style={{ width: `${e.probability}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      {fortune.love_line && (
        <p className="mt-3 whitespace-pre-line text-xs leading-relaxed text-gray-500">
          💕 오늘의 연애: {fortune.love_line}
        </p>
      )}
      <p className="mt-3 text-xs text-gray-500">📍 행운의 장소: {fortune.lucky_place.name}</p>
      {fortune.lotto_phrase && (
        <p className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
          {fortune.lotto_phrase}
        </p>
      )}
    </article>
  );
}
