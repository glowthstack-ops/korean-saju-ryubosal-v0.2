"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { InfoTooltip } from "@/components/layout/InfoTooltip";
import { fetchLuckMonths } from "@/lib/api";
import { ELEMENT_KO, elementLabel, elementStyle, ganjiKo } from "@/lib/elements";
import { applyCalibrationToLuckCycles, applyCalibrationToLuckPillars } from "@/lib/luck-calibration";
import type { CalibrationResult, LuckPillar, LuckSinsal, ManseResult, Profile } from "@/lib/types";

// 백엔드 응답에 일부 필드가 없어도(구버전/부분 데이터) 깨지지 않도록 방어.
function ent(obj: Record<string, number> | undefined | null): [string, number][] {
  return Object.entries(obj ?? {});
}

// ISO datetime → "YYYY-MM-DD HH:MM" (T 제거, 분까지만).
function fmtDT(v: unknown): string {
  const s = String(v ?? "");
  const m = s.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : s;
}

// 숫자를 소수 1자리로 정리(분 단위 보정값 가독성).
function r1(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n * 10) / 10) : String(v ?? "");
}

// 부호 명시(+/−): 가산/감산이 한눈에 보이도록 양수에도 +를 붙인다.
function s1(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v ?? "");
  const r = Math.round(n * 10) / 10;
  return (r > 0 ? "+" : "") + r;
}

// 표준시 offset(분) → "UTC+9시간" / "UTC+5:30".
function fmtOffset(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v ?? "");
  const sign = n >= 0 ? "+" : "-";
  const a = Math.abs(n);
  const h = Math.floor(a / 60);
  const m = a % 60;
  return m ? `UTC${sign}${h}:${String(m).padStart(2, "0")}` : `UTC${sign}${h}시간`;
}

function Card({
  title,
  info,
  action,
  children,
}: {
  title: string;
  info?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 flex items-center text-sm font-semibold">
        {title}
        {info && <InfoTooltip text={info} />}
        {action && <span className="ml-auto font-normal">{action}</span>}
      </h2>
      {children}
    </section>
  );
}

export function BirthSummaryBar({ result }: { result: ManseResult }) {
  const s = result.input_summary as Record<string, unknown>;
  const cal = s.calendar_type === "lunar" ? "음력" : "양력";
  // 입력 시간은 HH:MM 까지만(초 제거).
  const time = s.birth_time_unknown
    ? "시간 모름"
    : String(s.birth_time ?? "").slice(0, 5);
  const dir = s.daewoon_direction === "forward" ? "순행대운" : s.daewoon_direction === "backward" ? "역행대운" : "";
  return (
    <div className="rounded-lg bg-gray-900 p-3 text-sm text-white">
      ({cal}) {String(s.birth_date)} {time} · {String(s.birth_place_name)} ·{" "}
      {s.gender === "male" ? "남성" : s.gender === "female" ? "여성" : ""} {dir}
    </div>
  );
}

export function TrueSolarTimeCard({
  result,
  applyEquationOfTime = true,
  onToggleEquationOfTime,
}: {
  result: ManseResult;
  applyEquationOfTime?: boolean;
  onToggleEquationOfTime?: (value: boolean) => void;
}) {
  const tc = result.time_correction as Record<string, unknown> | null;
  if (!tc) return null;
  const changed = Boolean(tc.hour_pillar_changed_by_true_solar_time);
  return (
    <Card
      title="시간 보정 · 진태양시"
      info="태어난 지역의 경도와 균시차를 반영해 실제 태양 위치 기준 시각으로 맞춘 값입니다. 태어난 '시(時)' 기둥을 정확히 정하는 데 씁니다."
      action={
        onToggleEquationOfTime && (
          <label className="flex items-center gap-1 text-[11px] text-gray-500">
            <input
              type="checkbox"
              checked={applyEquationOfTime}
              onChange={(e) => onToggleEquationOfTime(e.target.checked)}
            />
            균시차 사용
          </label>
        )
      }
    >
      <ul className="space-y-1 text-xs text-gray-600">
        <li>표준시: {fmtOffset(tc.timezone_offset_minutes)} · 서머타임: {tc.daylight_saving_applied ? "적용" : "미적용"}</li>
        <li>
          경도보정: {s1(tc.longitude_correction_minutes)}분 ·{" "}
          {/* 미사용 시 원값을 밝은 회색(비활성)으로 노출 — 진태양시에만 미반영. */}
          <span className={applyEquationOfTime ? "" : "text-gray-300"}>
            균시차: {s1(tc.equation_of_time_minutes)}분{!applyEquationOfTime && " (미적용)"}
          </span>
        </li>
        <li>진태양시: {fmtDT(tc.true_solar_datetime)}</li>
        {changed && (
          <li className="rounded bg-amber-100 p-1 text-amber-800">
            ⚠ 진태양시 적용으로 시주 변경: {String(tc.standard_time_hour_pillar)}(일반시) → {String(tc.true_solar_time_hour_pillar)}(진태양시)
          </li>
        )}
      </ul>
    </Card>
  );
}

