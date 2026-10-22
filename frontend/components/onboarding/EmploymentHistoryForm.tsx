"use client";

// [직장 이력] 자격득실 내역 수준의 입사·퇴사 월일을 줄 단위로 받는다(EMPLOYMENT_HISTORY_CALIBRATION.md §4).
// 전부 선택 사항. 날짜는 일 단위, 모르면 'YYYY-MM'까지만. 같은 직장 묶기(파견→정직원 전환)는 묶기 칸에
// 같은 글자를 적는다. 표시용 이름은 목록 구분용이며 풀이 문장에는 쓰이지 않는다.

import { useEffect, useState } from "react";

import { getEmploymentHistory, submitEmploymentHistory } from "@/lib/subjects";
import type {
  EmploymentChannel,
  EmploymentExitReason,
  EmploymentHistoryEntry,
  EmploymentHistorySubmitResult,
  EmploymentNature,
} from "@/lib/types";

interface Props {
  subjectId: string;
  onDone: (result?: EmploymentHistorySubmitResult) => void;
}

const KIND_OPTIONS: { value: EmploymentHistoryEntry["kind"]; label: string }[] = [
  { value: "entry", label: "입사" },
  { value: "exit", label: "퇴사" },
  { value: "conversion", label: "전환(같은 직장 내 신분 변경)" },
];
const NATURE_OPTIONS: { value: EmploymentNature; label: string }[] = [
  { value: "regular", label: "정규" },
  { value: "dispatch", label: "파견" },
  { value: "intern", label: "인턴" },
  { value: "military", label: "군복무" },
  { value: "conversion", label: "전환" },
];
const CHANNEL_OPTIONS: { value: EmploymentChannel; label: string }[] = [
  { value: "direct", label: "직접 지원" },
  { value: "offer", label: "회사 제안" },
  { value: "referral", label: "지인 소개" },
  { value: "conversion", label: "전환" },
];
const EXIT_OPTIONS: { value: EmploymentExitReason; label: string }[] = [
  { value: "voluntary", label: "자발" },
  { value: "involuntary", label: "타의(권고·해고)" },
  { value: "contract_end", label: "계약 종료" },
];
const DATE_RE = /^\d{4}-\d{2}(-\d{2})?$/;

function emptyEntry(): EmploymentHistoryEntry {
  return { date: "", kind: "entry", nature: "regular", channel: null, exit_reason: null, group: null, org: null };
}

export function EmploymentHistoryForm({ subjectId, onDone }: Props) {
  const [rows, setRows] = useState<EmploymentHistoryEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [hasPrior, setHasPrior] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getEmploymentHistory(subjectId)
      .then((v) => {
        setRows(v.entries.length ? v.entries : [emptyEntry()]);
        setHasPrior(v.entries.length > 0);
        setLoaded(true);
      })
      .catch((e: unknown) => setErr((e as Error)?.message ?? "불러오기에 실패했습니다."));
  }, [subjectId]);

  const patch = (i: number, next: Partial<EmploymentHistoryEntry>) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...next } : r)));
  const remove = (i: number) => setRows((prev) => prev.filter((_, j) => j !== i));
  const add = () => setRows((prev) => [...prev, emptyEntry()]);

  async function submit() {
    setErr(null);
    const filled = rows.filter((r) => r.date.trim());
    const bad = filled.find((r) => !DATE_RE.test(r.date.trim()));
    if (bad) {
      setErr(`날짜 형식을 확인해 주세요: '${bad.date}' (YYYY-MM-DD 또는 YYYY-MM)`);
      return;
    }
    setBusy(true);
    try {
      const entries = filled.map((r) => ({
        ...r,
        date: r.date.trim(),
        org: r.org?.trim() || null,
        group: r.group?.trim() || null,
        channel: r.kind === "exit" ? null : r.channel ?? null,
        exit_reason: r.kind === "exit" ? r.exit_reason ?? null : null,
      }));
      const result = await submitEmploymentHistory(subjectId, entries);
      onDone(result);
    } catch (e: unknown) {
      setErr((e as Error)?.message ?? "저장에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (!loaded && !err) return <p className="text-sm text-zinc-500">불러오는 중…</p>;

  return (
    <div className="space-y-3 text-sm">
      {hasPrior && (
        <p className="rounded bg-amber-50 px-2.5 py-1.5 text-xs text-amber-700 ring-1 ring-amber-200">
          저장된 직장 이력을 불러왔습니다. 수정 후 저장하면 기존 이력을 대체합니다.
        </p>
      )}
      <p className="text-zinc-600">
        건강보험·국민연금 자격득실 내역의 입사일·퇴사일을 그대로 적어 주세요. 일자를 모르면 연월(YYYY-MM)까지만
        적어도 됩니다. 파견에서 정직원이 된 경우처럼 사실상 같은 직장이면 &lsquo;묶기&rsquo; 칸에 같은 글자를
        적어 주세요. 이름 칸은 목록 구분용이며 풀이 문장에는 쓰이지 않습니다.
      </p>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-2 gap-1.5 rounded border p-2 md:grid-cols-7">
            <input aria-label="날짜" placeholder="YYYY-MM-DD" value={r.date}
              onChange={(e) => patch(i, { date: e.target.value })}
              className="rounded border px-1.5 py-1 text-xs" />
            <select aria-label="종류" value={r.kind} className="rounded border px-1.5 py-1 text-xs"
              onChange={(e) => patch(i, { kind: e.target.value as EmploymentHistoryEntry["kind"] })}>
              {KIND_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select aria-label="성격" value={r.nature} className="rounded border px-1.5 py-1 text-xs"
              onChange={(e) => patch(i, { nature: e.target.value as EmploymentNature })}>
              {NATURE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {r.kind === "exit" ? (
              <select aria-label="퇴사 사유" value={r.exit_reason ?? ""} className="rounded border px-1.5 py-1 text-xs"
                onChange={(e) => patch(i, { exit_reason: (e.target.value || null) as EmploymentExitReason | null })}>
                <option value="">사유 모름</option>
                {EXIT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <select aria-label="입사 통로" value={r.channel ?? ""} className="rounded border px-1.5 py-1 text-xs"
                onChange={(e) => patch(i, { channel: (e.target.value || null) as EmploymentChannel | null })}>
                <option value="">통로 모름</option>
                {CHANNEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            )}
            <input aria-label="같은 직장 묶기" placeholder="묶기(예: A)" value={r.group ?? ""}
              onChange={(e) => patch(i, { group: e.target.value })}
              className="rounded border px-1.5 py-1 text-xs" />
            <input aria-label="표시용 이름" placeholder="이름(선택)" value={r.org ?? ""}
              onChange={(e) => patch(i, { org: e.target.value })}
              className="rounded border px-1.5 py-1 text-xs" />
            <button type="button" onClick={() => remove(i)} aria-label="줄 삭제"
              className="rounded border px-1.5 py-1 text-xs text-zinc-500 hover:bg-zinc-50">
              삭제
            </button>
          </div>
        ))}
      </div>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <div className="flex items-center gap-2">
        <button type="button" onClick={add}
          className="rounded border border-zinc-300 px-3 py-1.5 text-zinc-700 hover:bg-zinc-50">
          줄 추가
        </button>
        <button type="button" onClick={submit} disabled={busy}
          className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "저장 중…" : hasPrior ? "수정 저장" : "저장"}
        </button>
      </div>
    </div>
  );
}
