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

// CAL-P0 — trait_probe FE↔BE enum 계약(백엔드 TRAIT_RESPONSES·TRAIT_PROBE_OPTIONS 미러).
// 값·라벨·순서가 어긋나면 응답이 unclear로 강등되므로 계약을 고정한다.
import { TRAIT_OPTIONS } from "@/lib/calibration";

describe("trait probe option contract (CAL-P0)", () => {
  it("mirrors backend TRAIT_RESPONSES values in order", () => {
    expect(TRAIT_OPTIONS.map((o) => o.value)).toEqual([
      "agreed",
      "mixed",
      "denied",
      "unclear",
    ]);
  });
  it("mirrors backend TRAIT_PROBE_OPTIONS labels in order", () => {
    expect(TRAIT_OPTIONS.map((o) => o.label)).toEqual([
      "대체로 그렇다",
      "상황에 따라 다르다",
      "그렇지 않다",
      "잘 모르겠다",
    ]);
  });
});

// CAL-P1-c — pair probe FE↔BE enum 계약(STATIC=trait 4지 재사용, TRANSIT=P1-b 확정 라벨).
import { STATIC_DEFICIENCY_OPTIONS, TRANSIT_OPTIONS } from "@/lib/calibration";

describe("deficiency pair option contract (CAL-P1-c)", () => {
  it("static options reuse trait responses in order", () => {
    expect(STATIC_DEFICIENCY_OPTIONS.map((o) => o.value)).toEqual([
      "agreed",
      "mixed",
      "denied",
      "unclear",
    ]);
  });
  it("transit options mirror backend TRANSIT_ACTIVATION_RESPONSES/labels", () => {
    expect(TRANSIT_OPTIONS.map((o) => o.value)).toEqual([
      "strong",
      "partial",
      "none",
      "unknown",
    ]);
    expect(TRANSIT_OPTIONS.map((o) => o.label)).toEqual([
      "강하게 있었다",
      "일부 있었다",
      "거의 없었다",
      "잘 모르겠다",
    ]);
  });
});

// CAL-QA — 무신호 응답 옵션 계약(docs/14 §8). 용신 검증 이벤트만 not_occurred 노출,
// 현실 캘리브레이션(발생 체크 후 결과)에는 미노출. unknown과 값 혼합 금지.
import {
  DOMAIN_OPTIONS,
  EVENT_OPTIONS,
  YONGSIN_EVENT_OPTIONS,
  normalizeEventRating,
} from "@/lib/calibration";

describe("no-signal rating contract (CAL-QA)", () => {
  it("domain options expose no_domain_activity distinct from unknown", () => {
    const values = DOMAIN_OPTIONS.map((o) => o.value);
    expect(values).toContain("no_domain_activity");
    expect(values).toContain("unknown");
    expect(
      DOMAIN_OPTIONS.find((o) => o.value === "no_domain_activity")?.label,
    ).toBe("특별한 일 없었음");
  });
  it("yongsin event options expose not_occurred; reality event options do not", () => {
    expect(YONGSIN_EVENT_OPTIONS.map((o) => o.value)).toContain("not_occurred");
    expect(EVENT_OPTIONS.map((o) => o.value)).not.toContain("not_occurred");
  });
  it("normalize keeps no-signal values and maps legacy na to unknown", () => {
    expect(normalizeEventRating("not_occurred")).toBe("not_occurred");
    expect(normalizeEventRating("no_domain_activity")).toBe("no_domain_activity");
    expect(normalizeEventRating("na")).toBe("unknown");
  });
});