export function StrengthPanel({ result }: { result: ManseResult }) {
  const st = result.force_analysis.strength;
  const b = st.basis;
  return (
    <Card title="신강/신약" info="나(일간)를 돕는 기운과 빼앗는 기운을 견줘 사주가 강한지 약한지 보는 지표입니다. 어떤 기운이 필요한지 가늠하는 출발점이 됩니다.">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <b>{st.band}</b>
        {st.borderline && <span className="text-[11px] text-amber-600">경계값</span>}
        {st.element_presence_label && (
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">
            {st.element_presence_label}
          </span>
        )}
        {st.element_balance_status && st.element_balance_status !== "균형" && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">
            오행 {st.element_balance_status}
          </span>
        )}
      </p>
      {st.band_note && <p className="mt-1 text-[11px] text-amber-700">{st.band_note}</p>}
      {/* 종격·가종·통관·유통 등 중화/특수 해석 경고(용신 분석 산출). 신약/신강 판정 보조. */}
      {(result.yongsin_analysis.warnings ?? []).map((w) => (
        <p key={w} className="mt-1 rounded bg-violet-50 px-2 py-1 text-[11px] text-violet-700">
          ⚖ {w.replace("pseudo_follow(가종)", "가종(假從)")}
        </p>
      ))}
      {(st.reason ?? []).length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-xs text-gray-600">
          {(st.reason ?? []).map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
      <p className="mt-1 text-xs text-gray-500">
        득령 {b.deukryeong ? "O" : "X"} · 득지 {b.deukji ? "O" : "X"} · 득세 {b.deukse ? "O" : "X"} · 통근 {b.tonggeun ? "O" : "X"}
      </p>
    </Card>
  );
}

// 오행 막대 색(파스텔 셀과 같은 계열, 막대 가독용으로 한 단계 진하게).
const ELEMENT_BAR: Record<string, string> = {
  "木": "bg-green-400", "火": "bg-rose-400", "土": "bg-amber-400",
  "金": "bg-gray-400", "水": "bg-slate-500",
};

const EXCESS_THRESHOLD = 35; // % 초과 시 '과다'(5개 카테고리 균등 20% 대비, 약 1.75배).
const DEFICIENT_THRESHOLD = 9; // % 미만이면 '부족'(백엔드 판정과 통일). 0%는 '부재'로 별도 표기.

// 기준 점선(플롯 하단 기준 pct% 높이).
function ThresholdLine({ pct, className }: { pct: number; className: string }) {
  return (
    <div
      className={`pointer-events-none absolute inset-x-0 border-t border-dashed ${className}`}
      style={{ bottom: `${pct}%` }}
    />
  );
}

// 과다/부족/없음 배지 — 오행은 범례와 같은 색 칩, 십성은 대표 십성(그룹)명 칩.
function elBadge(e: string) {
  return <span key={e} className={`rounded px-1 ${elementStyle(e)}`}>{elementLabel(e)}</span>;
}
function tgBadge(name: string) {
  return (
    <span key={name} className="rounded border border-indigo-200 bg-indigo-50 px-1 text-indigo-600">{name}</span>
  );
}

// 서브타이틀 행 — 제목 + 과다/부족/없음 배지 + 우측 캡션.
function ChartHeading(
  { title, right, over, weak, absent }:
  { title: string; right: string; over: ReactNode[]; weak: ReactNode[]; absent: ReactNode[] },
) {
  return (
    <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
      <span className="text-xs font-semibold text-gray-700">{title}</span>
      {over.length > 0 && <span className="flex flex-wrap items-center gap-1 text-red-500">과다 {over}</span>}
      {weak.length > 0 && <span className="flex flex-wrap items-center gap-1 text-sky-600">부족 {weak}</span>}
      {absent.length > 0 && <span className="flex flex-wrap items-center gap-1 text-gray-400">없음 {absent}</span>}
      <span className="ml-auto text-gray-400">{right}</span>
    </div>
  );
}

// 세로 막대그래프 — 막대 높이 = 값(%)을 0~100% 축에 매핑. 점선=과다/부족 기준.
function BarChart({ rows }: { rows: { label: string; value: number; color: string }[] }) {
  if (rows.length === 0) return <p className="text-[11px] text-gray-400">해당 없음</p>;
  return (
    <div>
      <div className="relative h-28">
        <ThresholdLine pct={EXCESS_THRESHOLD} className="border-red-400/70" />
        <ThresholdLine pct={DEFICIENT_THRESHOLD} className="border-sky-300" />
        <div className="flex h-full items-stretch gap-1.5">
          {rows.map((r) => (
            <div key={r.label} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
              <span className="mb-0.5 text-[10px] tabular-nums text-gray-500">{r.value}%</span>
              <div className={`w-full rounded-t ${r.color}`} style={{ height: `${Math.min(r.value, 100)}%` }} />
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1 flex gap-1.5">
        {rows.map((r) => (
          <span key={r.label} className="min-w-0 flex-1 whitespace-nowrap text-center text-[11px] font-medium text-gray-500">{r.label}</span>
        ))}
      </div>
    </div>
  );
}

// 십성 5그룹(비겁/식상/재성/관성/인성) — 각 그룹 막대 + 하위 십성 비율.
const TEN_GOD_GROUPS = [
  { name: "비겁", members: ["비견", "겁재"] },
  { name: "식상", members: ["식신", "상관"] },
  { name: "재성", members: ["정재", "편재"] },
  { name: "관성", members: ["정관", "편관"] },
  { name: "인성", members: ["정인", "편인"] },
] as const;

function tenGodGroups(data: Record<string, number>) {
  return TEN_GOD_GROUPS.map((g) => {
    const members = g.members
      .map((m) => ({ name: m, value: data[m] ?? 0 }))
      .sort((a, b) => b.value - a.value);
    const total = Math.round(members.reduce((s, m) => s + m.value, 0) * 100) / 100;
    return { name: g.name, total, members };
  }).sort((a, b) => b.total - a.total);
}

function TenGodGroupChart({ data }: { data: Record<string, number> }) {
  const groups = tenGodGroups(data);

  return (
    <div>
      <div className="relative h-28">
        <ThresholdLine pct={EXCESS_THRESHOLD} className="border-red-400/70" />
        <ThresholdLine pct={DEFICIENT_THRESHOLD} className="border-sky-300" />
        <div className="flex h-full items-stretch gap-1.5">
          {groups.map((g) => (
            <div key={g.name} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
              <span className="mb-0.5 text-[10px] tabular-nums text-gray-500">{g.total}%</span>
              <div className="w-full rounded-t bg-indigo-400" style={{ height: `${Math.min(g.total, 100)}%` }} />
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1 flex gap-1.5">
        {groups.map((g) => (
          <div key={g.name} className="flex min-w-0 flex-1 flex-col items-center">
            {/* 그룹명: Level 2 */}
            <span className="text-[11px] font-medium text-gray-500">{g.name}</span>
            {/* 하위 십성 상세: Level 3(작고 흐리게 + 간격) */}
            <div className="mt-1 flex flex-col items-center gap-0.5 text-[9px] leading-tight">
              {g.members.map((m) => (
                <span key={m.name} className={m.value > 0 ? "text-gray-400" : "text-gray-300"}>
                  {m.name} {m.value}%
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const DIST_MODES = [
  { key: "raw", label: "사주원국", desc: "지장간 미적용 · 원국 표면 글자 기준" },
  { key: "env", label: "지장간+환경보정", desc: "지장간 반영 · 일간 제외 환경 분포" },
  { key: "season", label: "월령 보정(세력판단용)", desc: "월령 보정 세력(신강약·용신 판단용)" },
] as const;

export function DistributionPanel({ result }: { result: ManseResult }) {
  const fe = result.force_analysis.five_elements;
  const tg = result.force_analysis.ten_gods;
  const amjang = fe.hidden_only_elements ?? [];
  const [mode, setMode] = useState<(typeof DIST_MODES)[number]["key"]>("env");

  // 모드별 데이터 소스(오행/십성).
  const SRC: Record<string, { el: Record<string, number>; tg: Record<string, number> }> = {
    raw: { el: fe.visible_percent, tg: tg.visible_percent },
    env: { el: fe.distribution_environment, tg: tg.distribution },
    season: { el: fe.season_adjusted_element_strength, tg: tg.season_adjusted_ten_god_strength },
  };
  const src = SRC[mode];
  const elRows = ent(src.el).map(([e, v]) => ({
    key: e, label: elementLabel(e), value: v, color: ELEMENT_BAR[e] ?? "bg-gray-300",
  }));
  const desc = DIST_MODES.find((m) => m.key === mode)!.desc;

  // 과다(>35) / 부족(0<v<9) / 없음(0) — 오행은 원소키, 십성은 그룹명 기준.
  const elOver = elRows.filter((r) => r.value > EXCESS_THRESHOLD).map((r) => elBadge(r.key));
  const elWeak = elRows.filter((r) => r.value > 0 && r.value < DEFICIENT_THRESHOLD).map((r) => elBadge(r.key));
  const elAbsent = elRows.filter((r) => r.value <= 0).map((r) => elBadge(r.key));
  const tgGroups = tenGodGroups(src.tg);
  const tgOver = tgGroups.filter((g) => g.total > EXCESS_THRESHOLD).map((g) => tgBadge(g.name));
  const tgWeak = tgGroups.filter((g) => g.total > 0 && g.total < DEFICIENT_THRESHOLD).map((g) => tgBadge(g.name));
  const tgAbsent = tgGroups.filter((g) => g.total <= 0).map((g) => tgBadge(g.name));

  return (
    <Card title="오행 · 십성 분포" info="사주를 이루는 다섯 기운(오행)과 나를 기준으로 한 관계(십성)의 분포입니다. 탭으로 보는 기준(원국 글자 / 지장간 포함 / 계절 반영)을 바꿀 수 있습니다.">
      <div className="mb-3 flex flex-wrap gap-1">
        {DIST_MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => setMode(m.key)}
            className={`rounded px-2 py-1 text-[11px] ${
              mode === m.key ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-gray-400">{desc}</p>
      <p className="mb-3 text-[11px] text-gray-400">
        수치 판정 기준: <span className="text-red-500">과다 {EXCESS_THRESHOLD}%이상</span>, <span className="text-sky-600">부족 {DEFICIENT_THRESHOLD}%미만</span>, <span className="text-gray-400">없음 0%</span>
      </p>

      <div className="space-y-3">
        <div>
          <ChartHeading
            title="오행"
            right={mode === "raw" ? "일간 포함" : "일간 제외"}
            over={elOver}
            weak={elWeak}
            absent={elAbsent}
          />
          <BarChart rows={elRows} />
        </div>
        <div>
          <ChartHeading title="십성" right="일간 제외" over={tgOver} weak={tgWeak} absent={tgAbsent} />
          <TenGodGroupChart data={src.tg} />
        </div>
        {/* 암장: 오행이자 십성 → 하단에 합쳐, 위치별 지장간·오행(색배지)·십성을 함께 표기. */}
        {amjang.length > 0 && (
          <div className="text-[11px] text-gray-500">
            <div className="text-[11px]">
              <span className="font-semibold text-gray-700">암장</span>
              <span className="text-gray-400"> - 지장간에만 있음</span>
            </div>
            <ul className="mt-0.5 space-y-0.5">
              {amjang.flatMap((h) => h.sources).map((s, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5">
                  <span className="text-gray-600">{s.position} {s.stage} {s.stem}</span>
                  {/* 오행: 사주 원국 범례와 동일한 색 배지 */}
                  <span className={`rounded px-1.5 py-0.5 ${elementStyle(s.element)}`}>
                    {elementLabel(s.element)}
                  </span>
                  {/* 십성: 십성 그래프 과다/부족 표시와 동일한 단일 컬러 칩 */}
                  {tgBadge(s.ten_god)}
                </li>
              ))}
            </ul>
            <div className="mt-0.5 text-gray-400">표면에 안 드러나 작동력 낮음</div>
          </div>
        )}
      </div>
    </Card>
  );
}

// 성패 등급 → 배지 색(내부 점수 대신 한글 라벨만 노출).
const SF_BADGE: Record<string, string> = {
  complete_success: "bg-green-100 text-green-700",
  partial_success: "bg-green-100 text-green-700",
  mixed: "bg-amber-100 text-amber-700",
  failure_with_rescue: "bg-red-100 text-red-600",
  clear_failure: "bg-red-100 text-red-600",
  severe_muddiness: "bg-red-100 text-red-600",
};
// 특수격 타입 → 한글(내부 코드 dominant/follow 숨김).
const SPECIAL_TYPE_KO: Record<string, string> = { dominant: "전왕·일행득기", follow: "종격" };

export function GeokgukPanel({ result }: { result: ManseResult }) {
  const g = result.geokguk as Record<string, unknown>;
  const e = g.evaluation as Record<string, unknown> | null | undefined;
  const candidates = (g.candidates as Array<Record<string, unknown>> | undefined) ?? [];
  const special = g.special_pattern as Record<string, unknown> | null | undefined;
  const aux = (g.auxiliary_structures as string[] | undefined) ?? [];
  // 파격은 코드 대신 한글 근거(evidence)+구제 여부로 표시.
  const failures = ((e?.failures as Array<Record<string, unknown>> | undefined) ?? []).filter((f) => f.active);
  const sfGrade = String(e?.success_failure_grade ?? "");
  return (
    <Card title="격국" info="월(月)을 중심으로 본 사주의 큰 틀로, 직업·사회적 역할의 성향을 읽는 데 씁니다. 용신 판단의 참고이며 이것만으로 용신을 정하지는 않습니다.">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <b>{String(g.main_structure)}</b>
        {e && (
          <span className={`rounded px-1.5 py-0.5 text-[11px] ${SF_BADGE[sfGrade] ?? "bg-gray-100 text-gray-600"}`}>
            {String(e.success_failure_label)}
          </span>
        )}
      </p>
      {special && (
        <div className="mt-1.5 rounded border border-violet-200 bg-violet-50 p-2 text-xs text-violet-700">
          <b>{special.override ? "특수격: " : "특수격 가능성: "}{String(special.name)}</b>
          <span className="text-violet-500"> ({SPECIAL_TYPE_KO[String(special.type)] ?? String(special.type)})</span>
          <div className="text-violet-500">
            {String(special.reason)}
            {special.override ? ` — 정격(${String(special.jeonggyeok)})과 병행 해석` : " — 정격과 병행 검토"}
          </div>
        </div>
      )}
      {e && (
        <div className="mt-1.5 space-y-1 text-xs text-gray-600">
          <div>{String(e.social_expression)}</div>
          <div className="text-gray-500">{String(e.clarity_policy)}</div>
          {failures.length > 0 && (
            <div className="text-amber-700">
              병(파격): {failures.map((f) => `${String(f.evidence)}${f.rescued ? "(구제 있음)" : "(구제 없음)"}`).join(" · ")}
            </div>
          )}
        </div>
      )}
      {aux.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-xs text-gray-500">
          {aux.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
      {candidates.length > 1 && (
        <details className="mt-1.5 text-xs text-gray-500">
          <summary className="cursor-pointer">격 후보</summary>
          <ul className="mt-1 space-y-0.5">
            {candidates.map((c, i) => (
              <li key={i} className={i === 0 ? "text-gray-700" : ""}>
                {String(c.name)}<span className="text-gray-400"> · {String(c.source)}</span>
                {c.revealed ? <span className="ml-1 text-emerald-600">투간</span> : null}
                <span className="ml-1 text-gray-400">{i === 0 ? "주격" : "보조"}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

// 관계 표기 라벨(합충형파해). 천간/지지 구분은 정렬 순서로 처리.
const REL_LABEL: Record<string, string> = {
  stem_combination: "합", six_combination: "합", three_harmony: "삼합",
  half_harmony: "반합", directional: "방합", clash: "충",
  punishment: "형", self_punishment: "형", break: "파", harm: "해",
};
// 컬럼 배치 순서 — 상단 사주 명식과 동일하게 시·일·월·년(좌→우).
const COL_ORDER = ["hour", "day", "month", "year"] as const;

// 천을귀인(일간 → 해당 지지) fallback — 백엔드 sinsal_catalog.CHEONEUL과 동일.
// 응답에 cheoneul_targets가 있으면 그 값을 우선 사용(구버전 응답 대비 표만 유지).
const CHEONEUL: Record<string, string[]> = {
  "甲": ["丑", "未"], "戊": ["丑", "未"], "庚": ["丑", "未"],
  "乙": ["子", "申"], "己": ["子", "申"],
  "丙": ["亥", "酉"], "丁": ["亥", "酉"],
  "辛": ["寅", "午"],
  "壬": ["卯", "巳"], "癸": ["卯", "巳"],
};
const POS_KO: Record<string, string> = { hour: "시", day: "일", month: "월", year: "년" };

// 하단 텍스트 나열용 항목명(병존·간여지동 포함). 충은 scope로 천간/지지 구분.
function itemLabel(item: Record<string, unknown>): string {
  const rt = String(item.relation_type);
  const scope = String(item.scope);
  switch (rt) {
    case "stem_combination": return "천간합";
    case "six_combination": return "육합";
    case "three_harmony": return "삼합";
    case "half_harmony": return "반합";
    case "directional": return "방합";
    case "clash": return scope === "stem" ? "천간충" : "지지충";
    case "punishment": {
      // notes(삼형/무례지형)를 라벨로 흡수해 종류별로 세분화.
      const notes = (item.notes as string[] | undefined) ?? [];
      if (notes.includes("삼형")) return "삼형";
      if (notes.includes("무례지형")) return "무례지형";
      return "형";
    }
    case "self_punishment": return "자형";
    case "break": return "파";
    case "harm": return "해";
    case "stem_duplication": return "천간 병존";
    case "branch_duplication": return "지지 병존";
    case "gan_yeo_ji_dong": return "간여지동";
    default: return rt;
  }
}

// 하단 목록 정렬: 천간 항목 먼저, 이어서 지지 항목.
function itemOrder(item: Record<string, unknown>): number {
  const rt = String(item.relation_type);
  const scope = String(item.scope);
  if (rt === "stem_combination") return 0; // 천간합
  if (rt === "clash" && scope === "stem") return 1; // 천간충
  if (rt === "stem_duplication") return 2; // 천간 병존
  if (["six_combination", "three_harmony", "half_harmony", "directional"].includes(rt)) return 10; // 지지합
  if (rt === "clash") return 11; // 지지충
  if (rt === "punishment" || rt === "self_punishment") return 12; // 지지형
  if (rt === "break") return 13; // 지지파
  if (rt === "harm") return 14; // 지지해
  if (rt === "branch_duplication") return 15; // 지지 병존
  if (rt === "gan_yeo_ji_dong") return 20; // 간여지동(천간·지지 동일 오행)
  return 99;
}

// 자리(positions)를 사주 원국 순서(시·일·월·년)로 정렬.
function sortedPositions(item: Record<string, unknown>): string[] {
  return ((item.positions as string[]) ?? [])
    .slice()
    .sort((a, b) => COL_ORDER.indexOf(a as typeof COL_ORDER[number]) - COL_ORDER.indexOf(b as typeof COL_ORDER[number]));
}

// "자형: 亥亥 (일·월) · 무례지형" 형태 한 줄. 간여지동은 오행을 함께 표기.
function itemLine(item: Record<string, unknown>, pillars: Pillars): string {
  const scope = String(item.scope);
  const ordered = sortedPositions(item);
  // 한자도 자리 순서(시·일·월·년)에 맞춰, 그 자리의 실제 간지로 표기.
  // 천간·지지 관계는 위치로 읽고, pillar 관계(간여지동)는 멤버(천간+지지) 그대로.
  const chars = (scope === "stem" || scope === "branch")
    ? ordered.map((p) => posChar(pillars, p, scope)).join("")
    : ((item.members as string[]) ?? []).join("");
  // 간여지동은 오행이 핵심 → "간여지동: 庚申(년주, 오행: 금)" 전용 포맷.
  if (String(item.relation_type) === "gan_yeo_ji_dong") {
    const posJu = ordered.map((p) => `${POS_KO[p] ?? p}주`).join("·");
    const els = [...new Set((item.affected_elements as string[] | undefined) ?? [])]
      .map((e) => ELEMENT_KO[e] ?? e)
      .join("·");
    return `${itemLabel(item)}: ${chars}(${posJu}${els ? `, 오행: ${els}` : ""})`;
  }
  const pos = ordered.map((p) => POS_KO[p] ?? p).join("·");
  return `${itemLabel(item)}: ${chars}${pos ? ` (${pos})` : ""}`;
}

// 표시 순서: 천간합 → 천간충 → 지지합 → 지지충 → 지지형 → 지지파 → 지지해.
function relOrder(i: Record<string, unknown>): number {
  const rt = String(i.relation_type);
  const scope = String(i.scope);
  if (rt === "stem_combination") return 0; // 천간합
  if (rt === "clash" && scope === "stem") return 1; // 천간충
  if (["six_combination", "three_harmony", "half_harmony", "directional"].includes(rt)) return 2; // 지지합
  if (rt === "clash") return 3; // 지지충
  if (rt === "punishment" || rt === "self_punishment") return 4; // 지지형
  if (rt === "break") return 5; // 지지파
  if (rt === "harm") return 6; // 지지해
  return 9;
}

type Pillars = ManseResult["pillars"];

// 멤버 배열 순서가 아니라 '그 자리의 실제 간지'를 쓴다(삼합·삼형 정합성 보장).
function posChar(pillars: Pillars, pos: string, scope: string): string {
  const p = (pillars as unknown as Record<string, { stem: string; branch: string } | null>)[pos];
  if (!p) return "";
  return scope === "stem" ? p.stem : p.branch;
}

// 박스 폭(px) — 라인이 박스 안쪽 가장자리에서 시작/끝나도록 계산에 사용.
const BOX_W = 44;
const BOX_HALF = BOX_W / 2;
const ARROW_GAP = 4; // 화살촉과 박스 사이 여백(px).
// 4분할 컬럼 중심 위치(%) — 상단 명식의 시·일·월·년 컬럼 중심과 동일.
const colCenter = (i: number) => (i + 0.5) * 25;

// 관여 위치를 시·일·월·년 컬럼 중심에 배치하고, 박스 안쪽 가장자리끼리 화살표로 잇는다.
function InteractionRow({ item, pillars }: { item: Record<string, unknown>; pillars: Pillars }) {
  const scope = String(item.scope);
  const positions = (item.positions as string[]) ?? [];
  const label = REL_LABEL[String(item.relation_type)] ?? String(item.relation_type);
  const cols = [...new Set(positions.map((p) => COL_ORDER.indexOf(p as typeof COL_ORDER[number])))]
    .filter((c) => c >= 0)
    .sort((a, b) => a - b);
  if (cols.length === 0) return null;
  const lo = cols[0];
  const hi = cols[cols.length - 1];
  return (
    <div className="relative h-10">
      {/* 연결선 + 양끝 화살촉 + 라벨: 두 박스의 안쪽 가장자리 사이만 잇는다. */}
      {hi > lo && (
        <div
          className="absolute top-1/2 flex -translate-y-1/2 items-center"
          style={{
            left: `calc(${colCenter(lo)}% + ${BOX_HALF + ARROW_GAP}px)`,
            width: `calc(${colCenter(hi) - colCenter(lo)}% - ${BOX_W + ARROW_GAP * 2}px)`,
          }}
        >
          <span className="h-0 w-0 border-y-4 border-r-[6px] border-y-transparent border-r-gray-400" />
          <span className="h-px flex-1 bg-gray-300" />
          <span className="px-1 text-[11px] font-medium leading-none text-gray-900">{label}</span>
          <span className="h-px flex-1 bg-gray-300" />
          <span className="h-0 w-0 border-y-4 border-l-[6px] border-y-transparent border-l-gray-400" />
        </div>
      )}
      {/* 위치별 간지 박스 — 한글 독음은 한자 우측에 병기. */}
      {positions.map((pos) => {
        const c = COL_ORDER.indexOf(pos as typeof COL_ORDER[number]);
        if (c < 0) return null;
        const ch = posChar(pillars, pos, scope);
        return (
          <span
            key={pos}
            style={{ left: `${colCenter(c)}%`, width: `${BOX_W}px` }}
            className="absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded border border-gray-300 bg-white py-0.5 text-center leading-none"
          >
            <span className="text-sm font-semibold">{ch}</span>
            <span className="text-[10px] text-gray-400">{ganjiKo(ch)}</span>
          </span>
        );
      })}
    </div>
  );
}

export function StructurePanel({ result }: { result: ManseResult }) {
  const pillars = result.pillars;
  const items = [...result.structure_analysis.interactions].sort(
    (a, b) => relOrder(a) - relOrder(b),
  );
  // 병존·간여지동 등은 다이어그램에 안 나오므로 하단 텍스트 목록에 합쳐서 누락 방지.
  // 정렬: 천간 항목 → 지지 항목.
  const amplifiers = result.structure_analysis.amplifiers ?? [];
  const allItems = [...items, ...amplifiers].sort((a, b) => itemOrder(a) - itemOrder(b));
  const gm = result.structure_analysis.gongmang as Record<string, unknown> | null;
  const dayVoid = (gm?.day_basis_empty_branches as string[] | undefined) ?? [];
  const yearVoid = (gm?.year_basis_empty_branches as string[] | undefined) ?? [];
  // 천을귀인(일간 기준 지지) · 월령 — 공망과 함께 하단에 참고 표기.
  // 백엔드 산출값(cheoneul_targets) 우선, 없으면(구버전 응답) 로컬 표 fallback.
  const cheoneul =
    result.traditional_extras?.sinsal?.cheoneul_targets
    ?? CHEONEUL[pillars.day_master]
    ?? [];
  // 월령 대표 글자 = 월지의 정기(본기) 지장간. (월지 자체가 아님)
  const monthHidden = pillars.month.hidden_stems ?? [];
  const wolryeongStem = (monthHidden.find((h) => h.type === "main") ?? monthHidden[0])?.stem
    ?? pillars.month.branch;
  const withKo = (chars: string[]) => chars.map((c) => `${c}(${ganjiKo(c)})`).join(" · ");
  return (
    <div className="space-y-2">
      {/* px-0: 상단 명식과 좌우 폭을 맞춰 컬럼이 수직 정렬되도록. */}
      <section className="rounded-lg border bg-white py-3">
        {items.length === 0 ? (
          <p className="px-4 text-xs text-gray-400">특이 관계 없음</p>
        ) : (
          // 컬럼 머리글(시·일·월·년)은 상단 명식 기준이라 생략.
          <div className="space-y-1">
            {items.map((i, idx) => <InteractionRow key={idx} item={i} pillars={pillars} />)}
          </div>
        )}
      </section>
      {/* 구조 항목 전체 텍스트 나열(병존·간여지동·공망 포함) — 기본 접힘. */}
      <details className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3 text-xs text-gray-600">
        <summary className="cursor-pointer font-semibold text-gray-700">원국 구조 상세</summary>
        <ul className="mt-1.5 space-y-0.5">
          {allItems.length === 0 && (
            <li className="text-gray-400">합·충·형·파·해·병존 등 특이 항목 없음</li>
          )}
          {allItems.map((it, idx) => <li key={idx}>{itemLine(it, pillars)}</li>)}
        </ul>
        <div className="mt-1.5 space-y-1 border-t border-gray-200 pt-1.5">
          {gm && (
            <div>
              <span className="mr-2 font-bold text-gray-700">공망</span>
              일 기준: {dayVoid.join("") || "없음"} · 년 기준: {yearVoid.join("") || "없음"}(미사용)
            </div>
          )}
          <div>
            <span className="mr-2 font-bold text-gray-700">천을귀인</span>
            {cheoneul.length ? withKo(cheoneul) : "없음"}
          </div>
          <div>
            <span className="mr-2 font-bold text-gray-700">월령</span>
            {withKo([wolryeongStem])}
            <span className="ml-1 text-gray-400">
              · 월지 {pillars.month.branch}({ganjiKo(pillars.month.branch)}) 정기
            </span>
          </div>
        </div>
      </details>
    </div>
  );
}

export function SinsalPanel({ result }: { result: ManseResult }) {
  const sinsal = result.traditional_extras?.sinsal?.full_list ?? [];
  // 시주·일주·월주·년주 — 상단 명식과 동일한 순서로 자리별 박스 구분.
  const cols: [("hour" | "day" | "month" | "year"), string][] = [
    ["hour", "시주"], ["day", "일주"], ["month", "월주"], ["year", "년주"],
  ];
  return (
    <section>
      {/* 사주 원국과 동일하게 외곽 박스 없이 제목 + 자리별 컬럼. */}
      <h2 className="mb-2 flex items-center text-sm font-semibold">
        신살/길성
        <InfoTooltip text="예부터 전해지는 상징적 별칭(길·흉의 신호)입니다. 해석을 풍부하게 하는 보조 정보로 참고하며, 길흉을 단정하지는 않습니다." />
      </h2>
      <div className="flex gap-2">
        {cols.map(([pos, ko]) => {
          const items = sinsal.filter((s) => s.position === pos);
          return (
            <div key={pos} className="flex flex-1 flex-col rounded-lg border bg-white p-2">
              <div className="mb-1 text-center text-xs font-semibold text-gray-500">{ko}</div>
              <div className="flex flex-1 flex-wrap content-start justify-center gap-1">
                {items.length === 0 && <span className="text-[11px] text-gray-300">-</span>}
                {items.map((s, i) => (
                  <span key={i} className="rounded border px-1.5 py-0.5 text-[11px]" title={s.basis}>
                    {s.name}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const LUCK_LABEL_SHORT: Record<string, { txt: string; cls: string }> = {
  pure_yongsin_luck: { txt: "용신운", cls: "bg-emerald-100 text-emerald-800" },
  pure_gisin_luck: { txt: "기신운", cls: "bg-rose-100 text-rose-800" },
  mixed_yongsin_surface: { txt: "천용·지기", cls: "bg-amber-100 text-amber-800" },
  mixed_gisin_surface: { txt: "천기·지용", cls: "bg-amber-100 text-amber-800" },
  partial_yongsin: { txt: "용신(부분)", cls: "bg-emerald-50 text-emerald-700" },
  partial_gisin: { txt: "기신(부분)", cls: "bg-rose-50 text-rose-700" },
  trigger_luck: { txt: "변동", cls: "bg-violet-100 text-violet-800" },
  neutral_luck: { txt: "평운", cls: "bg-gray-100 text-gray-500" },
};

function luckChip(code?: string, fallback?: string) {
  const m = code ? LUCK_LABEL_SHORT[code] : undefined;
  if (!m) return <span className="text-gray-500">{fallback ?? "-"}</span>;
  return <span className={`rounded px-1 py-0.5 text-[10px] ${m.cls}`}>{m.txt}</span>;
}

function polSign(p?: { element: string; score: number } | null) {
  if (!p) return "";
  const s = p.score > 0.15 ? "↑" : p.score < -0.15 ? "↓" : "·";
  return `${p.element}${s}`;
}

// 만세력 카드 한 칸: 상단 라벨 + 천간/십성 박스 + 지지/운성 박스(오행색). 선택·클릭 지원.
// 신살 polarity → 한글 분류(툴팁용).
const SINSAL_POLARITY_KO: Record<string, string> = {
  positive: "길신",
  caution: "흉성",
  neutral: "신살",
};

// 일주복음 전용 툴팁 — 운 간지가 일주와 동일할 때만 등장.
const BOGEUM_DESC =
  "복음(伏吟) · 운의 간지가 일주와 동일 — 엎드려 신음하는 형국으로 정체·반복·내적 침체를 의미";

function sinsalTitle(s: LuckSinsal): string {
  if (s.name === "복음") return BOGEUM_DESC;
  return `${SINSAL_POLARITY_KO[s.polarity] ?? "신살"} · ${s.name}`;
}

function LuckCol({
  topLabel, stem, branch, stemEl, branchEl, stemGod, branchGod, unseong, sinsal,
  current, selected, onClick, colRef,
}: {
  topLabel: string;
  stem: string;
  branch: string;
  stemEl?: string;
  branchEl?: string;
  stemGod: string;
  branchGod: string;
  unseong?: string;
  sinsal?: LuckSinsal[];
  current?: boolean;
  selected?: boolean;
  onClick?: () => void;
  colRef?: React.Ref<HTMLButtonElement>;
}) {
  const ring = selected
    ? "ring-2 ring-indigo-400 bg-indigo-50"
    : current
      ? "ring-1 ring-yellow-300 bg-yellow-50"
      : "";
  return (
    <button ref={colRef} type="button" onClick={onClick}
      className={`flex w-16 shrink-0 flex-col items-center gap-1 rounded p-1.5 ${ring} ${onClick ? "cursor-pointer hover:bg-gray-50" : ""}`}>
      <div className="text-[11px] font-semibold leading-none text-gray-700">{topLabel}</div>
      <div className="text-[10px] leading-none text-gray-400">{stemGod}</div>
      <div className="w-full">
        <div className={`rounded-t border text-center ${elementStyle(stemEl)}`}>
          <div className="pt-1.5 text-lg font-bold leading-none">{stem}</div>
          <div className="pb-1 pt-0.5 text-[10px] leading-none opacity-80">{ganjiKo(stem)}</div>
        </div>
        <div className={`rounded-b border-x border-b text-center ${elementStyle(branchEl)}`}>
          <div className="pt-1.5 text-lg font-bold leading-none">{branch}</div>
          <div className="pb-1 pt-0.5 text-[10px] leading-none opacity-80">{ganjiKo(branch)}</div>
        </div>
      </div>
      <div className="text-[10px] leading-none text-gray-400">{branchGod}</div>
      {unseong && <div className="text-[10px] leading-none text-gray-400">{unseong}</div>}
      {sinsal && sinsal.length > 0 && (
        <div className="mt-0.5 w-full border-t border-gray-200 pt-0.5">
          <div className="flex flex-wrap justify-center gap-x-0.5 gap-y-px leading-tight">
            {sinsal.map((s, i) => (
              <span
                key={i}
                title={sinsalTitle(s)}
                className={s.name === "복음"
                  ? "text-[9px] font-medium text-amber-600"
                  : "text-[9px] text-gray-500"}
              >
                {s.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </button>
  );
}

function LuckStrip({
  label,
  hint,
  note,
  children,
}: {
  label: string;
  hint?: string;
  note?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-xs font-semibold text-gray-700">
        {label}
        {hint && <span className="ml-1 font-normal text-[10px] text-gray-400">{hint}</span>}
      </p>
      {/* note: 서브타이틀 아래·컬럼 위에 들어가는 보조 설명(예: 대운의 순행/대운수). */}
      {note}
      {/* 우→좌 오름차순(작은 값이 오른쪽): 렌더 시 배열을 역순으로 넘긴다.
          py로 선택 링이 스크롤 컨테이너에 잘리지 않도록 여백 확보.
          md↑(카드 폭 충분)에서는 gap을 좁혀 10칸이 가로 스크롤 없이 들어가게 한다. */}
      <div className="flex gap-2 overflow-x-auto px-1 pt-1.5 pb-2 md:gap-1">{children}</div>
    </div>
  );
}

// 선택/현재 칸을 가로 스크롤 컨테이너의 가운데로(페이지 세로 스크롤은 건드리지 않음).
function centerInScroll(el: HTMLElement | null) {
  const p = el?.parentElement;
  if (!el || !p) return;
  p.scrollLeft = el.offsetLeft - p.clientWidth / 2 + el.offsetWidth / 2;
}

export function LuckPanel({
  result,
  profile,
  timeOptions,
  calibration,
}: {
  result: ManseResult;
  profile?: Profile;
  calibration?: CalibrationResult | null;
  // 화면에 표시 중인 차트와 같은 시간옵션(균시차 토글 상태)으로 월운을 계산하기 위한 전달값.
  timeOptions?: Record<string, unknown>;
}) {
  const lc = useMemo(
    () => applyCalibrationToLuckCycles(result.luck_cycles, calibration ?? null),
    [result.luck_cycles, calibration],
  );
  const router = useRouter();
  const [selDaewoon, setSelDaewoon] = useState<number>(lc?.current_daewoon_index ?? 0);
  const [selYear, setSelYear] = useState<number | null>(lc?.current_year ?? null);
  const [monthsCache, setMonthsCache] = useState<Record<number, LuckPillar[]>>(
    lc?.current_year != null ? { [lc.current_year]: lc.monthly_luck } : {},
  );
  const [loadingYear, setLoadingYear] = useState<number | null>(null);
  const dwRef = useRef<HTMLButtonElement>(null);
  const syRef = useRef<HTMLButtonElement>(null);
  const moRef = useRef<HTMLButtonElement>(null);
  // 최초/선택 변경 시 선택 칸을 가운데로 스크롤.
  useEffect(() => centerInScroll(dwRef.current), []);
  useEffect(() => centerInScroll(syRef.current), [selDaewoon]);
  useEffect(() => centerInScroll(moRef.current), [selYear, monthsCache]);
  // 균시차 토글 등으로 결과가 재계산되면 이전 옵션 기준의 월운 캐시를 버리고 재시드.
  useEffect(() => {
    setMonthsCache(lc?.current_year != null ? { [lc.current_year]: lc.monthly_luck } : {});
  }, [lc]);
  if (!lc) return null;

  const jiao = (lc.trace?.exact_jiao_un_dates as string[] | undefined) ?? [];
  const curMonthLabel =
    lc.current_year != null && lc.current_month != null
      ? `${lc.current_year}-${String(lc.current_month).padStart(2, "0")}`
      : null;

  const sewoon = lc.daewoon_table[selDaewoon]?.sewoon ?? [];
  const months = selYear != null ? monthsCache[selYear] ?? [] : [];

  const loadMonths = async (year: number) => {
    if (year === lc.current_year || monthsCache[year] || !profile) return;
    setLoadingYear(year);
    try {
      const m = await fetchLuckMonths(profile, year, undefined, timeOptions);
      const adjusted = applyCalibrationToLuckPillars(m, calibration ?? null);
      setMonthsCache((c) => ({ ...c, [year]: adjusted }));
    } catch {
      /* 무시: 로딩 실패 시 빈 상태 */
    } finally {
      setLoadingYear(null);
    }
  };

  const selectDaewoon = (idx: number) => {
    setSelDaewoon(idx);
    const years = (lc.daewoon_table[idx]?.sewoon ?? []).map((s) => Number(s.label));
    const y = lc.current_year != null && years.includes(lc.current_year) ? lc.current_year : years[0];
    setSelYear(y ?? null);
    if (y != null) loadMonths(y);
  };
  const selectYear = (year: number) => {
    setSelYear(year);
    loadMonths(year);
  };
  const selectMonth = (label: string) => {
    const [yy, mm] = label.split("-");
    router.push(`/calendar/${Number(yy)}/${Number(mm)}`);
  };

  return (
    <Card title="대운 · 세운 · 월운" info="10년·1년·1달 단위로 흘러오는 운의 흐름입니다. 타고난 사주는 그대로 두고, 시기마다 어떤 기운이 더해지는지 봅니다.">
      <LuckStrip
        label="대운"
        hint="선택 시 해당 세운이 표시됩니다"
        note={
          <p className="text-xs text-gray-600">
            {lc.direction === "forward" ? "순행" : "역행"} · 대운수 {lc.start_age}세
            {lc.current_age != null && ` · 현재 ${lc.current_age}세`}
          </p>
        }
      >
        {[...lc.daewoon_table].reverse().map((d) => (
          <LuckCol key={d.index} topLabel={`${d.start_age}세`} stem={d.stem} branch={d.branch}
            stemEl={d.stem_effect?.element} branchEl={d.branch_effect?.element}
            stemGod={d.stem_ten_god} branchGod={d.branch_ten_god} unseong={d.twelve_unseong}
            sinsal={d.luck_sinsal}
            current={d.index === lc.current_daewoon_index} selected={d.index === selDaewoon}
            colRef={d.index === selDaewoon ? dwRef : undefined}
            onClick={() => selectDaewoon(d.index)} />
        ))}
      </LuckStrip>

      {sewoon.length > 0 && (
        <LuckStrip label="세운" hint="선택 시 해당 월운이 표시됩니다">
          {[...sewoon].reverse().map((y) => (
            <LuckCol key={y.label} topLabel={y.label} stem={y.stem} branch={y.branch}
              stemEl={y.stem_effect?.element} branchEl={y.branch_effect?.element}
              stemGod={y.stem_ten_god} branchGod={y.branch_ten_god} unseong={y.twelve_unseong}
              sinsal={y.luck_sinsal}
              current={Number(y.label) === lc.current_year} selected={Number(y.label) === selYear}
              colRef={Number(y.label) === selYear ? syRef : undefined}
              onClick={() => selectYear(Number(y.label))} />
          ))}
        </LuckStrip>
      )}

      {selYear != null && (
        <LuckStrip label="월운" hint="선택 시 간지달력으로 이동합니다">
          {loadingYear === selYear && months.length === 0 ? (
            <span className="py-4 text-[11px] text-gray-400">월운 불러오는 중…</span>
          ) : (
            [...months].reverse().map((m) => (
              <LuckCol key={m.label} topLabel={`${Number(m.label.slice(5))}월`} stem={m.stem} branch={m.branch}
                stemEl={m.stem_effect?.element} branchEl={m.branch_effect?.element}
                stemGod={m.stem_ten_god} branchGod={m.branch_ten_god} unseong={m.twelve_unseong}
                sinsal={m.luck_sinsal}
                current={m.label === curMonthLabel}
                colRef={m.label === curMonthLabel ? moRef : undefined}
                onClick={() => selectMonth(m.label)} />
            ))
          )}
        </LuckStrip>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-semibold text-gray-700">대운 상세 정리</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-center text-[11px]">
            <thead className="text-gray-400">
              <tr className="border-b">
                <th className="px-2 py-1.5">나이</th><th className="px-2 py-1.5">간지</th>
                <th className="px-2 py-1.5">십성</th><th className="px-2 py-1.5">운성</th>
                <th className="px-2 py-1.5">용신관계</th><th className="px-2 py-1.5">교운일</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {lc.daewoon_table.map((d) => (
                <tr key={d.index} className={d.index === lc.current_daewoon_index ? "bg-yellow-50 font-semibold" : ""}>
                  <td className="px-2 py-2 align-middle">{d.start_age}</td>
                  <td className="px-2 py-2 align-middle">{d.ganji}</td>
                  <td className="px-2 py-2 align-middle">{d.stem_ten_god}/{d.branch_ten_god}</td>
                  <td className="px-2 py-2 align-middle">{d.twelve_unseong}</td>
                  <td className="px-2 py-2 align-middle" title={d.luck_summary}>
                    <div className="flex justify-center">{luckChip(d.luck_label_code, d.yongsin_relation)}</div>
                    <div className="mt-0.5 text-[9px] text-gray-400">천{polSign(d.stem_effect)} 지{polSign(d.branch_effect)}</div>
                    {/* 보라색 동태 설명: '·' 기준으로 의미 단위를 줄바꿈. 항상 2줄 높이 예약 → 셀 균일 */}
                    <div className="mx-auto mt-0.5 min-h-[2.2em] max-w-[9rem] text-[9px] leading-tight text-violet-500">
                      {(d.branch_effect?.branch_label ?? "")
                        .split("·")
                        .map((p) => p.trim())
                        .filter(Boolean)
                        .map((part) => (
                          <div key={part} className="break-keep">{part}</div>
                        ))}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 align-middle text-[10px] text-gray-500">{jiao[d.index] ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <dl className="mt-2 space-y-1 text-[10px] leading-snug text-gray-500">
          <div>
            <dt className="inline font-semibold text-gray-600">천간 · 지지</dt>
            <dd className="inline"> — 천간=드러나는 기회·표면, 지지=실제 기반·환경 (↑용신 ↓기신)</dd>
          </div>
          <div>
            <dt className="inline font-semibold text-gray-600">혼합운</dt>
            <dd className="inline"> — 천용·지기=겉은 기회·현실 부담, 천기·지용=초반 압박·기반 회복</dd>
          </div>
          <div>
            <dt className="inline font-semibold text-violet-500">지지 동태(보라)</dt>
            <dd className="inline"> — 공망=실속·지연(작동력↓), 충=사건화·변동(트리거↑), 공망충발=비었던 기운이 충 자극으로 사건화(불안정)</dd>
          </div>
        </dl>
      </details>
    </Card>
  );
}
