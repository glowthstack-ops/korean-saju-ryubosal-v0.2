"use client";

// [현실 신호 캘리브레이션] 주요 ~10개 연도에 실제 있었던 일을 선택(+발생 월은 기억나는 경우만).
// 개인 사건 시그니처로 풀이 정확도를 높인다(Life Event Inference §5). 전부 선택 사항(건너뛰기 가능).

import { useEffect, useState } from "react";

import { getRealityCalibration, submitRealityCalibration } from "@/lib/subjects";
import type {
  RealityCalibrationQuestionSet,
  RealityCalibrationYearAnswer,
} from "@/lib/types";

interface Props {
  subjectId: string;
  onDone: () => void;
}

type YearState = {
  occurred: Record<string, number | null>; // event_key → 발생 월(null = 모름)
  none: boolean;
};

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

export function StepRealityCalibration({ subjectId, onDone }: Props) {
  const [q, setQ] = useState<RealityCalibrationQuestionSet | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [state, setState] = useState<Record<number, YearState>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getRealityCalibration(subjectId)
      .then((res) => {
        setQ(res);
        const init: Record<number, YearState> = {};
        for (const y of res.years) init[y.year] = { occurred: {}, none: false };
        setState(init);
      })
      .catch((e: unknown) => setErr((e as Error)?.message ?? "불러오기에 실패했습니다."));
  }, [subjectId]);

  function toggleEvent(year: number, key: string) {
    setState((prev) => {
      const ys = prev[year] ?? { occurred: {}, none: false };
      const occ = { ...ys.occurred };
      if (key in occ) delete occ[key];
      else occ[key] = null;
      return { ...prev, [year]: { occurred: occ, none: false } };
    });
  }

  function setMonth(year: number, key: string, month: number | null) {
    setState((prev) => {
      const ys = prev[year] ?? { occurred: {}, none: false };
      return { ...prev, [year]: { ...ys, occurred: { ...ys.occurred, [key]: month } } };
    });
  }

  function toggleNone(year: number) {
    setState((prev) => {
      const ys = prev[year] ?? { occurred: {}, none: false };
      return { ...prev, [year]: { occurred: {}, none: !ys.none } };
    });
  }

  async function submit() {
    if (!q) return;
    setBusy(true);
    setErr(null);
    try {
      const answers: RealityCalibrationYearAnswer[] = q.years.map((y) => {
        const ys = state[y.year] ?? { occurred: {}, none: false };
        return {
          year: y.year,
          none_of_them: ys.none,
          occurred: Object.entries(ys.occurred).map(([event_key, month]) => ({
            event_key,
            month,
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
      <p className="text-zinc-600">{q.note}</p>
      {q.years.map((y) => {
        const ys = state[y.year] ?? { occurred: {}, none: false };
        return (
          <div key={y.year} className="rounded border p-3">
            <div className="mb-2 font-medium">
              {y.year}년 <span className="text-zinc-400">{y.ganji}</span>
              {y.daewoon_transition && (
                <span className="ml-1 text-amber-600">· 대운 교체기</span>
              )}
            </div>
            <div className="space-y-2">
              {y.events.map((ev) => {
                const checked = ev.event_key in ys.occurred;
                return (
                  <div key={ev.event_key} className="flex items-center gap-2">
                    <label className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={ys.none}
                        onChange={() => toggleEvent(y.year, ev.event_key)}
                      />
                      {ev.label}
                    </label>
                    {checked && (
                      <select
                        aria-label="발생 월"
                        className="rounded border px-1.5 py-0.5 text-xs"
                        value={ys.occurred[ev.event_key] ?? ""}
                        onChange={(e) =>
                          setMonth(
                            y.year,
                            ev.event_key,
                            e.target.value ? Number(e.target.value) : null,
                          )
                        }
                      >
                        <option value="">월 모름</option>
                        {MONTHS.map((m) => (
                          <option key={m} value={m}>
                            {m}월
                          </option>
                        ))}
                      </select>
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
      <button
        type="button"
        onClick={submit}
        disabled={busy}
        className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50"
      >
        {busy ? "저장 중…" : "저장하고 계속"}
      </button>
    </div>
  );
}
