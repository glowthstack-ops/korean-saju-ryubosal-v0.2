"use client";

// 리포트 페이지 단위 뷰어 — 섹션을 한 장씩 넘겨 보고, 인쇄(PDF) 시 전체를 출력한다.
// 화면에서는 현재 섹션만 보이고, @media print에서는 모든 섹션이 보이도록 한다.

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { readingFontClasses } from "@/lib/storage";
import { useReadingFontSize } from "@/lib/useReadingFontSize";

export interface ReportSection {
  section_id: string;
  title: string;
  text: string;
}

export function ReportPager({ sections, title }: { sections: ReportSection[]; title: string }) {
  const [page, setPage] = useState(0);
  // 읽기 글자 크기(설정) — AI 채팅 상담과 공통. 본문 마크다운 크기에 적용한다.
  const { prose: proseFontCls } = readingFontClasses(useReadingFontSize());
  const total = sections.length;
  if (total === 0) return <p className="text-sm text-gray-500">표시할 섹션이 없습니다.</p>;

  return (
    // 하단 고정 페이저에 마지막 본문이 가리지 않도록 화면용 하단 패딩(인쇄 시 제거).
    <div className="pb-24 print:pb-0">
      {/* 인쇄 제목(인쇄 시에만) */}
      <h1 className="mb-4 hidden text-2xl font-bold print:block">{title}</h1>

      {sections.map((s, i) => (
        <article
          key={s.section_id}
          className={`${i === page ? "block" : "hidden"} print:mb-8 print:block print:break-after-page`}
        >
          <h2 className="mb-2 text-lg font-semibold">{s.title}</h2>
          <div
            className={`prose ${proseFontCls} max-w-none leading-relaxed
              prose-p:my-2 prose-li:my-0.5 prose-headings:mt-4 prose-headings:mb-1
              prose-table:my-3 prose-table:text-xs prose-th:bg-gray-50
              prose-th:px-2 prose-th:py-1 prose-th:border prose-th:align-top
              prose-td:px-2 prose-td:py-1 prose-td:border prose-td:align-top`}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // 넓은 점수표는 가로 스크롤 컨테이너로 감싸 모바일에서도 깨지지 않게.
                table: (props) => (
                  <div className="overflow-x-auto print:overflow-visible">
                    <table {...props} />
                  </div>
                ),
              }}
            >
              {s.text}
            </ReactMarkdown>
          </div>
        </article>
      ))}

      {/* 화면용 페이저 컨트롤 — 뷰포트 하단 고정(스크롤해도 항상 노출, 인쇄 시 숨김).
          내부 컨테이너는 본문과 동일한 max-w-4xl로 가운데 정렬. */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded border px-3 py-1 text-sm disabled:opacity-40"
          >
            ← 이전
          </button>
          <span className="truncate text-xs text-gray-500">
            {page + 1} / {total} · {sections[page].title}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(total - 1, p + 1))}
            disabled={page === total - 1}
            className="rounded border px-3 py-1 text-sm disabled:opacity-40"
          >
            다음 →
          </button>
        </div>
      </nav>
    </div>
  );
}
