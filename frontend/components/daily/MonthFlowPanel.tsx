"use client";

// /daily 일간 탭과 일주 카드 사이 고정 패널 — 이번 달 흐름(천간 공통 + 일주별).
// 월운 간지가 바뀔 때까지 같은 내용이라 오늘 카드와 영역을 나눈다.
// 제목에 월 이름·기간을 붙이고(입절 전 주에 지난달 내용을 '이번 달'로 읽는 혼동 방지, docs/17 §25-3),
// 월운 전환 7일 전부터는 다음 달 미리보기를 한 줄 더 보여 준다.
// 일주별 흐름은 6일주 전부(관계 문장 또는 자리 문장, dict.v1.20 §27) — 내 일주만 펼치고 나머지는 접어 둔다.
// 과거 계약(v1.19 이전) 보드는 관계가 있는 일주만이라 빈 목록 안내가 남아 있다.

import type { DailyMonthStemFlow } from "@/lib/daily-fortune";

export function MonthFlowPanel({
  flow,
  myIlju,
  monthLabel,
  nextMonthLabel,
}: {
  flow: DailyMonthStemFlow;
  myIlju: string | null;
  monthLabel?: string | null;
  nextMonthLabel?: string | null;
}) {
  const myNote = myIlju ? flow.ilju_notes.find((n) => n.ilju === myIlju) : undefined;
  return (
    <section className="rounded-lg border bg-gray-50 p-5">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-bold text-gray-800">이번 달 흐름</h2>
        {monthLabel && <span className="text-xs text-gray-500">{monthLabel}</span>}
      </div>
      <div className="mt-3">
        <p className="text-xs font-semibold text-gray-500">천간 공통 흐름</p>
        <p className="mt-0.5 text-sm leading-relaxed text-gray-700">{flow.common}</p>
        {flow.same_group_note && (
          <p className="mt-1 text-sm leading-relaxed text-gray-700">{flow.same_group_note}</p>
        )}
      </div>
      <div className="mt-3">
        <p className="text-xs font-semibold text-gray-500">일주별 흐름</p>
        {flow.ilju_notes.length === 0 ? (
          <p className="mt-0.5 text-sm leading-relaxed text-gray-500">
            이번 달은 일주별로 갈리는 흐름이 없어요. 천간 공통 흐름 그대로예요.
          </p>
        ) : (
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
        )}
        {myIlju && flow.ilju_notes.length > 0 && !myNote && (
          <p className="mt-1 text-xs text-gray-500">
            내 일주는 이번 달 천간 공통 흐름 그대로예요.
          </p>
        )}
      </div>
      {flow.next_preview && (
        <div className="mt-3 border-t pt-3">
          <p className="text-xs font-semibold text-gray-500">
            다음 달 미리보기{nextMonthLabel ? ` · ${nextMonthLabel}` : ""}
          </p>
          <p className="mt-0.5 text-sm leading-relaxed text-gray-700">{flow.next_preview}</p>
        </div>
      )}
    </section>
  );
}
