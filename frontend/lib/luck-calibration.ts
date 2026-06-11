import type { CalibrationResult, LuckCycles, LuckPillar, LuckPolarity } from "./types";

const STEM_ELEMENT: Record<string, string> = {
  "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
  "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
};

const BRANCH_HIDDEN: Record<string, Array<[string, number]>> = {
  "子": [["水", 0.3], ["水", 0.7]],
  "丑": [["水", 0.2], ["金", 0.2], ["土", 0.6]],
  "寅": [["土", 0.2], ["火", 0.2], ["木", 0.6]],
  "卯": [["木", 0.3], ["木", 0.7]],
  "辰": [["木", 0.2], ["水", 0.2], ["土", 0.6]],
  "巳": [["土", 0.2], ["金", 0.2], ["火", 0.6]],
  "午": [["火", 0.3], ["土", 0.2], ["火", 0.5]],
  "未": [["火", 0.2], ["木", 0.2], ["土", 0.6]],
  "申": [["土", 0.2], ["水", 0.2], ["金", 0.6]],
  "酉": [["金", 0.3], ["金", 0.7]],
  "戌": [["金", 0.2], ["火", 0.2], ["土", 0.6]],
  "亥": [["土", 0.2], ["木", 0.2], ["水", 0.6]],
};

function roleSets(calibration: CalibrationResult | null): { useful: Set<string>; unfavorable: Set<string> } | null {
  if (!calibration || calibration.status === "uncertain" || !calibration.final_yongsin) return null;
  return {
    useful: new Set([calibration.final_yongsin, calibration.final_heesin].filter(Boolean) as string[]),
    unfavorable: new Set([calibration.final_gisin, calibration.final_gusin].filter(Boolean) as string[]),
  };
}

function polarity(score: number): string {
  if (score > 0.15) return "용신";
  if (score < -0.15) return "기신";
  return "한신";
}

function elementScore(element: string | undefined, useful: Set<string>, unfavorable: Set<string>): number {
  if (!element) return 0;
  if (useful.has(element)) return 1;
  if (unfavorable.has(element)) return -1;
  return 0;
}

function stemEffect(stem: string, useful: Set<string>, unfavorable: Set<string>): LuckPolarity {
  const element = STEM_ELEMENT[stem] ?? "";
  const score = elementScore(element, useful, unfavorable);
  return { element, type: polarity(score), score };
}

function branchEffect(
  branch: string,
  previous: LuckPolarity | null | undefined,
  useful: Set<string>,
  unfavorable: Set<string>,
): LuckPolarity {
  const parts = BRANCH_HIDDEN[branch] ?? [];
  const base = parts.reduce((acc, [el, weight]) => acc + elementScore(el, useful, unfavorable) * weight, 0);
  let score = base;
  const isVoid = Boolean(previous?.is_void);
  const hasClash = Boolean(previous?.has_clash);
  let reliability = 1;
  let eventTrigger = 0;
  let volatility = 0;
  if (isVoid && hasClash) {
    score *= 0.65; reliability = 0.5; eventTrigger = 1.5; volatility = 1.5;
  } else if (isVoid) {
    score *= 0.6; reliability = 0.6; volatility = 1;
  } else if (hasClash) {
    score *= 0.8; reliability = 0.85; eventTrigger = 1; volatility = 1;
  }
  return {
    ...(previous ?? { element: "", type: "한신", score: 0 }),
    element: previous?.element ?? "",
    type: polarity(score),
    score: Math.round(score * 10000) / 10000,
    base_score: Math.round(base * 10000) / 10000,
    is_void: isVoid,
    has_clash: hasClash,
    event_trigger: eventTrigger,
    volatility,
    reliability,
  };
}

