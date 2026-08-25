import type { Metadata } from "next";
import "./globals.css";
import { Gnb } from "@/components/layout/Gnb";
import { Providers } from "@/components/providers/Providers";

export const metadata: Metadata = {
  title: "류보살 v2 — 만세력 · 간지달력",
  description: "정밀 만세력, 대운·세운·월운, 간지달력을 제공하는 사주 서비스.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <Gnb />
          <main className="mx-auto max-w-4xl px-4 pt-6 pb-20">
            {/* 광고 영역은 무료 사용 흐름 확정 후 재도입 — AdSlot 컴포넌트는 보존. */}
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
