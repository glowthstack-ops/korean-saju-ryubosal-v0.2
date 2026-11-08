"use client";

// /daily 일간 탭 아래, 이번 달 패널 위 고정 패널 — 올해의 결(단식, docs/17 §26).
// 일간 기준 올해 기운의 결만 말하고 길흉은 가르지 않는다(양면 어휘). 세운이 바뀔 때까지 같다.
// 과거 계약 보드(dict.v1.18 이하)는 year_flow 가 null 이라 패널이 없다.

import type { DailyYearStemFlow } from "@/lib/daily-fortune";

export function YearFlowPanel({
  flow,
  yearLabel,
}: {
  flow: DailyYearStemFlow;
  yearLabel?: string | null;
}) {
  return (
    <section className="rounded-lg border bg-amber-50/60 p-5">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-bold text-gray-800">올해의 결</h2>
        {yearLabel && <span className="text-xs text-gray-500">{yearLabel}</span>}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-gray-700">{flow.tone}</p>
      {flow.emphasis && (
        <p className="mt-1 text-sm leading-relaxed text-gray-700">{flow.emphasis}</p>
      )}
      {flow.points.length > 0 && (
        <ul className="mt-3 space-y-1">
          {flow.points.map((p) => (
            <li key={p} className="text-sm leading-relaxed text-gray-700">
              · {p}
            </li>
          ))}
        </ul>
      )}
      {flow.peak_months && (
        <p className="mt-3 border-t pt-3 text-sm leading-relaxed text-gray-700">
          {flow.peak_months}
        </p>
      )}
    </section>
  );
}
