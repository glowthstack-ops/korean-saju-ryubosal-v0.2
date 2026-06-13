"use client";

// 사주 1건 카드 — 별명 + 생년월일시 + 용신/물상 등록여부 인디케이터 + (옵션)액션 버튼.
// 목록(관리)과 게이트웨이(선택) 양쪽에서 재사용한다. 액션은 props 콜백으로 주입.

import type { SubjectSummary } from "@/lib/types";

function formatBirth(s: SubjectSummary): string {
  const b = s.birth;
  const cal = b.calendar_type === "lunar" ? "음력" : "양력";
  const time = b.birth_time_unknown ? "시간모름" : (b.birth_time?.slice(0, 5) ?? "시간모름");
  const g = b.gender === "female" || s.gender === "female" ? "여" : "남";
  return `${b.birth_date} ${time} · ${cal} · ${g}`;
}

interface Props {
  subject: SubjectSummary;
  active?: boolean;
  onSelect?: (s: SubjectSummary) => void;
  onEdit?: (s: SubjectSummary) => void;
  onDelete?: (s: SubjectSummary) => void;
}

export function SubjectCard({ subject, active, onSelect, onEdit, onDelete }: Props) {
  const clickable = !!onSelect;
  return (
    <div
      onClick={clickable ? () => onSelect?.(subject) : undefined}
      className={`rounded-lg border bg-white p-4 shadow-sm transition ${
        clickable ? "cursor-pointer hover:shadow" : ""
      } ${active ? "ring-2 ring-blue-500" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">
            {subject.label}
            {subject.kind === "companion" && (
              <span className="ml-1 rounded bg-purple-50 px-1.5 py-0.5 text-[10px] text-purple-600">
                동반자
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs text-gray-500">{formatBirth(subject)}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Indicator on={subject.yongsin_registered} label="용신" />
          <Indicator on={subject.mulsang_registered} label="물상" />
        </div>
      </div>

      {(onEdit || onDelete) && (
        <div className="mt-3 flex gap-2 text-xs">
          {onEdit && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit(subject);
              }}
              className="rounded border px-2 py-1 text-gray-600 hover:bg-gray-50"
            >
              수정
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(subject);
              }}
              className="rounded border border-red-200 px-2 py-1 text-red-500 hover:bg-red-50"
            >
              삭제
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Indicator({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      title={`${label} ${on ? "등록됨" : "미등록"}`}
      className={`rounded px-1.5 py-0.5 text-[10px] ${
        on ? "bg-emerald-50 text-emerald-600" : "bg-gray-100 text-gray-400"
      }`}
    >
      {label}
      {on ? "✓" : "–"}
    </span>
  );
}
