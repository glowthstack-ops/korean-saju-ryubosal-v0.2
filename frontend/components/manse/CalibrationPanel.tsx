"use client";

import { useEffect, useState } from "react";
import { InfoTooltip } from "@/components/layout/InfoTooltip";
import { submitCalibration, type FeedbackAnswer } from "@/lib/api";
import { elementLabel, elementStyle } from "@/lib/elements";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

const ALL_ELEMENTS = ["木", "火", "土", "金", "水"];

const RATINGS: { value: string; label: string }[] = [
  { value: "very_positive", label: "크게 좋아짐" },
  { value: "positive", label: "좋아짐" },
  { value: "neutral", label: "비슷·잔잔" },
  { value: "negative", label: "힘들어짐" },
  { value: "very_negative", label: "크게 힘들어짐" },
  { value: "unknown", label: "기억 안 남" },
];

const axisKo: Record<string, string> = {
  eokbu: "억부", johu: "조후", pattern: "격국", disease: "병약", special: "특수격",
};

// 모델 → 판단 축(백엔드 _AXIS_OF 미러). 검증 확정 축 라벨에 사용.
const axisOfModel: Record<string, string> = {
  support_day_master: "eokbu", resource_as_yongsin: "eokbu", output_as_yongsin: "eokbu",
  eokbu_normal: "eokbu", wealth_breaks_resource: "eokbu", officer_controls_peer: "eokbu",
  resource_curbs_output: "eokbu", johu: "johu", pattern_sangsin: "pattern",
  disease_remedy: "disease", dominant_one_element: "special", follow_structure: "special",
  bridge_tonggwan: "disease",
};

const STATUS_KO: Record<string, string> = {
  calibrated: "확정", probable: "유력", uncertain: "불확실", candidate: "후보(검증 필요)",
};

