"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchLuckDays } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";
import { loadEotPreference, loadProfile } from "@/lib/storage";
import { subjectEotPreference, summaryToProfile } from "@/lib/subject-mapping";
import { getSelectedSubjectId, getSubject } from "@/lib/subjects";
import type { CalendarDay, CalendarMonth, LuckPillar, LuckSinsal, Profile } from "@/lib/types";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

// 일운 오버레이(십성·신살·길흉) 기준 사주:
// - 로그인: 현재 "선택된 사주"만 사용(선택 안 했으면 오버레이 없음 — 데굴님 확정 2026-07-01).
//   균시차는 사주별 속성(birth.time_options)을 그대로 쓴다(데굴님 확정 2026-07-13).
// - 게스트: IndexedDB의 로컬 프로필 + 기기 로컬 균시차 토글.
async function resolveOverlayProfile(): Promise<
  { profile: Profile; eot: boolean } | null
> {
  if (isLoggedIn()) {
    const id = getSelectedSubjectId();
    if (!id) return null;
    try {
      const summary = await getSubject(id);
      return { profile: summaryToProfile(summary), eot: subjectEotPreference(summary) };
    } catch {
      return null;
    }
  }
  const profile = await loadProfile().catch(() => null);
  return profile ? { profile, eot: loadEotPreference() } : null;
}

// 손없는 날 — 음력 끝수가 9·0인 날(손[方位神]이 어느 방위에도 없어 이사·개업 등에 길). 로그인·사주와
// 무관한 상시 정보로, 음력일만으로 결정된다(음력 9·10·19·20·29·30일).
function isSonEomneunDay(lunarIso: string | undefined): boolean {
  if (!lunarIso) return false;
  const day = Number(lunarIso.split("-")[2]);
  return Number.isFinite(day) && (day % 10 === 9 || day % 10 === 0);
}

// 신살 polarity → 한글 분류(툴팁용).
const SINSAL_POLARITY_KO: Record<string, string> = {
  positive: "길신",
  caution: "흉성",
  neutral: "신살",
};

// 일주복음 전용 툴팁 — 일운 간지가 일주와 동일할 때만 등장.
const BOGEUM_DESC =
  "복음(伏吟) · 운의 간지가 일주와 동일 — 엎드려 신음하는 형국으로 정체·반복·내적 침체를 의미";

function sinsalTitle(s: LuckSinsal): string {
  if (s.name === "복음") return BOGEUM_DESC;
  return `${SINSAL_POLARITY_KO[s.polarity] ?? "신살"} · ${s.name}`;
}

function localTodayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// backend weekday: Mon=0..Sun=6 → 일요일 시작 컬럼(Sun=0).
const sunFirstCol = (weekday: number) => (weekday + 1) % 7;

