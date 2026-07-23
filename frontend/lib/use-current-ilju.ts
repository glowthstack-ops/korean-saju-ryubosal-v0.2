"use client";

// 현재 사용자(선택 사주 또는 게스트 프로필)의 일주(日柱) 해석 — 공통 resolver + hook.
// CalendarGrid의 오버레이 기준 사주 규칙과 동일 로직을 한곳으로 모았다:
// - 로그인: 현재 "선택된 사주"만 사용(선택 없으면 null). 균시차는 사주별 속성.
// - 게스트: IndexedDB 로컬 프로필 + 기기 로컬 균시차 토글.
// 일주는 calculateManse 결과의 pillars.day.ganji 에서 파생한다(유일한 기존 경로).

import { useEffect, useState } from "react";
import { calculateManse } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";
import { loadEotPreference, loadProfile } from "@/lib/storage";
import { subjectEotPreference, summaryToProfile } from "@/lib/subject-mapping";
import { getSelectedSubjectId, getSubject } from "@/lib/subjects";
import type { Profile } from "@/lib/types";

/** 오버레이/일주 계산 기준 사주 해석 (CalendarGrid와 공유). */
export async function resolveOverlayProfile(): Promise<{ profile: Profile; eot: boolean } | null> {
  if (isLoggedIn()) {
    const id = getSelectedSubjectId();
    if (!id) return null;
    try {
      const summary = await getSubject(id);
      return { profile: summaryToProfile(summary), eot: subjectEotPreference(summary) };
    } catch {
      return null;
    }
  }
  const profile = await loadProfile().catch(() => null);
  return profile ? { profile, eot: loadEotPreference() } : null;
}

/** 현재 사용자의 일주(한자 2자, 예 "甲子") — 기준 사주가 없으면 null. */
export async function resolveCurrentSubjectIlju(): Promise<string | null> {
  const resolved = await resolveOverlayProfile();
  if (!resolved) return null;
  try {
    const result = await calculateManse(resolved.profile, undefined, {
      apply_equation_of_time: resolved.eot,
    });
    return result.pillars.day.ganji;
  } catch {
    return null;
  }
}

export type CurrentIljuStatus = "loading" | "none" | "ready";

/** 메인 카드 등에서 쓰는 현재 일주 hook — loading 동안 스켈레톤 표시용. */
export function useCurrentIlju(): { status: CurrentIljuStatus; ilju: string | null } {
  const [status, setStatus] = useState<CurrentIljuStatus>("loading");
  const [ilju, setIlju] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    resolveCurrentSubjectIlju().then((value) => {
      if (cancelled) return;
      setIlju(value);
      setStatus(value ? "ready" : "none");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, ilju };
}