export function YongsinPanel({
  result,
  calibration,
  onRedo,
}: {
  result: ManseResult;
  calibration: CalibrationResult | null;
  onRedo?: () => void;
}) {
  const y = result.yongsin_analysis;
  const statusKo = STATUS_KO;
  const yongsin = (calibration?.final_yongsin ?? y.final.yongsin) as string | null;
  const heesin = (calibration?.final_heesin ?? y.final.heesin) as string | null;
  const gisin = (calibration?.final_gisin ?? y.final.gisin) as string | null;
  const gusin = (calibration?.final_gusin ?? y.final.gusin) as string | null;
  // 한신 = 용/희/기/구에 배정되지 않은 나머지 한 오행.
  const assigned = [yongsin, heesin, gisin, gusin].filter(Boolean) as string[];
  const hansin = ALL_ELEMENTS.find((e) => !assigned.includes(e)) ?? null;
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 flex items-center text-sm font-semibold">
        용신 후보
        <InfoTooltip text="사주의 균형을 잡아 주는, 가장 필요한 핵심 기운입니다. 먼저 후보로 제시하고 과거 경험과 맞춰 본 뒤 확정합니다. 부족한 오행이 곧 용신은 아닙니다." />
      </h2>
      <p className="text-sm">
        상태: <b>{statusKo[calibration?.status ?? y.status] ?? y.status}</b>
      </p>
      <div className="mt-2 grid grid-cols-5 gap-1.5 text-xs">
        <Box label="용신" v={yongsin} />
        <Box label="희신" v={heesin} />
        <Box label="기신" v={gisin} />
        <Box label="구신" v={gusin} />
        <Box label="한신" v={hansin} />
      </div>
      <p className="mt-2 text-[11px] text-gray-500">
        후보 모델: {y.candidate_models.map((m) => `${m.label}${m.is_auxiliary ? "(보조)" : ""}`).join(" · ")}
      </p>
      {(y.axes ?? []).length > 0 && (
        <p className="mt-1 text-[11px] text-gray-500">
          판단 축(가중치): {y.axes.map((a) => `${axisKo[a.axis] ?? a.axis} ${a.weight}→${a.top_element}`).join(" · ")}
        </p>
      )}
      {calibration?.selected_model && (
        <p className="mt-1 text-[11px] text-emerald-700">
          검증 확정 축: {axisKo[axisOfModel[calibration.selected_model] ?? ""] ?? calibration.selected_model}
          {calibration.final_yongsin ? `[${elementLabel(calibration.final_yongsin)}]` : ""}
          {" · 피드백 일치율 "}{Math.round(calibration.match_rate * 100)}%
        </p>
      )}
      {calibration && (
        <div className="mt-3 flex items-center justify-between rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs">
          <span className="font-semibold text-emerald-800">답변 반영 완료</span>
          {onRedo && (
            <button type="button" onClick={onRedo}
              className="rounded border border-gray-300 bg-white px-2.5 py-1 text-gray-700 hover:bg-gray-50">
              검증 다시 진행
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function Box({ label, v }: { label: string; v: string | null }) {
  return (
    <div className="text-center">
      <div className="mb-1 text-[11px] text-gray-400">{label}</div>
      <div className={`rounded border p-2 text-sm font-bold leading-tight ${v ? elementStyle(v) : "border-dashed text-gray-300"}`}>
        {v ? elementLabel(v) : "-"}
      </div>
    </div>
  );
}

type AnswerMap = Record<string, { rating: string; events: string[] }>;

export function CalibrationPanel({
  result,
  profile,
  referenceDate,
  timeOptions,
  onResult,
  initialAnswers,
  submitted = false,
}: {
  result: ManseResult;
  profile: Profile;
  referenceDate: string;
  // 화면에 표시 중인 차트와 같은 시간옵션(균시차 토글 상태)으로 채점하기 위한 전달값.
  timeOptions?: Record<string, unknown>;
  onResult: (r: CalibrationResult, answers: AnswerMap) => void;
  initialAnswers?: AnswerMap;
  submitted?: boolean;
}) {
  const questions = result.calibration?.questions ?? [];
  const [answers, setAnswers] = useState<AnswerMap>(initialAnswers ?? {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 저장된 답변이 비동기로 도착하면 1회 복원(사용자 입력 전 복원되므로 안전).
  useEffect(() => {
    if (initialAnswers && Object.keys(initialAnswers).length > 0) {
      setAnswers(initialAnswers);
    }
  }, [initialAnswers]);

  // 제출 완료 시 문항을 접는다(완료 표시·재시도는 위 '용신 후보' 패널에서 처리).
  if (submitted) return null;

  // 문항이 없으면(예: 어린 나이로 과거 운 이력이 부족) 빈 화면 대신 사유를 안내한다.
  if (questions.length === 0) {
    return (
      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-1 text-sm font-semibold">용신 검증 질문</h2>
        <p className="text-xs text-gray-500">
          검증할 과거 운(運) 기간이 충분하지 않거나 후보 모델이 부족해 용신 검증 질문을
          생성할 수 없습니다.
        </p>
      </section>
    );
  }

  const answeredCount = questions.filter(
    (q) => answers[q.id]?.rating && answers[q.id]?.rating !== "unknown",
  ).length;

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
      onResult(await submitCalibration(profile, payload, referenceDate, timeOptions), answers);
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
            {q.period_range && (
              <p className="mt-0.5 text-[11px] text-gray-400">{q.period_range}</p>
            )}
            <p className="mt-1 text-[10px] font-medium text-gray-400">그 해 흐름</p>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {RATINGS.map((r) => (
                <button key={r.value} type="button" onClick={() => setRating(q.id, r.value)}
                  className={`rounded border px-2 py-0.5 text-[11px] ${
                    answers[q.id]?.rating === r.value ? "border-gray-800 bg-gray-800 text-white" : ""
                  }`}>
                  {r.label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[10px] font-medium text-gray-400">영향 영역(복수)</p>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {q.options.map((opt) => (
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
      <p className="mt-1 text-center text-[11px] text-gray-400">
        {answeredCount}/{questions.length}개 응답
        {answeredCount === 0 && " · 흐름을 하나도 고르지 않으면 검증되지 않아요"}
      </p>
    </section>
  );
}
