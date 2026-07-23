"use client";

// 일간(10천간) 탭 — 갑목~계수(천간+오행 병기). 탭당 6개 일주가 리스팅된다.
// active/onChange 값은 한글 천간 1자("갑" 등, DailyIljuFortune.day_stem_ko와 일치).

const STEMS: { stem: string; label: string }[] = [
  { stem: "갑", label: "갑목" },
  { stem: "을", label: "을목" },
  { stem: "병", label: "병화" },
  { stem: "정", label: "정화" },
  { stem: "무", label: "무토" },
  { stem: "기", label: "기토" },
  { stem: "경", label: "경금" },
  { stem: "신", label: "신금" },
  { stem: "임", label: "임수" },
  { stem: "계", label: "계수" },
];

export function StemTabs({
  active,
  onChange,
}: {
  active: string;
  onChange: (stem: string) => void;
}) {
  return (
    <div className="flex flex-wrap justify-center gap-1">
      {STEMS.map((s) => (
        <button
          key={s.stem}
          onClick={() => onChange(s.stem)}
          className={`rounded px-3 py-1.5 text-sm ${
            active === s.stem
              ? "bg-gray-800 font-medium text-white"
              : "border bg-white text-gray-600"
          }`}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}

export const STEM_TABS = STEMS;
