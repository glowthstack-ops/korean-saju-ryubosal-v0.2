"use client";

// 일간(10천간) 탭 — 갑~계. 탭당 6개 일주가 리스팅된다.

const STEMS = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"];

export function StemTabs({
  active,
  onChange,
}: {
  active: string;
  onChange: (stem: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {STEMS.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`rounded px-3 py-1.5 text-sm ${
            active === s ? "bg-gray-800 font-medium text-white" : "border bg-white text-gray-600"
          }`}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

export const STEM_TABS = STEMS;
