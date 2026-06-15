"use client";

// 리포트 페이지 단위 뷰어 — 섹션을 한 장씩 넘겨 보고, 인쇄(PDF) 시 전체를 출력한다.
// 화면에서는 현재 섹션만 보이고, @media print에서는 모든 섹션이 보이도록 한다.

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface ReportSection {
  section_id: string;
  title: string;
  text: string;
}

export function ReportPager({ sections, title }: { sections: ReportSection[]; title: string }) {
  const [page, setPage] = useState(0);
  const total = sections.length;
  if (total === 0) return <p className="text-sm text-gray-500">표시할 섹션이 없습니다.</p>;

  return (
    <div>
      {/* 화면용 페이저 컨트롤(인쇄 시 숨김) */}
      <div className="mb-3 flex items-center justify-between print:hidden">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0}
          className="rounded border px-3 py-1 text-sm disabled:opacity-40"
        >
          ← 이전
        </button>
        <span className="text-xs text-gray-500">
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

      {/* 인쇄 제목(인쇄 시에만) */}
      <h1 className="mb-4 hidden text-2xl font-bold print:block">{title}</h1>

      {sections.map((s, i) => (
        <article
          key={s.section_id}
          className={`${i === page ? "block" : "hidden"} print:mb-8 print:block print:break-after-page`}
        >
          <h2 className="mb-2 text-lg font-semibold">{s.title}</h2>
          <div
            className="prose prose-sm max-w-none leading-relaxed
              prose-p:my-2 prose-li:my-0.5 prose-headings:mt-4 prose-headings:mb-1
              prose-table:my-3 prose-table:text-xs prose-th:bg-gray-50
              prose-th:px-2 prose-th:py-1 prose-th:border prose-th:align-top
              prose-td:px-2 prose-td:py-1 prose-td:border prose-td:align-top"
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
    </div>
  );
}
