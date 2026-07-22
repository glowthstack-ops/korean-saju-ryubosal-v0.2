"use client";

// 온보딩 스텝 공통 셸 — 진행 표시·제목·스킵/다음/이전 바.

interface Props {
  step: number; // 0-based
  total: number;
  title: string;
  desc?: string;
  canSkip?: boolean;
  onSkip?: () => void;
  onBack?: () => void;
  children: React.ReactNode;
}

const LABELS = ["사주입력", "용신확정", "물상해석", "페르소나", "현실보정"];

export function StepShell({ step, total, title, desc, canSkip, onSkip, onBack, children }: Props) {
  return (
    <section className="space-y-4 rounded-lg bg-white p-6 shadow-sm">
      <div className="flex items-center gap-1.5">
        {Array.from({ length: total }).map((_, i) => (
          <div key={i} className="flex-1">
            <div className={`h-1 rounded ${i <= step ? "bg-gray-800" : "bg-gray-200"}`} />
            <p
              className={`mt-1 text-center text-[10px] ${
                i === step ? "font-medium text-gray-800" : "text-gray-400"
              }`}
            >
              {LABELS[i]}
            </p>
          </div>
        ))}
      </div>

      <div>
        <h1 className="text-xl font-bold">{title}</h1>
        {desc && <p className="mt-1 text-sm text-gray-500">{desc}</p>}
      </div>

      {children}

      <div className="flex items-center justify-between pt-2">
        {onBack ? (
          <button onClick={onBack} className="text-sm text-gray-500 hover:underline">
            ← 이전
          </button>
        ) : (
          <span />
        )}
        {canSkip && onSkip && (
          <button onClick={onSkip} className="text-sm text-gray-500 hover:underline">
            건너뛰기
          </button>
        )}
      </div>
    </section>
  );
}
