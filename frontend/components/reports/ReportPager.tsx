"use client";

// 리포트 페이지 단위 뷰어 — 섹션을 한 장씩 넘겨 보고, 목차에서 원하는 장으로 바로 이동한다.
// 화면에서는 현재 섹션만 보이고, @media print에서는 모든 섹션이 보이도록 한다.
// 섹션 제목은 사용자 친화 표시(section-display) — 백엔드 규격 제목은 그대로 두고 표시만 대체.

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sectionBlurb, sectionLabel } from "@/lib/section-display";
import { readingFontClasses } from "@/lib/storage";
import { useReadingFontSize } from "@/lib/useReadingFontSize";

export interface ReportSection {
  section_id: string;
  title: string;
  text: string;
}

export function ReportPager({ sections, title }: { sections: ReportSection[]; title: string }) {
  const [page, setPage] = useState(0);
  const [tocOpen, setTocOpen] = useState(false);
  // 읽기 글자 크기(설정) — AI 채팅 상담과 공통. 본문 마크다운 크기에 적용한다.
  const { prose: proseFontCls } = readingFontClasses(useReadingFontSize());
  const total = sections.length;
  if (total === 0) return <p className="text-sm text-gray-500">표시할 섹션이 없습니다.</p>;

  // 친화 표시 제목(원본 title 폴백) — 화면·목차·페이저 공용.
  const displayTitle = (s: ReportSection) => sectionLabel(s.section_id, s.title);
  const goTo = (i: number) => {
    setPage(i);
    setTocOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const current = sections[page];
  const blurb = sectionBlurb(current.section_id);

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
          <h2 className="mb-1 text-lg font-semibold">{displayTitle(s)}</h2>
          {/* 한 줄 설명 — 이 장에서 무엇을 알 수 있는지(화면 전용, 인쇄 시 숨김). */}
          {i === page && blurb && (
            <p className="mb-3 text-xs text-gray-400 print:hidden">{blurb}</p>
          )}
          <div
            className={`prose ${proseFontCls} max-w-none leading-relaxed
              prose-p:my-2 prose-li:my-0.5 prose-headings:mt-4 prose-headings:mb-1
              prose-table:my-3 prose-table:text-xs prose-th:bg-gray-50
              prose-th:px-2 prose-th:py-1 prose-th:border prose-th:align-top
              prose-td:px-2 prose-td:py-1 prose-td:border prose-td:align-top`}
          >
            <ReactMarkdown
              // singleTilde 비활성 — '1~2개월' 같은 범위 표기가 취소선으로 잘못 렌더되지 않게.
              remarkPlugins={[[remarkGfm, { singleTilde: false }]]}
              components={{
                // 넓은 점수표는 가로 스크롤 컨테이너로 감싸 모바일에서도 깨지지 않게.
                table: (props) => (
                  <div className="overflow-x-auto print:overflow-visible">
                    <table {...props} />
                  </div>
                ),
                // 취소선(고쳐 지운 자취)은 사용자에게 의문만 준다 — 표시하지 않는다(기존 리포트 대비).
                del: () => null,
              }}
            >
              {s.text}
            </ReactMarkdown>
          </div>
        </article>
      ))}

      {/* 목차 드로어(오버레이) — 화면 전용. 원하는 장으로 바로 이동한다. */}
      {tocOpen && (
        <div className="fixed inset-0 z-50 print:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setTocOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[70vh] overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-80 sm:rounded-none">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">목차</h3>
              <button
                onClick={() => setTocOpen(false)}
                className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
              >
                닫기 ✕
              </button>
            </div>
            <ol className="space-y-0.5">
              {sections.map((s, i) => (
                <li key={s.section_id}>
                  <button
                    onClick={() => goTo(i)}
                    className={`w-full rounded px-2 py-2 text-left text-sm ${
                      i === page
                        ? "bg-gray-800 text-white"
                        : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    <span className="mr-1.5 text-xs opacity-60">{i + 1}.</span>
                    {displayTitle(s)}
                    {sectionBlurb(s.section_id) && (
                      <span
                        className={`mt-0.5 block text-[11px] ${
                          i === page ? "text-gray-300" : "text-gray-400"
                        }`}
                      >
                        {sectionBlurb(s.section_id)}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}

      {/* 화면용 페이저 컨트롤 — 뷰포트 하단 고정(스크롤해도 항상 노출, 인쇄 시 숨김).
          가운데 버튼을 누르면 목차 드로어가 열린다. */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-2 px-4 py-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded border px-3 py-1 text-sm disabled:opacity-40"
          >
            ← 이전
          </button>
          <button
            onClick={() => setTocOpen(true)}
            className="flex-1 truncate rounded px-2 py-1 text-center text-xs text-gray-600 hover:bg-gray-100"
            title="목차 열기"
          >
            ☰ {page + 1} / {total} · {displayTitle(current)}
          </button>
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
