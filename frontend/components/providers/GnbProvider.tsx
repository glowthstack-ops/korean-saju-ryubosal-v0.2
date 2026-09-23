"use client";

// GNB 드로어 열림 상태 — 헤더의 햄버거 버튼 외에도 페이지 안의 [로그인] 버튼 등
// 어디서든 사이드바(계정 패널 포함)를 열 수 있도록 전역 컨텍스트로 둔다.

import { createContext, useCallback, useContext, useMemo, useState } from "react";

interface GnbContextValue {
  open: boolean;
  openGnb: () => void;
  closeGnb: () => void;
}

const GnbContext = createContext<GnbContextValue | null>(null);

export function GnbProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const openGnb = useCallback(() => setOpen(true), []);
  const closeGnb = useCallback(() => setOpen(false), []);
  const value = useMemo(() => ({ open, openGnb, closeGnb }), [open, openGnb, closeGnb]);
  return <GnbContext.Provider value={value}>{children}</GnbContext.Provider>;
}

export function useGnb(): GnbContextValue {
  const ctx = useContext(GnbContext);
  if (!ctx) throw new Error("useGnb는 GnbProvider 안에서만 사용할 수 있습니다.");
  return ctx;
}
