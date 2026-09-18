"use client";

// PDF 저장 — 브라우저 인쇄 대화상자(대상: PDF로 저장). 서버 docx→pdf 파이프라인은 추후(docs/10 8장).
//
// 저장 파일명은 브라우저가 document.title 을 쓴다. 모든 테마가 같은 레이아웃 제목을
// 공유하면 파일명이 전부 동일해지므로(2026-08-24 사용자 지적), 인쇄 직전에 제목을
// 내용 식별용 파일명으로 바꾸고 인쇄가 끝나면 복원한다.

export function PdfExportButton({ filename }: { filename?: string }) {
  const handlePrint = () => {
    if (!filename) {
      window.print();
      return;
    }
    const prev = document.title;
    const restore = () => {
      document.title = prev;
      window.removeEventListener("afterprint", restore);
    };
    window.addEventListener("afterprint", restore);
    document.title = filename;
    window.print();
  };
  return (
    <button
      onClick={handlePrint}
      className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white print:hidden"
    >
      PDF로 저장 / 인쇄
    </button>
  );
}
