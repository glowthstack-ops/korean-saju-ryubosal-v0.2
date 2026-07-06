"use client";

import { useEffect, useState } from "react";
import { InfoTooltip } from "@/components/layout/InfoTooltip";
import { submitCalibration, type FeedbackAnswer } from "@/lib/api";
import {
  CALIB_DOMAINS,
  DOMAIN_OPTIONS,
  OVERALL_OPTIONS,
  STATIC_DEFICIENCY_OPTIONS,
  TRAIT_OPTIONS,
  TRANSIT_OPTIONS,
  YONGSIN_EVENT_OPTIONS,
  normalizeEventRating,
  type AnswerMap,
} from "@/lib/calibration";
import { elementLabel, elementStyle } from "@/lib/elements";
import type { CalibrationResult, ManseResult, Profile } from "@/lib/types";

const ALL_ELEMENTS = ["木", "火", "土", "金", "水"];

// 이벤트 카테고리 표시 라벨(백엔드 EVENT_CATEGORY_LABEL 미러). affection은 혼인상태 정보가
// 없을 때의 기본값으로 "연애/부부"를 쓴다(이벤트 라벨 자체가 구체적이라 충분).
const CATEGORY_KO: Record<string, string> = {
  career: "직업",
  move: "이동",
  affection: "연애/부부",
  money: "금전",
  health: "건강",
  study: "학업",
};

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
  confirmedYongsin = null,
  onRedo,
}: {
  result: ManseResult;
  calibration: CalibrationResult | null;
  confirmedYongsin?: string | null;
  onRedo?: () => void;
}) {
  const y = result.yongsin_analysis;
  const statusKo = STATUS_KO;
  // 표시 용신: 이 기기의 검증(calibration) > DB 등록 확정 용신 > 계산 후보.
  // confirmedYongsin은 다른 기기/Wizard로 등록한 경우 교차 복원(검증 없어도 등록값 노출).
  const registered = !calibration && !!confirmedYongsin;
  const yongsin = (calibration?.final_yongsin ?? confirmedYongsin ?? y.final.yongsin) as
    | string
    | null;
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
        상태:{" "}
        <b>{registered ? "확정(등록됨)" : (statusKo[calibration?.status ?? y.status] ?? y.status)}</b>
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

export function CalibrationPanel({
  result,
  profile,
  referenceDate,
  timeOptions,
  onResult,
  initialAnswers,
  submitted = false,
  registered = false,
}: {
  result: ManseResult;
  profile: Profile;
  referenceDate: string;
  // 화면에 표시 중인 차트와 같은 시간옵션(균시차 토글 상태)으로 채점하기 위한 전달값.
  timeOptions?: Record<string, unknown>;
  onResult: (r: CalibrationResult, answers: AnswerMap) => void;
  initialAnswers?: AnswerMap;
  submitted?: boolean;
  // DB에 이미 확정 용신이 등록된 상태(이 기기 검증 기록은 없음) — 질문 대신 '등록 완료'를 표시한다.
  registered?: boolean;
}) {
  const questions = result.calibration?.questions ?? [];
  const [answers, setAnswers] = useState<AnswerMap>(initialAnswers ?? {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reverify, setReverify] = useState(false);

  // 저장된 답변이 비동기로 도착하면 1회 복원(사용자 입력 전 복원되므로 안전).
  useEffect(() => {
    if (initialAnswers && Object.keys(initialAnswers).length > 0) {
      setAnswers(initialAnswers);
    }
  }, [initialAnswers]);

  // 제출 완료 시 문항을 접는다(완료 표시·재시도는 위 '용신 후보' 패널에서 처리).
  if (submitted) return null;

  // 이미 DB에 등록된 용신이 있으면 질문 대신 '등록 완료'를 보여준다 — 원하면 다시 검증 가능.
  if (registered && !reverify) {
    return (
      <section className="flex items-center justify-between rounded-lg border border-emerald-300 bg-emerald-50 p-4">
        <span className="text-sm font-semibold text-emerald-800">용신 등록 완료</span>
        <button
          type="button"
          onClick={() => setReverify(true)}
          className="rounded border border-gray-300 bg-white px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-50"
        >
          다시 검증
        </button>
      </section>
    );
  }

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

  // 응답 수 — 전체 체감·영역·사건 중 하나라도 유의미하게 고르면 응답으로 본다.
  // probe 유형(CAL-P0): trait는 선택지 응답, transition은 영역 칩 선택을 응답으로 본다.
  const isAnswered = (q: (typeof questions)[number]): boolean => {
    const a = answers[q.id];
    if (!a) return false;
    if (q.question_type === "trait_probe") return !!a.trait_response;
    if (q.question_type === "static_deficiency_probe") return !!a.static_response;
    if (q.question_type === "transit_activation_probe") return !!a.transit_response;
    if (q.question_type === "transition_probe") return (a.events ?? []).length > 0;
    if (a.rating && a.rating !== "unknown") return true;
    if (Object.values(a.domain_ratings ?? {}).some((v) => v && v !== "unknown")) return true;
    return Object.values(a.event_ratings ?? {}).some(
      (v) => normalizeEventRating(v) && normalizeEventRating(v) !== "unknown",
    );
  };
  const answeredCount = questions.filter(isAnswered).length;

  const patch = (id: string, next: Partial<AnswerMap[string]>) =>
    setAnswers((a) => {
      const base = a[id] ?? { rating: "unknown", events: [] };
      return { ...a, [id]: { ...base, ...next } };
    });
  const setRating = (id: string, rating: string) => patch(id, { rating });
  const toggleEvent = (id: string, ev: string) => {
    const cur = answers[id]?.events ?? [];
    patch(id, { events: cur.includes(ev) ? cur.filter((e) => e !== ev) : [...cur, ev] });
  };
  const setDomainRating = (id: string, domain: string, rating: string) =>
    patch(id, { domain_ratings: { ...(answers[id]?.domain_ratings ?? {}), [domain]: rating } });
  const setEventRating = (id: string, eventKey: string, rating: string) =>
    patch(id, { event_ratings: { ...(answers[id]?.event_ratings ?? {}), [eventKey]: rating } });
  const setTraitResponse = (id: string, v: string) => patch(id, { trait_response: v });
  const setTraitStatement = (id: string, v: string) => patch(id, { trait_statement: v });
  const setStaticResponse = (id: string, v: string) => patch(id, { static_response: v });
  const setTransitResponse = (id: string, v: string) => patch(id, { transit_response: v });

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: FeedbackAnswer[] = questions.map((q) => ({
        question_id: q.id,
        overall_rating: answers[q.id]?.rating ?? "unknown",
        selected_events: answers[q.id]?.events ?? [],
        event_ratings: answers[q.id]?.event_ratings ?? {},
        domain_ratings: answers[q.id]?.domain_ratings ?? {},
        event_intensity: answers[q.id]?.event_intensity ?? {},
        // trait_probe(CAL-P0)·pair(CAL-P1) — 채점 비반영, 표현 보정용으로만 서버에 전달.
        trait_response: answers[q.id]?.trait_response ?? null,
        trait_statement: answers[q.id]?.trait_statement?.trim() || null,
        static_response: answers[q.id]?.static_response ?? null,
        transit_response: answers[q.id]?.transit_response ?? null,
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
      <ol className="space-y-4">
        {questions.map((q) => {
          const a = answers[q.id];

          // trait_probe(CAL-P0) — 성향 확인: 선택형 고정. 정답 확인이 아니라 표현 보정용이며
          // 용신·점수를 바꾸지 않는다(백엔드 채점 비반영 고정).
          if (q.question_type === "trait_probe") {
            return (
              <li key={q.id} className="rounded border p-2.5">
                <p className="text-sm font-medium">{q.question_text}</p>
                <p className="mt-0.5 text-[11px] text-gray-400">
                  답변 스타일을 더 잘 맞추기 위한 확인 질문이에요. 용신이나 운세 점수는
                  바뀌지 않아요.
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {TRAIT_OPTIONS.map((o) => (
                    <button key={o.value} type="button"
                      onClick={() => setTraitResponse(q.id, o.value)}
                      className={`rounded border px-2 py-1 text-[11px] ${
                        a?.trait_response === o.value
                          ? "border-gray-800 bg-gray-800 text-white"
                          : "text-gray-600"
                      }`}>
                      {o.label}
                    </button>
                  ))}
                </div>
                <input type="text" maxLength={80}
                  value={a?.trait_statement ?? ""}
                  onChange={(e) => setTraitStatement(q.id, e.target.value)}
                  placeholder="실제로는 어떤지 한 줄로 남겨 주셔도 좋아요 (선택)"
                  className="mt-2 w-full rounded border px-2 py-1 text-[11px] placeholder:text-gray-300"
                />
              </li>
            );
          }

          // static_deficiency_probe(CAL-P1 A) — 평소 체감: 선택형 고정, 채점 비반영.
          if (q.question_type === "static_deficiency_probe") {
            return (
              <li key={q.id} className="rounded border p-2.5">
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                  평소 체감
                </span>
                <p className="mt-1 text-sm font-medium">{q.question_text}</p>
                <p className="mt-0.5 text-[11px] text-gray-400">
                  평소 체감에 가까운 답을 골라주세요. 이 답변은 해석 표현을 더 정확히
                  맞추기 위한 참고용이에요.
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {STATIC_DEFICIENCY_OPTIONS.map((o) => (
                    <button key={o.value} type="button"
                      onClick={() => setStaticResponse(q.id, o.value)}
                      className={`rounded border px-2 py-1 text-[11px] ${
                        a?.static_response === o.value
                          ? "border-gray-800 bg-gray-800 text-white"
                          : "text-gray-600"
                      }`}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          }

          // transit_activation_probe(CAL-P1 B) — 해당 시기 체감: 연도 앵커형, 채점 비반영.
          if (q.question_type === "transit_activation_probe") {
            return (
              <li key={q.id} className="rounded border p-2.5">
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                  해당 시기 체감
                </span>
                <p className="mt-1 text-sm font-medium">{q.question_text}</p>
                {q.period_range && (
                  <p className="mt-0.5 text-[11px] text-gray-400">{q.period_range}</p>
                )}
                <p className="mt-0.5 text-[11px] text-gray-400">
                  해당 해에 실제로 체감된 변화가 있었는지 확인하는 질문이에요. 답변이
                  용신이나 운세 점수를 바꾸지는 않아요.
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {TRANSIT_OPTIONS.map((o) => (
                    <button key={o.value} type="button"
                      onClick={() => setTransitResponse(q.id, o.value)}
                      className={`rounded border px-2 py-1 text-[11px] ${
                        a?.transit_response === o.value
                          ? "border-gray-800 bg-gray-800 text-white"
                          : "text-gray-600"
                      }`}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          }

          // transition_probe(CAL-P0) — 교운기 회상: 사건 단정 없이 변화 체감만 확인.
          // 응답은 영향 영역 칩(복수)으로 받는다(채점 비반영 — 질문 품질·회상 보조용).
          if (q.question_type === "transition_probe") {
            return (
              <li key={q.id} className="rounded border p-2.5">
                <p className="text-sm font-medium">{q.question_text}</p>
                {q.period_range && (
                  <p className="mt-0.5 text-[11px] text-gray-400">{q.period_range}</p>
                )}
                <p className="mt-0.5 text-[11px] text-gray-400">
                  이 시기는 대운(10년 흐름)이 바뀌는 전환 전후예요. 실제 사건이 아니더라도
                  생활 리듬이나 주변 환경 변화가 체감됐는지 확인해요.
                </p>
                <p className="mt-2 text-[10px] font-medium text-gray-400">
                  변화가 있었던 영역(복수)
                </p>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {q.options.map((opt) => (
                    <button key={opt} type="button" onClick={() => toggleEvent(q.id, opt)}
                      className={`rounded-full border px-2 py-0.5 text-[10px] ${
                        a?.events?.includes(opt)
                          ? "border-emerald-600 bg-emerald-50"
                          : "text-gray-500"
                      }`}>
                      {opt}
                    </button>
                  ))}
                </div>
              </li>
            );
          }

          return (
            <li key={q.id} className="rounded border p-2.5">
              <p className="text-sm font-medium">{q.question_text}</p>
              {q.period_range && (
                <p className="mt-0.5 text-[11px] text-gray-400">{q.period_range}</p>
              )}

              {/* ① 그 해 전체 체감(7상태) */}
              <p className="mt-2 text-[10px] font-medium text-gray-400">그 해 전체 체감</p>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {OVERALL_OPTIONS.map((r) => (
                  <button key={r.value} type="button" onClick={() => setRating(q.id, r.value)}
                    className={`rounded border px-2 py-0.5 text-[11px] ${
                      a?.rating === r.value ? "border-gray-800 bg-gray-800 text-white" : "text-gray-600"
                    }`}>
                    {r.label}
                  </button>
                ))}
              </div>

              {/* ② 영역별 체감(5상태) */}
              <p className="mt-2 text-[10px] font-medium text-gray-400">영역별 체감</p>
              <div className="mt-0.5 space-y-2">
                {CALIB_DOMAINS.map((dom) => {
                  const cur = a?.domain_ratings?.[dom.key];
                  return (
                    <div key={dom.key}>
                      <span className="text-[12px] text-gray-600">{dom.label}</span>
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {DOMAIN_OPTIONS.map((o) => (
                          <button key={o.value} type="button"
                            onClick={() => setDomainRating(q.id, dom.key, o.value)}
                            className={`rounded border px-2 py-1 text-[11px] ${
                              cur === o.value ? "border-indigo-600 bg-indigo-600 text-white" : "text-gray-500"
                            }`}>
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* ③ 사건별 결과 — 라벨은 한 줄, 버튼은 아래에서 줄바꿈(모바일 대응) */}
              {q.events && q.events.length ? (
                <>
                  <p className="mt-2 text-[10px] font-medium text-gray-400">그 해 실제 사건 · 결과</p>
                  <ul className="mt-0.5 space-y-2">
                    {q.events.map((ev) => {
                      const cur = normalizeEventRating(a?.event_ratings?.[ev.event_key]);
                      return (
                        <li key={ev.event_key}>
                          <div className="text-[13px]">
                            {ev.label}
                            <span className="ml-1 rounded bg-gray-100 px-1 py-0.5 text-[10px] text-gray-400">
                              {CATEGORY_KO[ev.category] ?? ev.category}
                            </span>
                          </div>
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            {YONGSIN_EVENT_OPTIONS.map((o) => (
                              <button key={o.value} type="button"
                                onClick={() => setEventRating(q.id, ev.event_key, o.value)}
                                className={`rounded border px-2 py-1 text-[11px] ${
                                  cur === o.value ? "border-gray-800 bg-gray-800 text-white" : "text-gray-500"
                                }`}>
                                {o.label}
                              </button>
                            ))}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </>
              ) : (
                <>
                  <p className="mt-2 text-[10px] font-medium text-gray-400">영향 영역(복수)</p>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {q.options.map((opt) => (
                      <button key={opt} type="button" onClick={() => toggleEvent(q.id, opt)}
                        className={`rounded-full border px-2 py-0.5 text-[10px] ${
                          a?.events?.includes(opt) ? "border-emerald-600 bg-emerald-50" : "text-gray-500"
                        }`}>
                        {opt}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </li>
          );
        })}
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
