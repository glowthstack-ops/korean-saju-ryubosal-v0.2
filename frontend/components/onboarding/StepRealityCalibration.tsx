"use client";

// [현실 신호 캘리브레이션] 주요 ~10개 연도에 실제 있었던 일 + 그해 체감(전체·영역·사건별)을 수집.
// 발생 여부는 subject_life_events(personal_match), 체감·영역·경험은 reality blob에 저장(docs/14 결정①).
// 전부 선택 사항(건너뛰기 가능). 공용 enum은 lib/calibration에서 재사용한다.

import { useEffect, useState } from "react";

import {
  CALIB_DOMAINS,
  DOMAIN_OPTIONS,
  EVENT_OPTIONS,
  OVERALL_OPTIONS,
  normalizeEventRating,
} from "@/lib/calibration";
import { getRealityCalibration, submitRealityCalibration } from "@/lib/subjects";
import type { RealityCalibrationQuestionSet, RealityCalibrationYearAnswer } from "@/lib/types";

interface Props {
  subjectId: string;
  onDone: () => void;
}

type Occ = { month: number | null; experience?: string; intensity?: number };
type YearState = {
  occurred: Record<string, Occ>; // event_key → 발생 월/경험/강도
  none: boolean;
  overall?: string; // 그해 전체 체감(ExperienceRating 7상태)
  domains: Record<string, string>; // 영역별 체감(domain → ExperienceRating)
};

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);
const _EMPTY: YearState = { occurred: {}, none: false, domains: {} };

