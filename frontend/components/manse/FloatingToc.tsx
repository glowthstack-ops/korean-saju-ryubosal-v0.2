"use client";

import { useEffect, useRef, useState } from "react";

export type TocItem = { id: string; label: string };

/**
 * 만세력 결과 페이지 우측 중앙(상하 기준)에 떠 있는 목차 이동 버튼.
 *
 * 노션(Notion) 스타일: 평소엔 섹션마다 얇은 가로 막대(dash)만 반투명하게 노출하고,
 * 마우스를 올리면(데스크톱) 또는 막대를 탭하면(모바일) 반투명·블러 패널로 펼쳐져
 * 섹션 이름 목록을 보여준다. 스크롤 위치에 따라 현재 섹션을 강조(scroll spy)한다.
 * 모든 화면 크기에서 표시한다.
 */
export function FloatingToc({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string | null>(items[0]?.id ?? null);
  const [open, setOpen] = useState(false);
  const navRef = useRef<HTMLElement | null>(null);

  // 모바일(호버 불가)에서 펼친 뒤 바깥을 탭하면 닫는다.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  // 스크롤 스파이: 화면 중앙 부근에 걸친 섹션을 현재 항목으로 본다.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const hit = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (hit) setActive(hit.target.id);
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 },
    );
    for (const it of items) {
      const el = document.getElementById(it.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [items]);

  const go = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setOpen(false); // 모바일: 항목 선택 후 패널을 닫는다.
  };

  return (
    <nav
      ref={navRef}
      aria-label="목차"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      // 화면(뷰포트) 오른쪽 끝에 고정. 모바일 노출은 hidden 제거로 해결했다.
      className="fixed right-0 top-1/2 z-40 block -translate-y-1/2"
    >
      {/* pl-10: 막대 왼쪽으로 보이지 않는 hover 영역을 넓혀 펼치기 쉽게 한다. */}
      <div className="flex justify-end py-3 pl-10 pr-2">
        {open ? (
          <ul className="max-h-[80vh] overflow-auto rounded-xl border border-gray-200/60 bg-white/70 p-1.5 shadow-lg backdrop-blur-md">
            {items.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  onClick={() => go(it.id)}
                  className={`block w-full whitespace-nowrap rounded-lg px-3 py-1 text-right text-xs transition-colors hover:bg-gray-100/80 ${
                    active === it.id ? "font-semibold text-gray-900" : "text-gray-500"
                  }`}
                >
                  {it.label}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          // 모바일(호버 불가)에서 탭하면 펼친다. py-1로 터치 영역을 넓힌다.
          <button
            type="button"
            aria-label="목차 펼치기"
            onClick={() => setOpen(true)}
            className="flex flex-col items-end gap-1.5 py-1"
          >
            {items.map((it) => (
              <span
                key={it.id}
                className={`h-0.5 rounded-full transition-all duration-200 ${
                  active === it.id ? "w-6 bg-gray-500/80" : "w-3.5 bg-gray-300/70"
                }`}
              />
            ))}
          </button>
        )}
      </div>
    </nav>
  );
}
