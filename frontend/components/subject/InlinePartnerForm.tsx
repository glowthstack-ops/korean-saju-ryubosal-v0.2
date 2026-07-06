"use client";

// 즉석 상대 입력 폼 — 등록 없이 1회 궁합 분석에 쓸 상대 출생정보(InlineBirthDTO)를 받는다.
// 백엔드 _resolve_partner_birth가 inline_birth를 그대로 해석한다(시간 없으면 시주 제외).
// 출생지는 자유 텍스트가 아니라 지역 피커(BirthForm과 동일 목록)로 선택 — 선택 지명의
// 좌표·tz를 함께 보내 백엔드 지명 시드와 무관하게 경도 보정이 정확하다(2026-07-03 수정).

import { useMemo, useState } from "react";
import { searchLocations } from "@/lib/locations";
import type { InlineBirthDTO, SajuLocation } from "@/lib/types";

interface Props {
  onSubmit: (label: string, birth: InlineBirthDTO) => void;
}

const TODAY_ISO = new Date().toISOString().slice(0, 10);

export function InlinePartnerForm({ onSubmit }: Props) {
  const [label, setLabel] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [calendar, setCalendar] = useState<"solar" | "lunar">("solar");
  const [gender, setGender] = useState<"M" | "F">("F");
  const [placeQuery, setPlaceQuery] = useState("");
  const [place, setPlace] = useState<SajuLocation | null>(null);

  const placeResults = useMemo(
    () => (placeQuery.trim() ? searchLocations(placeQuery).slice(0, 8) : []),
    [placeQuery],
  );

  const valid = date.length === 10 && (timeUnknown || time.length >= 4);

  function submit() {
    if (!valid) return;
    onSubmit(label.trim() || "상대", {
      date,
      time: timeUnknown ? null : time,
      calendar_type: calendar,
      gender,
      birthplace: place?.name ?? null,
      latitude: place?.lat ?? null,
      longitude: place?.lon ?? null,
      timezone: place?.tz ?? null,
    });
  }

  return (
    <div className="space-y-2.5 text-sm">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-gray-500">호칭(선택)</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="상대"
            className="mt-0.5 w-full rounded border px-2 py-1.5"
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500">생년월일</span>
          {/* min/max로 연도 입력을 4자리로 제한 — 없으면 브라우저가 6자리 연도를 허용해
              4자 입력 후 월 칸으로 자동 이동하지 않는다(BirthForm과 동일 처리). */}
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            min="1900-01-01"
            max={TODAY_ISO}
            className="mt-0.5 w-full rounded border px-2 py-1.5"
          />
        </label>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-gray-500">태어난 시간</span>
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            disabled={timeUnknown}
            className="mt-0.5 w-full rounded border px-2 py-1.5 disabled:bg-gray-100"
          />
        </label>
        <label className="mt-5 flex items-center gap-1.5 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={timeUnknown}
            onChange={(e) => setTimeUnknown(e.target.checked)}
          />
          시간 모름(시주 제외)
        </label>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="flex gap-1.5">
          {(["solar", "lunar"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCalendar(c)}
              className={`rounded border px-2.5 py-1 text-xs ${
                calendar === c ? "border-indigo-300 bg-indigo-50 font-medium" : ""
              }`}
            >
              {c === "solar" ? "양력" : "음력"}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          {(["F", "M"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGender(g)}
              className={`rounded border px-2.5 py-1 text-xs ${
                gender === g ? "border-indigo-300 bg-indigo-50 font-medium" : ""
              }`}
            >
              {g === "F" ? "여성" : "남성"}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="text-xs text-gray-500">출생지(선택)</span>
        <input
          value={placeQuery}
          onChange={(e) => {
            setPlaceQuery(e.target.value);
            setPlace(null);
          }}
          placeholder="도시 검색 (예: 서울, 성남시 분당구)"
          className="mt-0.5 w-full rounded border px-2 py-1.5"
        />
        {placeResults.length > 0 && !place && (
          <div className="mt-1 flex max-h-24 flex-wrap gap-1 overflow-y-auto">
            {placeResults.map((l) => (
              <button
                type="button"
                key={`${l.name}-${l.tz}`}
                onClick={() => {
                  setPlace(l);
                  setPlaceQuery(l.name);
                }}
                className="rounded border bg-white px-2 py-1 text-xs"
              >
                {l.name}
              </button>
            ))}
          </div>
        )}
        <p className="mt-0.5 text-[11px] text-gray-400">
          {place
            ? `선택: ${place.name} (${place.region})`
            : "목록에서 선택해 주세요. 미선택 시 서울 기준으로 계산돼요."}
        </p>
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={!valid}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        이 상대와 궁합 보기 →
      </button>
    </div>
  );
}
