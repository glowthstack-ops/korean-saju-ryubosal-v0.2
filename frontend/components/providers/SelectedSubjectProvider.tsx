"use client";

// 현재 선택된 사주(대상)와 동반자를 보관하는 컨텍스트.
// sessionStorage에 캐시해 새로고침에도 유지한다(민감정보가 아닌 식별자만). 서비스(만세력·
// 테마·채팅)는 이 컨텍스트로 "누구의 사주인가"를 공유하며, 별명만 표시용으로 함께 캐시한다.
// 캐시에는 선택 당시의 로그인 ID(owner)를 함께 새겨, 다른 사용자로 로그인하거나 로그아웃한
// 뒤 이전 선택이 남는 일을 막는다. 또한 reconcile()로 실제 사주목록과 대조해 삭제된 선택을 정리한다.
//
// 재로그인 복원(2026-07-23): 선택 사주를 계정 설정(last-subject)에 서버 영속한다.
// - 저장: latest-write-wins 직렬 저장기 — UI는 즉시 반영, 서버 PUT은 400ms trailing
//   debounce(새 값이 이전 예약을 덮음), 진행 중 요청 뒤에는 최신 pending 1개만 전송.
// - 복원: 로그인 시 로컬 캐시가 없으면 서버 값을 조회해 복원(isRestoring 동안 소비자는
//   스켈레톤 표시 — 이전 계정 값 노출·CTA 깜빡임 방지). localStorage(간지달력 기준)와 동기화.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  getLastSubject,
  getSubject,
  putLastSubject,
  setSelectedSubjectId,
} from "@/lib/subjects";

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
  // 서버 last-subject 복원 진행 중 — 소비자(메인 카드 등)는 CTA 대신 스켈레톤 표시.
  isRestoring: boolean;
  setSelected: (s: SelectedSubject | null) => void;
  setCompanion: (s: SelectedSubject | null) => void;
  clear: () => void;
  // 권위 있는 사주목록(유효 id 집합)과 대조해, 목록에 없는 선택/동반자를 비운다.
  reconcile: (validIds: string[]) => void;
}

const Ctx = createContext<SelectedSubjectState | null>(null);
const KEY = "ryubosal:selectedSubject";
const COMPANION_KEY = "ryubosal:selectedCompanion";
const SAVE_DEBOUNCE_MS = 400;

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
  const [isRestoring, setIsRestoring] = useState(false);

  // ── latest-write-wins 서버 저장기 ──────────────────────────────
  // pending = 아직 전송하지 않은 최신 값 1개(중간값은 덮어씀). in-flight 완료 후 재전송.
  const pendingRef = useRef<{ value: string | null } | null>(null);
  const inFlightRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSave = useCallback(() => {
    if (inFlightRef.current) return;
    const p = pendingRef.current;
    if (!p) return;
    pendingRef.current = null;
    inFlightRef.current = true;
    putLastSubject(p.value)
      .catch(() => {
        /* 서버 저장 실패 — 로컬 선택은 유지(다음 선택 시 재시도) */
      })
      .finally(() => {
        inFlightRef.current = false;
        if (pendingRef.current) runSave();
      });
  }, []);

  const scheduleServerSave = useCallback(
    (value: string | null) => {
      pendingRef.current = { value };
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(runSave, SAVE_DEBOUNCE_MS);
    },
    [runSave],
  );

  // 로그아웃·계정 전환·unmount 시 예약 취소(이전 계정으로의 뒤늦은 전송 방지)
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      pendingRef.current = null;
    };
  }, [loginId]);

  // 로그인 정체성과 캐시를 대조한다. owner가 현재 로그인 ID와 다르면(다른 사용자·로그아웃·
  // 구버전 캐시) 폐기한다. 캐시가 없고 로그인 상태면 서버 last-subject로 복원한다.
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

    if (vs || !loginId) {
      setIsRestoring(false);
      if (vs) setSelectedSubjectId(vs.subjectId); // 간지달력 기준(localStorage) 동기화
      return;
    }
    // 서버 복원 — 응답 전에는 이전 계정 로컬 값을 쓰지 않는다(스켈레톤).
    let cancelled = false;
    setIsRestoring(true);
    (async () => {
      try {
        const id = await getLastSubject();
        if (cancelled || !id) return;
        const summary = await getSubject(id);
        if (cancelled) return;
        const restored = { subjectId: id, label: summary.label };
        setSelectedState(restored);
        write(KEY, { ...restored, owner: loginId });
        setSelectedSubjectId(id);
      } catch {
        /* 서버 미응답(503 등) — 복원 없이 진행, 로컬 신규 선택은 정상 동작 */
      } finally {
        if (!cancelled) setIsRestoring(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authReady, loginId]);

  const setSelected = useCallback(
    (s: SelectedSubject | null) => {
      setSelectedState(s);
      write(KEY, s ? { ...s, owner: loginId } : null);
      setSelectedSubjectId(s?.subjectId ?? null);
      if (loginId) scheduleServerSave(s?.subjectId ?? null);
    },
    [loginId, scheduleServerSave],
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
    () => ({ selected, companion, isRestoring, setSelected, setCompanion, clear, reconcile }),
    [selected, companion, isRestoring, setSelected, setCompanion, clear, reconcile],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelectedSubject(): SelectedSubjectState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSelectedSubject must be used within SelectedSubjectProvider");
  return ctx;
}

export type { SelectedSubject };
