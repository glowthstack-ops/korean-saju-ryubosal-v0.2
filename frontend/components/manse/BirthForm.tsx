"use client";

import { useMemo, useState } from "react";
import { searchLocations } from "@/lib/locations";
import type { Profile, SajuLocation } from "@/lib/types";

export function BirthForm({
  onSubmit,
  initial,
  heading = "사용자 정보 등록",
  submitLabel = "만세력 보기",
  children,
}: {
  onSubmit: (p: Profile) => void;
  // 수정(edit) 모드 프리필. 미지정 시 기본값.
  initial?: Profile;
  // 헤더 문구(null이면 숨김 — 온보딩처럼 외부에서 제목을 제공할 때).
  heading?: string | null;
  submitLabel?: string;
  // 폼 상단에 주입할 추가 입력(예: 온보딩 별명) — 같은 submit으로 함께 처리된다.
  children?: React.ReactNode;
}) {
  const [gender, setGender] = useState<"male" | "female">(initial?.gender ?? "male");
  const [calendarType, setCalendarType] = useState<"solar" | "lunar">(
    initial?.calendarType ?? "solar",
  );
  const [isLeapMonth, setIsLeapMonth] = useState(initial?.isLeapMonth ?? false);
  const [birthDate, setBirthDate] = useState(initial?.birthDate ?? "1990-01-01");
  const [birthTime, setBirthTime] = useState(initial?.birthTime ?? "12:00");
  const [timeUnknown, setTimeUnknown] = useState(initial?.timeUnknown ?? false);
  const [query, setQuery] = useState(initial?.place.name ?? "서울");
  const [place, setPlace] = useState<SajuLocation | null>(initial?.place ?? null);

  const results = useMemo(() => searchLocations(query).slice(0, 8), [query]);
  const chosen = place ?? results[0] ?? null;

  return (
    <form
      className="space-y-5 rounded-lg bg-white p-6 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (!chosen) return;
        onSubmit({
          gender, calendarType, isLeapMonth, birthDate,
          birthTime: timeUnknown ? null : birthTime,
          timeUnknown, place: chosen,
        });
      }}
    >
      {heading && <h1 className="text-xl font-bold">{heading}</h1>}
      {children}

      <div>
        <span className="mb-1 block text-sm font-medium">성별</span>
        <div className="flex gap-3 text-sm">
          {(["male", "female"] as const).map((g) => (
            <label key={g} className="flex items-center gap-1">
              <input type="radio" checked={gender === g} onChange={() => setGender(g)} />
              {g === "male" ? "남성" : "여성"}
            </label>
          ))}
        </div>
      </div>

      <div>
        <span className="mb-1 block text-sm font-medium">달력</span>
        <div className="flex items-center gap-3 text-sm">
          {(["solar", "lunar"] as const).map((c) => (
            <label key={c} className="flex items-center gap-1">
              <input type="radio" checked={calendarType === c} onChange={() => setCalendarType(c)} />
              {c === "solar" ? "양력" : "음력"}
            </label>
          ))}
          {calendarType === "lunar" && (
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={isLeapMonth} onChange={(e) => setIsLeapMonth(e.target.checked)} />
              윤달
            </label>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">생년월일</span>
          {/* min/max로 연도 입력을 4자리로 제한(브라우저 date 입력의 6자리 연도 방지). */}
          <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)}
            min="1900-01-01" max={new Date().toISOString().slice(0, 10)}
            className="w-full rounded border px-2 py-1" required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">태어난 시간</span>
          <input type="time" value={birthTime} disabled={timeUnknown}
            onChange={(e) => setBirthTime(e.target.value)}
            className="w-full rounded border px-2 py-1 disabled:bg-gray-100" />
          <label className="mt-1 flex items-center gap-1 text-xs">
            <input type="checkbox" checked={timeUnknown} onChange={(e) => setTimeUnknown(e.target.checked)} />
            시간 모름
          </label>
        </label>
      </div>

      <div>
        <span className="mb-1 block text-sm font-medium">태어난 지역</span>
        <input value={query} onChange={(e) => { setQuery(e.target.value); setPlace(null); }}
          placeholder="도시 검색" className="w-full rounded border px-2 py-1 text-sm" />
        <div className="mt-1 flex max-h-32 flex-wrap gap-1 overflow-y-auto">
          {results.map((l) => (
            <button type="button" key={`${l.name}-${l.tz}`} onClick={() => setPlace(l)}
              className={`rounded border px-2 py-1 text-xs ${
                chosen?.name === l.name ? "border-gray-800 bg-gray-800 text-white" : "bg-white"
              }`}>
              {l.name}
            </button>
          ))}
        </div>
        {chosen && (
          <p className="mt-1 text-xs text-gray-500">
            선택: {chosen.name} ({chosen.region}) · {chosen.tz}
          </p>
        )}
      </div>

      <button type="submit" disabled={!chosen}
        className="w-full rounded bg-gray-900 py-2 text-white disabled:bg-gray-400">
        {submitLabel}
      </button>
    </form>
  );
}
