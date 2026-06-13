"use client";

// 즉석 상대 입력 폼 — 등록 없이 1회 궁합 분석에 쓸 상대 출생정보(InlineBirthDTO)를 받는다.
// 백엔드 _resolve_partner_birth가 inline_birth를 그대로 해석한다(시간 없으면 시주 제외).

import { useState } from "react";
import type { InlineBirthDTO } from "@/lib/types";

interface Props {
  onSubmit: (label: string, birth: InlineBirthDTO) => void;
}

export function InlinePartnerForm({ onSubmit }: Props) {
  const [label, setLabel] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [calendar, setCalendar] = useState<"solar" | "lunar">("solar");
  const [gender, setGender] = useState<"M" | "F">("F");
  const [birthplace, setBirthplace] = useState("");

  const valid = date.length === 10 && (timeUnknown || time.length >= 4);

  function submit() {
    if (!valid) return;
    onSubmit(label.trim() || "상대", {
      date,
      time: timeUnknown ? null : time,
      calendar_type: calendar,
      gender,
      birthplace: birthplace.trim() || null,
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
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
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

      <label className="block">
        <span className="text-xs text-gray-500">출생지(선택)</span>
        <input
          value={birthplace}
          onChange={(e) => setBirthplace(e.target.value)}
          placeholder="예: 서울"
          className="mt-0.5 w-full rounded border px-2 py-1.5"
        />
      </label>

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
