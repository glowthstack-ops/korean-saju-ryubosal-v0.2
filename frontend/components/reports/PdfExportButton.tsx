"use client";

// PDF 저장 — 브라우저 인쇄 대화상자(대상: PDF로 저장). 서버 docx→pdf 파이프라인은 추후(docs/10 8장).

export function PdfExportButton() {
  return (
    <button
      onClick={() => window.print()}
      className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white print:hidden"
    >
      PDF로 저장 / 인쇄
    </button>
  );
}
