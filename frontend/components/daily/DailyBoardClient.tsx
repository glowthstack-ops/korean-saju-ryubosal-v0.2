"use client";

// /daily 본문 — 상단(날짜·Top5) + 일간 탭 + 일주 카드 6개. 서버 프리페치 실패 시
// 클라이언트에서 재요청한다. 표시 날짜는 API 값만 사용(클라이언트 재계산 금지).

import { useEffect, useState } from "react";
import { DailyFortuneCard } from "@/components/daily/DailyFortuneCard";
import { StemTabs } from "@/components/daily/StemTabs";
import { Top5Strip } from "@/components/daily/Top5Strip";
import {
  type DailyFortuneBoard,
  formatFortuneDate,
  getDailyBoard,
} from "@/lib/daily-fortune";
import { useCurrentIlju } from "@/lib/use-current-ilju";

export function DailyBoardClient({ initial }: { initial: DailyFortuneBoard | null }) {
  const [board, setBoard] = useState<DailyFortuneBoard | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [stem, setStem] = useState("갑");
  const [highlight, setHighlight] = useState<string | null>(null);
  const { ilju: myIlju } = useCurrentIlju();

  useEffect(() => {
    if (board) return;
    getDailyBoard()
      .then(setBoard)
      .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"));
  }, [board]);

  // 내 일주가 확인되면 해당 일간 탭을 기본 선택
  useEffect(() => {
    if (!myIlju || !board) return;
    const mine = board.fortunes.find((f) => f.ilju === myIlju);
    if (mine) setStem(mine.day_stem_ko);
  }, [myIlju, board]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!board) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  const scrollTo = (ilju: string) => {
    const target = board.fortunes.find((f) => f.ilju === ilju);
    if (!target) return;
    setStem(target.day_stem_ko);
    setHighlight(ilju);
    // 탭 전환 렌더 후 스크롤
    setTimeout(() => {
      document.getElementById(`ilju-${ilju}`)?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 50);
  };

  const visible = board.fortunes.filter((f) => f.day_stem_ko === stem);

  return (
    <div className="space-y-4">
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-xl font-bold">일주별 오늘의 운세</h1>
        <p className="mt-1 text-sm text-gray-500">
          {formatFortuneDate(board.fortune_date, board.weekday_ko)} · 60일주 전체
        </p>
      </section>

      <Top5Strip board={board} onSelect={scrollTo} />

      <section className="space-y-3">
        <StemTabs active={stem} onChange={(s) => { setStem(s); setHighlight(null); }} />
        <div className="grid gap-4 sm:grid-cols-2">
          {visible.map((f) => (
            <DailyFortuneCard
              key={f.ilju}
              fortune={f}
              highlight={f.ilju === highlight || f.ilju === myIlju}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
