"use client";

// 메인 무료 영역 최상단 가로 전체 카드 — 일주별 오늘의 운세 (PRD UI/UX 2·3항).
// - 기준 사주 확인 중: 스켈레톤(로그인 CTA 깜빡임 방지)
// - 일주 확보(로그인 선택 사주 또는 게스트 프로필): 해당 일주 운세 + [일주 전체보기]
// - 미확보: 타이틀 + 오늘 날짜(요일) + [로그인]·[만세력에서 사주등록] + [일주 전체보기]

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  type DailyFortuneSingle,
  formatFortuneDate,
  getDailyBoard,
  getDailyFortune,
} from "@/lib/daily-fortune";
import { useCurrentIlju } from "@/lib/use-current-ilju";

const SLOT_ICON: Record<string, string> = { good: "🌟", caution: "⚠️", support: "🍀" };

export function DailyHomeCard() {
  const { status, ilju } = useCurrentIlju();
  const [single, setSingle] = useState<DailyFortuneSingle | null>(null);
  const [failed, setFailed] = useState(false);
  // CTA 카드용 오늘 날짜(요일) — 클라이언트 재계산 금지, API 값만 사용
  const [ctaDate, setCtaDate] = useState<{ iso: string; weekdayKo: string } | null>(null);

  useEffect(() => {
    if (status !== "ready" || !ilju) return;
    getDailyFortune(ilju)
      .then(setSingle)
      .catch(() => setFailed(true));
  }, [status, ilju]);

  useEffect(() => {
    if (status !== "none" && !failed) return;
    getDailyBoard()
      .then((b) => setCtaDate({ iso: b.fortune_date, weekdayKo: b.weekday_ko }))
      .catch(() => {});
  }, [status, failed]);

  if (status === "loading" || (status === "ready" && !single && !failed)) {
    return (
      <section className="animate-pulse rounded-lg bg-white p-6 shadow-sm">
        <div className="h-5 w-40 rounded bg-gray-200" />
        <div className="mt-3 h-4 w-64 rounded bg-gray-100" />
        <div className="mt-2 h-4 w-52 rounded bg-gray-100" />
      </section>
    );
  }

  if (status === "ready" && single) {
    const f = single.fortune;
    return (
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-bold">일주별 오늘의 운세</h2>
          <span className="text-xs text-gray-400">
            {formatFortuneDate(single.fortune_date, single.weekday_ko)}
          </span>
        </div>
        <p className="mt-1 text-sm font-semibold text-gray-700">
          오늘의 {f.ilju_ko}일주 운세
        </p>
        <p className="mt-2 text-sm leading-relaxed">{f.headline}</p>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
          {f.events.map((e) => (
            <li key={e.event_key}>
              {SLOT_ICON[e.slot] ?? ""} {e.phrase}{" "}
              <b className="text-gray-800">{e.probability}%</b>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="text-xs text-gray-500">📍 행운의 장소: {f.lucky_place.name}</span>
          <Link href="/daily" className="text-sm text-gray-700 underline">
            일주 전체보기 →
          </Link>
        </div>
        {f.lotto_phrase && (
          <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
            {f.lotto_phrase}
          </p>
        )}
      </section>
    );
  }

  // 미확보(비로그인·사주 미등록) 또는 단건 조회 실패 — CTA 카드
  return (
    <section className="rounded-lg bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold">일주별 오늘의 운세</h2>
        {ctaDate && (
          <span className="text-xs text-gray-400">
            {formatFortuneDate(ctaDate.iso, ctaDate.weekdayKo)}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-gray-600">
        내 일주(태어난 날의 기운)를 알면 매일 아침 5초 만에 오늘의 흐름을 확인할 수 있어요.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link href="/sajus" className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white">
          로그인
        </Link>
        <Link href="/manse" className="rounded border px-3 py-1.5 text-sm">
          만세력에서 사주등록
        </Link>
        <Link href="/daily" className="rounded border px-3 py-1.5 text-sm">
          일주 전체보기
        </Link>
      </div>
    </section>
  );
}
