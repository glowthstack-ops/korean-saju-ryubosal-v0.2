import type { Metadata } from "next";
import "./globals.css";
import { AdSlot } from "@/components/layout/AdSlot";
import { Nav } from "@/components/layout/Nav";

export const metadata: Metadata = {
  title: "류보살 v2 — 만세력 · 간지달력",
  description: "정밀 만세력, 대운·세운·월운, 간지달력을 제공하는 사주 서비스.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Nav />
        <main className="mx-auto max-w-3xl px-4 py-6">
          <AdSlot label="상단 광고" />
          {children}
          <AdSlot label="하단 광고" />
        </main>
        <footer className="border-t bg-white py-6 text-center text-xs text-gray-400">
          류보살 v2 · 계산은 결정론적 만세력 엔진, 개인정보는 브라우저에만 암호화 저장됩니다.
        </footer>
      </body>
    </html>
  );
}
