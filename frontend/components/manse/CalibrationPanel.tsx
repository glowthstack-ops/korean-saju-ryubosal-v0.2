"use client";

import { useState } from "react";
import { InfoTooltip } from "@/components/layout/InfoTooltip";
import { submitCalibration, type FeedbackAnswer } from "@/lib/api";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

const RATINGS: { value: string; label: string }[] = [
  { value: "very_positive", label: "매우 좋았다" },
  { value: "positive", label: "좋았다" },
  { value: "neutral", label: "보통" },
  { value: "negative", label: "힘들었다" },
  { value: "very_negative", label: "매우 힘들었다" },
  { value: "unknown", label: "기억 안 남" },
];

export function YongsinPanel({
  result,
  calibration,
}: {
  result: ManseResult;
  calibration: CalibrationResult | null;
}) {
  const y = result.yongsin_analysis;
  const statusKo: Record<string, string> = {
    calibrated: "확정", probable: "유력", uncertain: "불확실",
    candidate: "후보(검증 필요)",
  };
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 flex items-center text-sm font-semibold">
        용신 후보
        <InfoTooltip text="용신은 최초 계산에서 확정하지 않습니다. 후보로 제시되며 과거 사건 검증 후 확정/유력/불확실로 판정됩니다. 부족한 오행이 곧 용신은 아닙니다." />
      </h2>
      <p className="text-sm">
        상태: <b>{statusKo[calibration?.status ?? y.status] ?? y.status}</b>
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <Box label="용신" v={(calibration?.final_yongsin ?? y.final.yongsin) as string | null} />
        <Box label="희신" v={(calibration?.final_heesin ?? y.final.heesin) as string | null} />
        <Box label="기신" v={(calibration?.final_gisin ?? y.final.gisin) as string | null} />
        <Box label="구신" v={(calibration?.final_gusin ?? y.final.gusin) as string | null} />
      </div>
      <p className="mt-2 text-[11px] text-gray-500">
        후보 모델: {y.candidate_models.map((m) => `${m.label}${m.is_auxiliary ? "(보조)" : ""}`).join(" · ")}
      </p>
      {calibration && (
        <p className="mt-1 text-[11px] text-gray-500">
          검증결과 match {calibration.match_rate} · 근거 {calibration.evidence_count}개 · 모델 {calibration.selected_model}
        </p>
      )}
    </section>
  );
}

function Box({ label, v }: { label: string; v: string | null }) {
  return (
    <div className="rounded border p-2 text-center">
      <div className="text-gray-400">{label}</div>
      <div className="text-base font-bold">{v ?? "-"}</div>
    </div>
  );
}

export function CalibrationPanel({
  result,
  profile,
  referenceDate,
  onResult,
}: {
  result: ManseResult;
  profile: Profile;
  referenceDate: string;
  onResult: (r: CalibrationResult) => void;
}) {
  const questions = result.calibration?.questions ?? [];
  const [answers, setAnswers] = useState<Record<string, { rating: string; events: string[] }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (questions.length === 0) return null;

  const setRating = (id: string, rating: string) =>
    setAnswers((a) => ({ ...a, [id]: { rating, events: a[id]?.events ?? [] } }));
  const toggleEvent = (id: string, ev: string) =>
    setAnswers((a) => {
      const cur = a[id]?.events ?? [];
      const events = cur.includes(ev) ? cur.filter((e) => e !== ev) : [...cur, ev];
      return { ...a, [id]: { rating: a[id]?.rating ?? "neutral", events } };
    });

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: FeedbackAnswer[] = questions.map((q) => ({
        question_id: q.id,
        overall_rating: answers[q.id]?.rating ?? "unknown",
        selected_events: answers[q.id]?.events ?? [],
      }));
      onResult(await submitCalibration(profile, payload, referenceDate));
    } catch (e) {
      setError(e instanceof Error ? e.message : "검증 제출 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border-2 border-gray-300 bg-white p-4">
      <h2 className="mb-1 text-sm font-semibold">용신 검증 질문</h2>
      <p className="mb-3 text-xs text-gray-500">
        과거 사건을 답하면 용신 후보를 검증해 확정합니다. 기억나지 않으면 점수에서 제외됩니다.
      </p>
      <ol className="space-y-3">
        {questions.map((q) => (
          <li key={q.id} className="rounded border p-2">
            <p className="text-sm">{q.question_text}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {RATINGS.map((r) => (
                <button key={r.value} type="button" onClick={() => setRating(q.id, r.value)}
                  className={`rounded border px-2 py-0.5 text-[11px] ${
                    answers[q.id]?.rating === r.value ? "border-gray-800 bg-gray-800 text-white" : ""
                  }`}>
                  {r.label}
                </button>
              ))}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {q.options.slice(0, 8).map((opt) => (
                <button key={opt} type="button" onClick={() => toggleEvent(q.id, opt)}
                  className={`rounded-full border px-2 py-0.5 text-[10px] ${
                    answers[q.id]?.events?.includes(opt) ? "border-emerald-600 bg-emerald-50" : "text-gray-500"
                  }`}>
                  {opt}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ol>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <button type="button" onClick={submit} disabled={busy}
        className="mt-3 w-full rounded bg-gray-900 py-2 text-white disabled:bg-gray-400">
        {busy ? "검증 중…" : "검증 제출"}
      </button>
    </section>
  );
}