function label(stemType: string, branchType: string, strong: boolean): [string, string, string] {
  if (stemType === "용신" && branchType === "용신") return ["pure_yongsin_luck", "강한 용신운", "천간·지지가 모두 확정 용희신에 해당"];
  if (stemType === "기신" && branchType === "기신") return ["pure_gisin_luck", "강한 기신운", "천간·지지가 모두 확정 기구신에 해당"];
  if (stemType === "용신" && branchType === "기신") return ["mixed_yongsin_surface", "천간 용신·지지 기신(혼합)", "겉은 도움이나 기반 부담이 함께 오는 운"];
  if (stemType === "기신" && branchType === "용신") return ["mixed_gisin_surface", "천간 기신·지지 용신(혼합)", "초반 압박 뒤 기반 회복이 가능한 운"];
  if (stemType === "용신" || branchType === "용신") return ["partial_yongsin", "용신운(부분)", "천간·지지 중 일부가 확정 용희신에 해당"];
  if (stemType === "기신" || branchType === "기신") return ["partial_gisin", "기신운(부분)", "천간·지지 중 일부가 확정 기구신에 해당"];
  if (strong) return ["trigger_luck", "변동·트리거운", "용신·기신색은 옅으나 충·공망 자극이 있는 운"];
  return ["neutral_luck", "평운", "확정 용희기구 기준 작용이 뚜렷하지 않은 운"];
}

function coarse(code: string): string {
  if (code === "pure_yongsin_luck" || code === "partial_yongsin") return "용신운";
  if (code === "pure_gisin_luck" || code === "partial_gisin") return "기신운";
  if (code === "mixed_yongsin_surface" || code === "mixed_gisin_surface") return "혼합";
  return "평운";
}

function periodWeights(periodType: string | undefined): [number, number] {
  if (periodType === "daewoon") return [0.35, 0.65];
  if (periodType === "year") return [0.45, 0.55];
  return [0.4, 0.6];
}

export function applyCalibrationToLuckPillars(
  pillars: LuckPillar[],
  calibration: CalibrationResult | null,
): LuckPillar[] {
  const roles = roleSets(calibration);
  if (!roles) return pillars;
  return pillars.map((p) => {
    const stem = stemEffect(p.stem, roles.useful, roles.unfavorable);
    const branch = branchEffect(p.branch, p.branch_effect, roles.useful, roles.unfavorable);
    const [code, ko, summary] = label(stem.type, branch.type, Boolean(branch.is_void || branch.has_clash));
    const [stemWeight, branchWeight] = periodWeights(p.period_type);
    return {
      ...p,
      stem_effect: stem,
      branch_effect: branch,
      luck_score: Math.round((stemWeight * stem.score + branchWeight * branch.score) * 10000) / 10000,
      luck_label_code: code,
      luck_label: ko,
      luck_summary: `${summary} · 검증 확정 용희신 기준`,
      yongsin_alignment: coarse(code),
    };
  });
}

export function applyCalibrationToLuckCycles(
  cycles: LuckCycles | null,
  calibration: CalibrationResult | null,
): LuckCycles | null {
  const roles = roleSets(calibration);
  if (!cycles || !roles) return cycles;
  return {
    ...cycles,
    daewoon_table: cycles.daewoon_table.map((d) => {
      const [p] = applyCalibrationToLuckPillars([{ ...d, label: String(d.start_age), period_type: "daewoon", yongsin_alignment: d.yongsin_relation }], calibration);
      return {
        ...d,
        stem_effect: p.stem_effect,
        branch_effect: p.branch_effect,
        luck_score: p.luck_score,
        luck_label_code: p.luck_label_code,
        luck_label: p.luck_label,
        luck_summary: p.luck_summary,
        yongsin_relation: p.yongsin_alignment,
        sewoon: applyCalibrationToLuckPillars(d.sewoon ?? [], calibration),
      };
    }),
    yearly_luck: applyCalibrationToLuckPillars(cycles.yearly_luck, calibration),
    monthly_luck: applyCalibrationToLuckPillars(cycles.monthly_luck, calibration),
    daily_luck: applyCalibrationToLuckPillars(cycles.daily_luck, calibration),
  };
}
