"use client";

// /daily 일간 탭과 일주 카드 사이 고정 패널 — 이번 달 흐름(천간 공통 + 일주별).
// 월운 간지가 바뀔 때까지 같은 내용이라 오늘 카드와 영역을 나눈다.
// 일주별 흐름은 6줄이라 카드를 밀어내므로 내 일주만 펼치고 나머지는 접어 둔다.

import type { DailyMonthStemFlow } from "@/lib/daily-fortune";

export function MonthFlowPanel({
  flow,
  myIlju,
}: {
  flow: DailyMonthStemFlow;
  myIlju: string | null;
}) {
  return (
    <section className="rounded-lg border bg-gray-50 p-5">
      <h2 className="text-sm font-bold text-gray-800">이번 달 흐름</h2>
      <div className="mt-3">
        <p className="text-xs font-semibold text-gray-500">천간 공통 흐름</p>
        <p className="mt-0.5 text-sm leading-relaxed text-gray-700">{flow.common}</p>
      </div>
      <div className="mt-3">
        <p className="text-xs font-semibold text-gray-500">일주별 흐름</p>
        <ul className="mt-1 space-y-1">
          {flow.ilju_notes.map((n) => (
            <li key={n.ilju}>
              <details open={n.ilju === myIlju}>
                <summary className="cursor-pointer text-sm font-semibold text-gray-700">
                  {n.ilju_ko}일주
                </summary>
                <p className="mt-0.5 text-sm leading-relaxed text-gray-700">{n.note}</p>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