function lunarShort(iso: string | undefined, leap: boolean): string {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${leap ? "윤" : "음"}${Number(m)}.${Number(d)}`;
}

export function MonthNav({ year, month }: { year: number; month: number }) {
  const prev = month === 1 ? { y: year - 1, m: 12 } : { y: year, m: month - 1 };
  const next = month === 12 ? { y: year + 1, m: 1 } : { y: year, m: month + 1 };
  return (
    <div className="flex items-center justify-between">
      <Link href={`/calendar/${prev.y}/${prev.m}`} className="rounded border px-3 py-1 text-sm hover:bg-gray-100">
        ← {prev.y}.{prev.m}
      </Link>
      <h2 className="text-lg font-bold">{year}년 {month}월</h2>
      <Link href={`/calendar/${next.y}/${next.m}`} className="rounded border px-3 py-1 text-sm hover:bg-gray-100">
        {next.y}.{next.m} →
      </Link>
    </div>
  );
}

export function DateJump() {
  const router = useRouter();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  return (
    <form
      className="flex items-center gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(`/calendar/${year}/${month}`);
      }}
    >
      <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))}
        className="w-20 rounded border px-2 py-1" aria-label="연도" />
      <span>년</span>
      <input type="number" min={1} max={12} value={month}
        onChange={(e) => setMonth(Number(e.target.value))}
        className="w-16 rounded border px-2 py-1" aria-label="월" />
      <span>월</span>
      <button type="submit" className="rounded bg-gray-800 px-3 py-1 text-white">이동</button>
    </form>
  );
}

// 신살/길신/흉성 칩(단색 회색, polarity는 툴팁).
function SinsalChips({ items }: { items: LuckSinsal[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-px flex flex-wrap justify-center gap-x-0.5 leading-tight">
      {items.map((s, i) => (
        <span key={i} title={sinsalTitle(s)}
          className={s.name === "복음"
            ? "text-[9px] font-medium text-amber-600"
            : "text-[9px] text-gray-500"}>
          {s.name}
        </span>
      ))}
    </div>
  );
}

function DayDetail({ d, luck, onClose }: { d: CalendarDay; luck?: LuckPillar; onClose: () => void }) {
  // 라벨/값을 grid 셀로 방출 — 부모 grid(max-content)가 라벨 열을 최장 항목명 기준으로 고정한다.
  const row = (label: string, value: string) => (
    <>
      <span className="text-gray-400">{label}</span>
      <span className="min-w-0 font-medium">{value}</span>
    </>
  );
  return (
    <div className="mt-3 rounded-lg border-2 border-gray-300 bg-white p-4 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-bold">
          <span>{d.date} ({WEEKDAYS[(d.weekday + 1) % 7]})</span>
          {isSonEomneunDay(d.lunar_date) && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-700">손없는 날</span>
          )}
        </h3>
        <button onClick={onClose} className="shrink-0 text-xs text-gray-400 hover:text-gray-700">닫기 ✕</button>
      </div>
      {/* 단일 grid: 라벨 열 = 최장 항목명(max-content) 기준 고정, 값 열 = 나머지(1fr). */}
      <div className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5">
        {row("음력", `${d.lunar_date}${d.is_leap_month ? " (윤달)" : ""}`)}
        {row("년주", `${d.year_ganji} (${d.year_ganji_ko}) · ${d.year_zodiac}띠`)}
        {row("월주", `${d.month_ganji} (${d.month_ganji_ko})`)}
        {row("일주", `${d.day_ganji} (${d.day_ganji_ko})`)}
        {d.naeum && row("납음(일주)", d.naeum)}
        {d.solar_term && row("절기", d.solar_term)}
        {luck && (
          <>
            <div className="col-span-2 mt-1 border-t border-dashed border-gray-300 pt-1" />
            {row("십성(천간/지지)", `${luck.stem_ten_god} / ${luck.branch_ten_god}`)}
            {luck.twelve_unseong && row("십이운성", luck.twelve_unseong)}
            {luck.luck_sinsal && luck.luck_sinsal.length > 0 && (
              <>
                <span className="text-gray-400">신살/길흉</span>
                <span className="flex min-w-0 flex-wrap gap-1">
                  {luck.luck_sinsal.map((s, i) => (
                    <span key={i} title={sinsalTitle(s)}
                      className={s.name === "복음"
                        ? "rounded border border-amber-300 px-1 text-xs font-medium text-amber-600"
                        : "rounded border px-1 text-xs text-gray-600"}>
                      {s.name}
                    </span>
                  ))}
                </span>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function CalendarGrid({ data }: { data: CalendarMonth }) {
  const today = localTodayISO();
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  // 사용자 원국 기준 일운(십성·십이운성·신살) 오버레이 — 선택된 사주(로그인)/로컬 프로필(게스트)만 로드.
  const [luckByDate, setLuckByDate] = useState<Record<string, LuckPillar>>({});

  useEffect(() => {
    let alive = true;
    setLuckByDate({});
    resolveOverlayProfile()
      .then((resolved) => {
        if (!resolved) return;
        // 로그인 사주 = 사주별 저장값, 게스트 = 기기 토글 — 만세력·챗·리포트와 동일 기준.
        const { profile: p, eot } = resolved;
        const timeOptions = { apply_equation_of_time: eot };
        return fetchLuckDays(p, data.year, data.month, undefined, timeOptions).then((days) => {
          if (!alive) return;
          const map: Record<string, LuckPillar> = {};
          for (const lp of days) map[lp.label] = lp;
          setLuckByDate(map);
        });
      })
      .catch(() => {
        /* 프로필 없음/조회 실패 시 기본 달력만 표시 */
      });
    return () => {
      alive = false;
    };
  }, [data.year, data.month]);

  const lead = data.days.length ? sunFirstCol(data.days[0].weekday) : 0;
  // 월 헤더 요약(중순 기준 — 입춘 경계로 월초/월말 간지가 바뀔 수 있어 대표값).
  const mid = data.days[Math.min(14, data.days.length - 1)];

  return (
    <div>
      {mid && (
        <p className="mb-2 text-xs text-gray-500">
          {mid.year_ganji}({mid.year_ganji_ko})년 · {mid.year_zodiac}띠 · 월건 {mid.month_ganji}({mid.month_ganji_ko})
        </p>
      )}
      {/* 요일 헤더: 스크롤 시에도 요일이 보이도록 상단 고정(여백 포함). */}
      <div className="sticky top-0 z-10 -mx-1 grid grid-cols-7 bg-white px-1 pb-1 pt-2 text-center text-xs font-semibold text-gray-500">
        {WEEKDAYS.map((w, i) => (
          <div key={w} className={i === 0 ? "text-red-500" : i === 6 ? "text-blue-500" : ""}>{w}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {Array.from({ length: lead }).map((_, i) => <div key={`b${i}`} />)}
        {data.days.map((d) => {
          const isToday = d.date === today;
          const luck = luckByDate[d.date];
          return (
            <button
              key={d.date}
              onClick={() => setSelected(d)}
              className={`flex min-h-[72px] flex-col items-center rounded border p-1 text-center transition hover:bg-gray-50 ${
                isToday ? "border-gray-800 bg-yellow-50" : "border-gray-200 bg-white"
              } ${selected?.date === d.date ? "ring-2 ring-gray-400" : ""}`}
            >
              {/* 상단 고정 영역: 날짜/간지(한자)/간지(한글)/음력/손없는날/절기 —
                  손없는날·절기를 고정 높이 슬롯으로 두어 모든 셀의 상단 영역 크기를 최대치로 고정
                  (셀마다 구분선·오버레이가 같은 줄에 정렬). */}
              <div className="flex w-full flex-col items-center">
                <div className="text-sm font-semibold">{Number(d.date.slice(8, 10))}</div>
                <div className="text-[11px] leading-tight">
                  {d.day_ganji}
                  <span className="block text-gray-500">{d.day_ganji_ko}</span>
                </div>
                <div className="text-[10px] text-gray-400">{lunarShort(d.lunar_date, d.is_leap_month)}</div>
                {/* 손없는 날 슬롯(절기와 동일 크기 박스·상시정보·로그인 무관): 음력 끝수 9·0. */}
                <div className="h-[15px] w-full">
                  {isSonEomneunDay(d.lunar_date) && (
                    <div className="rounded bg-amber-100 text-[10px] leading-[15px] text-amber-700">손없는날</div>
                  )}
                </div>
                {/* 절기 슬롯(손없는날과 동일 크기·사이 여백). */}
                <div className="mt-0.5 h-[15px] w-full">
                  {d.solar_term && (
                    <div className="rounded bg-emerald-100 text-[10px] leading-[15px] text-emerald-700">{d.solar_term}</div>
                  )}
                </div>
              </div>
              {/* 절기 아래 구분선: 천간/지지 십성 · 십이운성. */}
              {luck && (
                <div className="w-full border-t border-dashed border-gray-300 mt-1 pt-1">
                  <div className="whitespace-nowrap text-[9px] leading-tight tracking-tighter text-gray-500">
                    {luck.stem_ten_god}·{luck.branch_ten_god}
                  </div>
                  {luck.twelve_unseong && (
                    <div className="text-[9px] leading-tight text-gray-400">{luck.twelve_unseong}</div>
                  )}
                </div>
              )}
              {/* 십이운성 아래 구분선: 길신 · 신살. */}
              {luck?.luck_sinsal && luck.luck_sinsal.length > 0 && (
                <div className="w-full border-t border-dashed border-gray-300 mt-1 pt-1">
                  <SinsalChips items={luck.luck_sinsal} />
                </div>
              )}
            </button>
          );
        })}
      </div>
      {selected && (
        <DayDetail d={selected} luck={luckByDate[selected.date]} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
