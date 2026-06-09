"use client";

import { useEffect, useState } from "react";

export type TocItem = { id: string; label: string };

/**
 * 만세력 결과 페이지 우측 중앙(상하 기준)에 떠 있는 목차 이동 버튼.
 *
 * 노션(Notion) 스타일: 평소엔 섹션마다 얇은 가로 막대(dash)만 반투명하게 노출하고,
 * 마우스를 올리면 반투명·블러 패널로 펼쳐져 섹션 이름 목록을 보여준다. 스크롤 위치에
 * 따라 현재 섹션을 강조(scroll spy)한다. 데스크톱(>=md)에서만 표시한다.
 */
export function FloatingToc({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string | null>(items[0]?.id ?? null);
  const [open, setOpen] = useState(false);

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
  };

  return (
    <nav
      aria-label="목차"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      className="fixed right-0 top-1/2 z-40 hidden -translate-y-1/2 lg:block"
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
          <ul className="flex flex-col items-end gap-1.5">
            {items.map((it) => (
              <li
                key={it.id}
                className={`h-0.5 rounded-full transition-all duration-200 ${
                  active === it.id ? "w-6 bg-gray-500/80" : "w-3.5 bg-gray-300/70"
                }`}
              />
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
