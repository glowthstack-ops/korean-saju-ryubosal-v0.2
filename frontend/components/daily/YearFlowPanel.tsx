"use client";

// /daily 일간 탭 아래, 이번 달 패널 위 고정 패널 — 올해의 흐름(단식, docs/17 §26).
// 제목은 2026-11-09 데굴님 "결이라는 어려운 단어는 지양" 으로 '올해의 결' → '올해의 흐름'.
// 일간 기준 올해 기운의 결만 말하고 길흉은 가르지 않는다(양면 어휘). 세운이 바뀔 때까지 같다.
// 과거 계약 보드(dict.v1.18 이하)는 year_flow 가 null 이라 패널이 없다.
// dict.v1.21(docs/17 §31)부터 네 칸이 늘었다 — 올해 안의 변화(가장 강한 때·전환) / 여러 해 흐름(3년 묶음) /
// 일주별 흐름(6일주 전부, 내 일주만 펼침) / 이런 명식이라면(조건 줄 — 조건 보유는 사용자가 자기 명식으로
// 판단하고, 확인은 하단 안내대로 AI 채팅상담·테마사주). 과거 계약 보드는 필드가 없어 칸이 그려지지 않는다.

import type { DailyYearStemFlow } from "@/lib/daily-fortune";

export function YearFlowPanel({
  flow,
  myIlju,
  yearLabel,
  directionNote,
}: {
  flow: DailyYearStemFlow;
  myIlju?: string | null;
  yearLabel?: string | null;
  directionNote?: string | null;
}) {
  const phase = flow.phase ?? [];
  const iljuNotes = flow.ilju_notes ?? [];
  const conditions = flow.conditions ?? [];
  return (
    <section className="rounded-lg border bg-amber-50/60 p-5">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-bold text-gray-800">올해의 흐름</h2>
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
      {/* 간여지동 달 문단("10월에는 천간과 지지가 모두 같은 성격의 글자로 …")은 2026-11-10 제거
          (데굴님 "불필요해보여", docs/17 §30). 과거 보드의 peak_months 값도 표시하지 않는다. */}
      {phase.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-500">올해 안의 변화</p>
          {phase.map((line) => (
            <p key={line} className="mt-0.5 text-sm leading-relaxed text-gray-700">
              {line}
            </p>
          ))}
        </div>
      )}
      {flow.span && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-500">여러 해 흐름</p>
          <p className="mt-0.5 text-sm leading-relaxed text-gray-700">{flow.span}</p>
        </div>
      )}
      {iljuNotes.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-500">일주별 흐름</p>
          <ul className="mt-1 space-y-1">
            {iljuNotes.map((n) => (
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
      )}
      {conditions.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-500">이런 명식이라면</p>
          <ul className="mt-1 space-y-1">
            {conditions.map((line) => (
              <li key={line} className="text-sm leading-relaxed text-gray-700">
                · {line}
              </li>
            ))}
          </ul>
        </div>
      )}
      {directionNote && (
        <p className="mt-3 border-t pt-3 text-xs leading-relaxed text-gray-500">{directionNote}</p>
      )}
    </section>
  );
}
