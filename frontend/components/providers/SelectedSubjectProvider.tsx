"use client";

// 현재 선택된 사주(대상)와 동반자를 보관하는 컨텍스트.
// sessionStorage에 캐시해 새로고침에도 유지한다(민감정보가 아닌 식별자만). 서비스(만세력·
// 테마·채팅)는 이 컨텍스트로 "누구의 사주인가"를 공유하며, 별명만 표시용으로 함께 캐시한다.
// 캐시에는 선택 당시의 로그인 ID(owner)를 함께 새겨, 다른 사용자로 로그인하거나 로그아웃한
// 뒤 이전 선택이 남는 일을 막는다. 또한 reconcile()로 실제 사주목록과 대조해 삭제된 선택을 정리한다.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";

interface SelectedSubject {
  subjectId: string;
  label: string;
}

// 저장 포맷 — 선택 당시의 소유 계정(owner)을 함께 보관한다.
interface StoredSubject extends SelectedSubject {
  owner: string | null;
}

interface SelectedSubjectState {
  selected: SelectedSubject | null;
  companion: SelectedSubject | null;
  setSelected: (s: SelectedSubject | null) => void;
  setCompanion: (s: SelectedSubject | null) => void;
  clear: () => void;
  // 권위 있는 사주목록(유효 id 집합)과 대조해, 목록에 없는 선택/동반자를 비운다.
  reconcile: (validIds: string[]) => void;
}

const Ctx = createContext<SelectedSubjectState | null>(null);
const KEY = "ryubosal:selectedSubject";
const COMPANION_KEY = "ryubosal:selectedCompanion";

function read(key: string): StoredSubject | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as StoredSubject) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: StoredSubject | null): void {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value));
    else sessionStorage.removeItem(key);
  } catch {
    /* 접근 불가 시 무시 */
  }
}

function strip(v: StoredSubject | null): SelectedSubject | null {
  return v ? { subjectId: v.subjectId, label: v.label } : null;
}

export function SelectedSubjectProvider({ children }: { children: React.ReactNode }) {
  const { ready: authReady, loginId } = useAuth();
  const [selected, setSelectedState] = useState<SelectedSubject | null>(null);
  const [companion, setCompanionState] = useState<SelectedSubject | null>(null);

  // 로그인 정체성과 캐시를 대조한다. owner가 현재 로그인 ID와 다르면(다른 사용자·로그아웃·
  // 구버전 캐시) 폐기한다. authReady/loginId가 바뀔 때마다 재검증한다.
  useEffect(() => {
    if (!authReady) return;
    const s = read(KEY);
    const c = read(COMPANION_KEY);
    const valid = (v: StoredSubject | null) => (v && v.owner === loginId ? strip(v) : null);
    const vs = valid(s);
    const vc = valid(c);
    if (s && !vs) write(KEY, null);
    if (c && !vc) write(COMPANION_KEY, null);
    setSelectedState(vs);
    setCompanionState(vc);
  }, [authReady, loginId]);

  const setSelected = useCallback(
    (s: SelectedSubject | null) => {
      setSelectedState(s);
      write(KEY, s ? { ...s, owner: loginId } : null);
    },
    [loginId],
  );

  const setCompanion = useCallback(
    (s: SelectedSubject | null) => {
      setCompanionState(s);
      write(COMPANION_KEY, s ? { ...s, owner: loginId } : null);
    },
    [loginId],
  );

  const clear = useCallback(() => {
    setSelected(null);
    setCompanion(null);
  }, [setSelected, setCompanion]);

  // 권위 있는 목록과 대조 — 목록에 없는 선택/동반자를 비운다(삭제·빈 목록 정리).
  // 의존성 없이 안정적이도록 함수형 업데이트를 쓰고, 변동 시에만 캐시를 정리한다.
  const reconcile = useCallback((validIds: string[]) => {
    const ids = new Set(validIds);
    setSelectedState((cur) => {
      if (cur && !ids.has(cur.subjectId)) {
        write(KEY, null);
        return null;
      }
      return cur;
    });
    setCompanionState((cur) => {
      if (cur && !ids.has(cur.subjectId)) {
        write(COMPANION_KEY, null);
        return null;
      }
      return cur;
    });
  }, []);

  const value = useMemo<SelectedSubjectState>(
    () => ({ selected, companion, setSelected, setCompanion, clear, reconcile }),
    [selected, companion, setSelected, setCompanion, clear, reconcile],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelectedSubject(): SelectedSubjectState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSelectedSubject must be used within SelectedSubjectProvider");
  return ctx;
}

export type { SelectedSubject };
