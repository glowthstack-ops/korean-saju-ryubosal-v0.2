// 일주별 오늘의 운세 — 공개 데이터 서버 프리페치 + 클라이언트 상호작용(탭·스크롤).
// 날짜가 바뀌면 이전 보드가 남지 않도록 프레임워크 캐시를 쓰지 않는다(force-dynamic).

import { DailyBoardClient } from "@/components/daily/DailyBoardClient";
import { getDailyBoardServer } from "@/lib/daily-fortune";

export const dynamic = "force-dynamic";

export default async function DailyPage() {
  const board = await getDailyBoardServer();
  return <DailyBoardClient initial={board} />;
}