export function StepRealityCalibration({ subjectId, onDone }: Props) {
  const [q, setQ] = useState<RealityCalibrationQuestionSet | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [state, setState] = useState<Record<number, YearState>>({});
  const [busy, setBusy] = useState(false);
  const [hasPrior, setHasPrior] = useState(false); // 이전 제출 존재(수정 모드)

  useEffect(() => {
    getRealityCalibration(subjectId)
      .then((res) => {
        setQ(res);
        // 이전 제출(prior)로 상태 프리필 — 발생/월 + 경험/강도 + 전체·영역 체감 모두 복원.
        const priorByYear = new Map((res.prior ?? []).map((a) => [a.year, a]));
        setHasPrior((res.prior ?? []).length > 0);
        const init: Record<number, YearState> = {};
        for (const y of res.years) {
          const a = priorByYear.get(y.year);
          init[y.year] = a
            ? {
                occurred: Object.fromEntries(
                  a.occurred.map((o) => [
                    o.event_key,
                    {
                      month: o.month ?? null,
                      experience: normalizeEventRating(o.experience) ?? undefined,
                      intensity: o.intensity ?? undefined,
                    },
                  ]),
                ),
                none: a.none_of_them,
                overall: a.overall_rating,
                domains: { ...(a.domain_ratings ?? {}) },
              }
            : { occurred: {}, none: false, domains: {} };
        }
        setState(init);
      })
      .catch((e: unknown) => setErr((e as Error)?.message ?? "불러오기에 실패했습니다."));
  }, [subjectId]);

  const patchYear = (year: number, next: Partial<YearState>) =>
    setState((prev) => ({ ...prev, [year]: { ...(prev[year] ?? _EMPTY), ...next } }));

  function toggleEvent(year: number, key: string) {
    const ys = state[year] ?? _EMPTY;
    const occ = { ...ys.occurred };
    if (key in occ) delete occ[key];
    else occ[key] = { month: null };
    patchYear(year, { occurred: occ, none: false });
  }
  const patchOcc = (year: number, key: string, next: Partial<Occ>) => {
    const ys = state[year] ?? _EMPTY;
    const cur = ys.occurred[key] ?? { month: null };
    patchYear(year, { occurred: { ...ys.occurred, [key]: { ...cur, ...next } } });
  };
  function toggleNone(year: number) {
    const ys = state[year] ?? _EMPTY;
    patchYear(year, { occurred: {}, none: !ys.none });
  }
  const setDomain = (year: number, domain: string, rating: string) => {
    const ys = state[year] ?? _EMPTY;
    patchYear(year, { domains: { ...ys.domains, [domain]: rating } });
  };

  async function submit() {
    if (!q) return;
    setBusy(true);
    setErr(null);
    try {
      const answers: RealityCalibrationYearAnswer[] = q.years.map((y) => {
        const ys = state[y.year] ?? _EMPTY;
        return {
          year: y.year,
          none_of_them: ys.none,
          overall_rating: ys.overall ?? "unknown",
          domain_ratings: ys.domains,
          occurred: Object.entries(ys.occurred).map(([event_key, o]) => ({
            event_key,
            month: o.month,
            experience: o.experience ?? null,
            intensity: o.intensity ?? null,
          })),
        };
      });
      await submitRealityCalibration(subjectId, answers);
      onDone();
    } catch (e: unknown) {
      setErr((e as Error)?.message ?? "저장에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (err) return <p className="text-sm text-red-600">{err}</p>;
  if (!q) return <p className="text-sm text-zinc-500">불러오는 중…</p>;
  if (q.years.length === 0) {
    return (
      <p className="text-sm text-zinc-500">표시할 연도가 없습니다. 이 단계는 건너뛰셔도 됩니다.</p>
    );
  }

  return (
    <div className="space-y-4 text-sm">
      {hasPrior && (
        <p className="rounded bg-amber-50 px-2.5 py-1.5 text-xs text-amber-700 ring-1 ring-amber-200">
          이전에 입력한 내용을 불러왔습니다. 수정 후 저장하면 기존 기록을 대체합니다.
        </p>
      )}
      <p className="text-zinc-600">{q.note}</p>
      {q.years.map((y) => {
        const ys = state[y.year] ?? _EMPTY;
        return (
          <div key={y.year} className="space-y-2 rounded border p-3">
            <div className="font-medium">
              {y.year}년 <span className="text-zinc-400">{y.ganji}</span>
              {y.daewoon_transition && <span className="ml-1 text-amber-600">· 대운 교체기</span>}
            </div>

            {/* ① 그해 전체 체감 */}
            <p className="text-[10px] font-medium text-zinc-400">그해 전체 체감</p>
            <div className="flex flex-wrap gap-1">
              {OVERALL_OPTIONS.map((o) => (
                <button key={o.value} type="button" onClick={() => patchYear(y.year, { overall: o.value })}
                  className={`rounded border px-2 py-0.5 text-[11px] ${
                    ys.overall === o.value ? "border-zinc-800 bg-zinc-800 text-white" : "text-zinc-600"
                  }`}>
                  {o.label}
                </button>
              ))}
            </div>

            {/* ② 영역별 체감 — 라벨 아래에 버튼을 줄바꿈 배치(모바일 대응) */}
            <p className="text-[10px] font-medium text-zinc-400">영역별 체감</p>
            <div className="space-y-2">
              {CALIB_DOMAINS.map((dom) => (
                <div key={dom.key}>
                  <span className="text-[12px] text-zinc-600">{dom.label}</span>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {DOMAIN_OPTIONS.map((o) => (
                      <button key={o.value} type="button" onClick={() => setDomain(y.year, dom.key, o.value)}
                        className={`rounded border px-2 py-1 text-[11px] ${
                          ys.domains[dom.key] === o.value ? "border-indigo-600 bg-indigo-600 text-white" : "text-zinc-500"
                        }`}>
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* ③ 실제 사건 + 결과/강도 */}
            <p className="text-[10px] font-medium text-zinc-400">실제 있었던 일</p>
            <div className="space-y-2">
              {y.events.map((ev) => {
                const occ = ys.occurred[ev.event_key];
                const checked = !!occ;
                return (
                  <div key={ev.event_key} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1.5">
                        <input type="checkbox" checked={checked} disabled={ys.none}
                          onChange={() => toggleEvent(y.year, ev.event_key)} />
                        {ev.label}
                      </label>
                      {checked && (
                        <select aria-label="발생 월" className="rounded border px-1.5 py-0.5 text-xs"
                          value={occ.month ?? ""}
                          onChange={(e) =>
                            patchOcc(y.year, ev.event_key, { month: e.target.value ? Number(e.target.value) : null })
                          }>
                          <option value="">월 모름</option>
                          {MONTHS.map((m) => (
                            <option key={m} value={m}>{m}월</option>
                          ))}
                        </select>
                      )}
                    </div>
                    {checked && (
                      <div className="pl-6">
                        <span className="text-[10px] text-zinc-400">결과</span>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {EVENT_OPTIONS.map((o) => (
                            <button key={o.value} type="button"
                              onClick={() => patchOcc(y.year, ev.event_key, { experience: o.value })}
                              className={`rounded border px-2 py-1 text-[11px] ${
                                occ.experience === o.value ? "border-zinc-800 bg-zinc-800 text-white" : "text-zinc-500"
                              }`}>
                              {o.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
              <label className="flex items-center gap-1.5 text-zinc-500">
                <input type="checkbox" checked={ys.none} onChange={() => toggleNone(y.year)} />
                해당 없음
              </label>
            </div>
          </div>
        );
      })}
      <button type="button" onClick={submit} disabled={busy}
        className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50">
        {busy ? "저장 중…" : hasPrior ? "수정 저장" : "저장하고 계속"}
      </button>
    </div>
  );
}
