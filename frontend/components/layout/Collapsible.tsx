"use client";

import type { ReactNode } from "react";

// 접이식 정보 카드 — 만세력 페이지의 '대운 상세 정리'·'격 후보'·'원국 구조 상세'가 공유하는 통일 디자인
// (2026-09-22 데굴님 지시). 접히는 동작은 브라우저 <details> 그대로 두고, 펼칠 수 있는 정보임을
// 눈에 띄게 한다: 테두리 카드 + 회전 화살표 + '펼쳐서 보기/접기' 힌트(숫자 배지 없음 — 데굴님 지시).
export function Collapsible({
  title,
  defaultOpen = false,
  className = "",
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      className={`group rounded-lg border border-gray-200 bg-white text-xs text-gray-600 shadow-sm open:border-gray-300 open:bg-gray-50 ${className}`}
    >
      <summary className="flex cursor-pointer list-none select-none items-center justify-between gap-2 rounded-lg px-3 py-3 hover:bg-gray-50 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-1.5 font-semibold text-gray-700">
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform duration-200 group-open:rotate-90"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M7 5l6 5-6 5" />
          </svg>
          {title}
        </span>
        <span className="text-[10px] font-normal text-gray-400">
          <span className="group-open:hidden">펼쳐서 보기</span>
          <span className="hidden group-open:inline">접기</span>
        </span>
      </summary>
      <div className="border-t border-gray-200 px-3 pb-3 pt-2">{children}</div>
    </details>
  );
}
