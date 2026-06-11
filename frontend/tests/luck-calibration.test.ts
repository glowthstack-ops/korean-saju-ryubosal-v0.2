import { describe, expect, it } from "vitest";
import { applyCalibrationToLuckPillars } from "@/lib/luck-calibration";
import type { CalibrationResult, LuckPillar } from "@/lib/types";

const CAL: CalibrationResult = {
  status: "calibrated",
  final_yongsin: "火",
  final_heesin: "木",
  final_gisin: "金",
  final_gusin: "土",
  confidence: 0.8,
  evidence_count: 4,
  match_rate: 0.8,
  selected_model: "johu",
  explanation: [],
};

describe("luck calibration overlay", () => {
  it("relabels luck by calibrated useful and unfavorable elements", () => {
    const luck: LuckPillar = {
      label: "2018-01",
      period_type: "month",
      ganji: "甲午",
      stem: "甲",
      branch: "午",
      stem_ten_god: "정재",
      branch_ten_god: "편관",
      yongsin_alignment: "평운",
      stem_effect: { element: "木", type: "한신", score: 0 },
      branch_effect: { element: "火", type: "한신", score: 0 },
    };

    const [adjusted] = applyCalibrationToLuckPillars([luck], CAL);

    expect(adjusted.stem_effect?.type).toBe("용신");
    expect(adjusted.branch_effect?.type).toBe("용신");
    expect(adjusted.luck_label_code).toBe("pure_yongsin_luck");
    expect(adjusted.yongsin_alignment).toBe("용신운");
    expect(adjusted.luck_summary).toContain("검증 확정");
  });
});
