"use client";

// 출생시간 미상(시주 없음) 표시 요소 — 2026-10-06 데굴님 승인.
//
// 원칙: '미상'을 '없음'으로 보이지 않게 한다. 시주가 있어야 채워지는 영역은 흐릿한 예시 위에
// 반투명 레이어를 덮어 "실제 데이터가 있을 때 무엇이 보이는지" 짐작할 수 있게 하고, 12시진 후보에
// 따라 갈리는 판정(강약·격국·용희신)은 '미확정' 뱃지 + 같은 레이어로 가린다. 후보 전부 일치한
// 항목만 '후보 전부 일치' 뱃지로 제한적 신뢰를 표시한다.

import type { ReactNode } from "react";
import type { HourUnknownAnalysis, ManseResult } from "@/lib/types";

/** 시주 미상이면 분석 메타(없으면 null). 시간이 있으면 항상 null. */
export function hourUnknownOf(result: ManseResult): HourUnknownAnalysis | null {
  if (result.pillars.hour !== null) return null;
  return result.hour_unknown ?? null;
}

export function isHourUnknown(result: ManseResult): boolean {
  return result.pillars.hour === null;
}

const ITEM_KO: Record<string, string> = {
  strength_band: "신강약",
  geokguk: "격국",
  useful_gods: "용희신",
};

/** 결과 페이지 상단 배너 — 3기둥 기준임과 확정/미확정 항목을 한 번에 알린다. */
export function HourUnknownBanner({ result }: { result: ManseResult }) {
  if (!isHourUnknown(result)) return null;
  const hu = result.hour_unknown ?? null;
  const differ = hu?.unconfirmed ?? [];
  const agree = hu ? Object.keys(ITEM_KO).filter((k) => !differ.includes(k)) : [];
  const range = hu?.daewoon_start_range;
  return (
    <div
      role="status"
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <p className="font-medium">
        출생시간이 없어 연·월·일주(3기둥) 기준으로 계산했어요.
        {hu?.basis.startsWith("band:") && ` 대략 시간대 '${hu.approx_band}' 후보 ${hu.candidates.length}개로 좁혀 비교했어요.`}
        {hu?.basis.startsWith("hint:") && ` 성향 문항으로 좁힌 추정 시진 ${hu.hint_branch}시 기준이에요(추정 — 확정 아님).`}
        {hu?.basis.startsWith("variant:") && ` 경계 당일 명식 변형 중 선택한 변형(${hu.variant_choice?.join("")}시) 기준으로 표시 중이에요(보기 선택 — 확정 아님).`}
      </p>
      <ul className="mt-1 space-y-0.5 text-xs text-amber-800">
        {hu && hu.pillar_variants.length > 1 && (
          <li className="text-rose-700">
            <b>명식 분기</b> · 경계 당일이라 출생시각에 따라 명식 자체가 {hu.pillar_variants.length}갈래예요:{" "}
            {hu.pillar_variants.map((v) => `${v.year_ganji}·${v.month_ganji}·${v.day_ganji}(${v.hour_branches.join("")}시${v.is_base ? ", 현재 표시" : ""})`).join(" / ")}
            . 현재 표시 명식은 확정이 아니에요.
          </li>
        )}
        <li>
          <b>산출 불가</b> · 시주와 시지에 걸리는 십성·지장간·12운성·납음·신살·합충 — 흐린 예시 자리로
          표시했어요(시간을 입력하면 채워집니다).
        </li>
        <li>
          <b>부분 확인</b> · 오행·십성 분포, 합충·신살은 세 기둥에서 보이는 범위까지만이에요. 시주에서
          보충될 수 있어 &quot;없다&quot;고 단정하지 않아요.
        </li>
        {hu ? (
          <li>
            <b>12시진 후보 비교</b> · 일치 {agree.map((k) => ITEM_KO[k]).join("·") || "없음"} / 상이{" "}
            {differ.map((k) => ITEM_KO[k]).join("·") || "없음"}
            {differ.length > 0 && " — 상이 항목은 확정하지 않고 풀이에도 쓰지 않아요."}
          </li>
        ) : (
          <li>
            <b>후보 비교</b> · 미산출(시간 후보 비교 정보가 없어요).
          </li>
        )}
        {range && (
          <li>
            <b>범위 표시</b> · 대운수 {range[0]}~{range[1]}세(출생시각 범위에 따라 달라져요).
          </li>
        )}
        {(hu?.boundary_warnings ?? []).map((w) => (
          <li key={w} className="text-rose-700">
            <b>경계</b> · {w}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 항목별 후보 비교 뱃지 — agree: '후보 전부 일치', differ: '미확정'. 시간이 있으면 null. */
export function ConsensusBadge({
  hu,
  item,
}: {
  hu: HourUnknownAnalysis | null;
  item: "strength_band" | "geokguk" | "useful_gods";
}) {
  if (!hu) return null;
  const c = hu[item];
  if (c.status === "agree") {
    return (
      <span
        className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700"
        title="출생시간을 12시진 전부로 바꿔 계산해도 같은 결론 — 시주 미상이지만 결론이 유지돼요."
      >
        시주 후보 전부 일치
      </span>
    );
  }
  return (
    <span
      className="rounded bg-rose-50 px-1.5 py-0.5 text-[11px] text-rose-700"
      title={`출생시각에 따라 달라져요: ${c.values.join(" / ")}`}
    >
      미확정 · 후보 {c.values.join("/")}
    </span>
  );
}

/**
 * 반투명 고스트 레이어 — children(흐린 예시 또는 미확정 값)을 blur 처리하고 그 위에 안내 라벨을
 * 덮는다. 영역의 크기와 배치는 그대로 유지되어 "여기에 무엇이 들어오는지" 짐작할 수 있다.
 */
export function GhostOverlay({
  label,
  sub,
  children,
  className = "",
}: {
  label: string;
  sub?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`} aria-label={label}>
      <div className="pointer-events-none select-none blur-[3px] opacity-60" aria-hidden>
        {children}
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center rounded bg-white/55 px-2 text-center">
        <span className="rounded bg-gray-800/80 px-2 py-0.5 text-[11px] font-medium text-white">{label}</span>
        {sub && <span className="mt-1 text-[10px] leading-tight text-gray-600">{sub}</span>}
      </div>
    </div>
  );
}
