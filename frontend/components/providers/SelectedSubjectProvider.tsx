"use client";

// 현재 선택된 사주(대상)와 동반자를 보관하는 컨텍스트.
// sessionStorage에 캐시해 새로고침에도 유지한다(민감정보가 아닌 식별자만). 서비스(만세력·
// 테마·채팅)는 이 컨텍스트로 "누구의 사주인가"를 공유하며, 별명만 표시용으로 함께 캐시한다.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

interface SelectedSubject {
  subjectId: string;
  label: string;
}

interface SelectedSubjectState {
  selected: SelectedSubject | null;
  companion: SelectedSubject | null;
  setSelected: (s: SelectedSubject | null) => void;
  setCompanion: (s: SelectedSubject | null) => void;
  clear: () => void;
}

const Ctx = createContext<SelectedSubjectState | null>(null);
const KEY = "ryubosal:selectedSubject";
const COMPANION_KEY = "ryubosal:selectedCompanion";

function read(key: string): SelectedSubject | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as SelectedSubject) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: SelectedSubject | null): void {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value));
    else sessionStorage.removeItem(key);
  } catch {
    /* 접근 불가 시 무시 */
  }
}

export function SelectedSubjectProvider({ children }: { children: React.ReactNode }) {
  const [selected, setSelectedState] = useState<SelectedSubject | null>(null);
  const [companion, setCompanionState] = useState<SelectedSubject | null>(null);

  useEffect(() => {
    setSelectedState(read(KEY));
    setCompanionState(read(COMPANION_KEY));
  }, []);

  const setSelected = useCallback((s: SelectedSubject | null) => {
    setSelectedState(s);
    write(KEY, s);
  }, []);

  const setCompanion = useCallback((s: SelectedSubject | null) => {
    setCompanionState(s);
    write(COMPANION_KEY, s);
  }, []);

  const clear = useCallback(() => {
    setSelected(null);
    setCompanion(null);
  }, [setSelected, setCompanion]);

  const value = useMemo<SelectedSubjectState>(
    () => ({ selected, companion, setSelected, setCompanion, clear }),
    [selected, companion, setSelected, setCompanion, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelectedSubject(): SelectedSubjectState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSelectedSubject must be used within SelectedSubjectProvider");
  return ctx;
}

export type { SelectedSubject };
