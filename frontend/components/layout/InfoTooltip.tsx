"use client";

import { type CSSProperties, useLayoutEffect, useRef, useState } from "react";

// 항목별 설명 툴팁(클릭 토글).
// position:fixed + 뷰포트 좌표 클램프로, ancestor(overflow/transform)에 상관없이
// 항상 화면 안(좌·우 8px 여백)에 머물게 한다. 스크롤/리사이즈 시 닫아 위치 어긋남을 막는다.
export function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<CSSProperties>({ visibility: "hidden" });

  // 열린 즉시(페인트 전) 아이콘 위치를 재서 뷰포트 안으로 클램프한 좌표를 적용.
  useLayoutEffect(() => {
    if (!open) return;
    const btn = btnRef.current;
    const tip = tipRef.current;
    if (!btn || !tip) return;
    const b = btn.getBoundingClientRect();
    const margin = 8;
    const width = tip.offsetWidth;
    let left = Math.min(b.left, window.innerWidth - margin - width);
    left = Math.max(left, margin);
    setPos({ position: "fixed", left, top: b.bottom + 4, visibility: "visible" });
  }, [open, text]);

  // 스크롤/리사이즈 시 닫기(fixed 위치 드리프트 방지).
  useLayoutEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <span className="ml-1 inline-block align-middle">
      <button
        type="button"
        aria-label="설명 보기"
        ref={btnRef}
        onClick={() => {
          setPos({ visibility: "hidden" });
          setOpen((v) => !v);
        }}
        className="inline-flex h-4 w-4 cursor-pointer items-center justify-center rounded-full bg-gray-300 text-[10px] text-gray-700"
      >
        ?
      </button>
      {open && (
        <span
          ref={tipRef}
          style={pos}
          className="z-50 block w-64 max-w-[90vw] whitespace-normal rounded bg-gray-800 p-2 text-xs font-normal text-white shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}
