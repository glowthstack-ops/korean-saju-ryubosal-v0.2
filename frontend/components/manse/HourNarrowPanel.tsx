"use client";

// 시주 후보 좁히기 — 대략 시간대 + 성향 문항 (2026-10-06 데굴님 승인).
//
// 후보 시진별 성향 문장(백엔드 사전 문구 그대로)을 보여 주고 "나와 맞다"를 고르면 일치 수로 순위를
// 낸다. 결과는 **추정**이다 — 적용해도 시간 미상 모드는 유지되고(hour=null) 풀이에는 '성향 추정
// 시진·확정 아님'으로만 표기된다. 출생 기록으로 시간을 확인하면 추정을 대체한다.

import { useEffect, useMemo, useState } from "react";
import { getHourTraits, postHourNarrow } from "@/lib/api";
import {
  APPROX_BANDS,
  APPROX_BAND_HOURS,
  type ApproxBand,
  type HourNarrowResponse,
  type HourTraitsResponse,
  type Profile,
} from "@/lib/types";

export function HourNarrowPanel({
  profile,
  referenceDate,
  onApply,
}: {
  profile: Profile;
  referenceDate: string;
  /** (timeApprox, hourHint) 적용 — 저장·재계산은 호출 측(결과 페이지) 책임. */
  onApply: (timeApprox: ApproxBand | null, hourHint: string | null) => void;
}) {
  const [band, setBand] = useState<ApproxBand | null>(profile.timeApprox ?? null);
  const [traits, setTraits] = useState<HourTraitsResponse | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<HourNarrowResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const bandProfile = useMemo<Profile>(
    () => ({ ...profile, timeApprox: band, hourHint: null }),
    [profile, band],
  );

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setBusy(true);
    setErr(null);
    setResult(null);
    setPicked(new Set());
    getHourTraits(bandProfile, referenceDate)
      .then((t) => { if (alive) setTraits(t); })
      .catch((e) => { if (alive) setErr(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [open, bandProfile, referenceDate]);

  const toggle = (id: string) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    setResult(null);
  };

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setResult(await postHourNarrow(bandProfile, referenceDate, [...picked]));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-amber-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">시주 후보 좁히기 <span className="font-normal text-gray-500">(대략 시간대 · 성향)</span></h2>
        <button
          onClick={() => setOpen((v) => !v)}
          className="rounded border px-2 py-1 text-xs hover:bg-gray-50"
        >
          {open ? "접기" : profile.hourHint ? `추정 ${profile.hourHint}시 — 다시 좁히기` : "시작"}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-gray-500">
        출생 시간을 모를 때 대략 시간대와 성향 문항으로 후보 시진을 좁혀요. 결과는 <b>추정</b>이며 확정이
        아니에요 — 적용해도 시간 미상 기준은 유지되고 풀이에는 &quot;성향 추정 시진&quot;으로만 표시돼요.
      </p>
      {open && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-1 text-xs">
            <span className="mr-1 text-gray-600">시간대</span>
            <button onClick={() => setBand(null)}
              className={`rounded border px-2 py-0.5 ${band === null ? "border-gray-800 bg-gray-800 text-white" : "bg-white"}`}>
              모름(12후보)
            </button>
            {APPROX_BANDS.map((b) => (
              <button key={b} onClick={() => setBand(b)} title={APPROX_BAND_HOURS[b]}
                className={`rounded border px-2 py-0.5 ${band === b ? "border-gray-800 bg-gray-800 text-white" : "bg-white"}`}>
                {b} <span className="opacity-70">{APPROX_BAND_HOURS[b]}</span>
              </button>
            ))}
          </div>
          {busy && !traits && <p className="text-xs text-gray-500">후보 계산 중…</p>}
          {err && <p className="text-xs text-rose-600">{err}</p>}
          {traits && traits.candidates.length > 0 && (
            <>
              <p className="text-[11px] text-gray-500">
                아래 문장 중 <b>나와 맞는 것</b>을 모두 고르세요. 어느 시진의 문장인지는 가려져 있어요(선입견
                방지). {traits.note}
              </p>
              <ul className="space-y-1">
                {shuffleStable(traits.candidates.flatMap((c) => c.statements)).map((s) => (
                  <li key={s.id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded border px-2 py-1.5 text-xs hover:bg-gray-50">
                      <input type="checkbox" className="mt-0.5" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
                      <span>{s.text}</span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2">
                <button onClick={run} disabled={busy || picked.size === 0}
                  className="rounded bg-gray-800 px-3 py-1.5 text-xs text-white disabled:opacity-40">
                  {busy ? "계산 중…" : `좁히기 (${picked.size}개 선택)`}
                </button>
                <button onClick={() => onApply(band, null)} className="rounded border px-3 py-1.5 text-xs hover:bg-gray-50">
                  시간대만 적용{band ? `(${band})` : "(모름)"}
                </button>
              </div>
            </>
          )}
          {result && (
            <div className="rounded border bg-gray-50 p-3 text-xs">
              <p className="font-medium">후보 순위</p>
              <ul className="mt-1 space-y-0.5">
                {result.ranking.map((r) => (
                  <li key={r.hour_branch} className="flex justify-between">
                    <span>{r.hour_branch}시 ({r.time_range}) · {r.ganji}</span>
                    <span className="text-gray-600">{r.matched}/{r.total} 일치</span>
                  </li>
                ))}
              </ul>
              {result.recommended ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span>
                    추천 추정 시진 <b>{result.recommended}시</b>
                    <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">
                      신뢰 {result.confidence === "medium" ? "보통" : "낮음"} · 추정
                    </span>
                  </span>
                  <button onClick={() => onApply(band, result.recommended)}
                    className="rounded bg-amber-600 px-3 py-1 text-white hover:bg-amber-700">
                    이 시진으로 추정 적용
                  </button>
                </div>
              ) : (
                <p className="mt-2 text-gray-600">단독 1위가 없어 추천하지 않아요. 문장을 더 고르거나 시간대를 좁혀 보세요.</p>
              )}
              <p className="mt-2 text-[11px] text-gray-500">{result.note}</p>
            </div>
          )}
          {profile.hourHint && (
            <button onClick={() => onApply(band, null)} className="text-[11px] text-gray-500 underline">
              현재 추정 시진({profile.hourHint}) 해제
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/** 문장 순서를 시진별로 묶이지 않게 섞되, 같은 입력엔 같은 순서(결정론) — 선입견 방지용. */
function shuffleStable<T extends { id: string }>(items: T[]): T[] {
  const hash = (s: string) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);
  return [...items].sort((a, b) => hash(a.id) - hash(b.id));
}
