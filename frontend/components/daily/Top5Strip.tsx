"use client";

// 금전·연애·좋은소식 3분야의 오늘 운 좋은 일주 Top5 — 칩 클릭 시 해당 카드로 스크롤.

import type { DailyFortuneBoard } from "@/lib/daily-fortune";

const GROUPS: { key: keyof DailyFortuneBoard["top5"]; label: string; icon: string }[] = [
  { key: "money", label: "금전", icon: "💰" },
  { key: "love", label: "연애", icon: "💗" },
  { key: "news", label: "좋은소식", icon: "💌" },
];

export function Top5Strip({
  board,
  onSelect,
}: {
  board: DailyFortuneBoard;
  onSelect?: (ilju: string) => void;
}) {
  const koByIlju = new Map(board.fortunes.map((f) => [f.ilju, f.ilju_ko]));
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {GROUPS.map((g) => (
        <div key={g.key} className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold text-gray-700">
            {g.icon} 오늘 {g.label} 운 좋은 일주 TOP5
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {board.top5[g.key].map((ilju, i) => (
              <button
                key={ilju}
                onClick={() => onSelect?.(ilju)}
                className="rounded-full bg-gray-100 px-2.5 py-1 text-xs hover:bg-gray-200"
              >
                <span className="mr-1 text-[10px] text-gray-400">{i + 1}</span>
                {koByIlju.get(ilju) ?? ilju}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
