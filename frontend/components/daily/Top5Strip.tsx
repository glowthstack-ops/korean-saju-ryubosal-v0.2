"use client";

// 금전·연애·좋은소식 3분야의 오늘 운 좋은 일주 Top5 — 칩 클릭 시 해당 카드로 스크롤.

import type { DailyFortuneBoard } from "@/lib/daily-fortune";

// 순위 표기 — 1~3위 메달, 4~5위 참가 메달
const RANK_MARKS = ["🥇", "🥈", "🥉", "🏅", "🏅"];

const GROUPS: { key: keyof DailyFortuneBoard["top5"]; title: string; icon: string }[] = [
  { key: "money", title: "오늘 금전 운 좋은 일주 TOP5", icon: "💰" },
  { key: "love", title: "오늘 연애 운 좋은 일주 TOP5", icon: "💗" },
  { key: "news", title: "오늘 좋은소식이 들려올 일주 TOP5", icon: "💌" },
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
            {g.icon} {g.title}
          </p>
          <ol className="mt-2 space-y-1">
            {board.top5[g.key].map((ilju, i) => (
              <li key={ilju}>
                <button
                  onClick={() => onSelect?.(ilju)}
                  className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-xs hover:bg-gray-100"
                >
                  <span className="w-5 shrink-0 text-center">{RANK_MARKS[i]}</span>
                  {koByIlju.get(ilju) ?? ilju}일주
                </button>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
