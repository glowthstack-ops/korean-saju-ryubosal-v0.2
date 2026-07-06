import { describe, expect, it } from "vitest";
import { buildReportSpec, THEMES, themeBySlug } from "@/lib/themes";
import type { SubjectSummary } from "@/lib/types";

function subject(id: string, label: string, birth = "1988-09-09"): SubjectSummary {
  return {
    subject_id: id,
    owner_id: "u",
    kind: "self",
    label,
    aliases: [],
    relation_to_user: null,
    birth: { calendar_type: "solar", birth_date: birth, birth_place_name: "서울", gender: "male" },
    gender: "male",
    is_minor: false,
    subscribed: false,
    yongsin_registered: false,
    mulsang_registered: false,
  };
}

describe("themes", () => {
  it("exposes the five themes", () => {
    expect(THEMES.map((t) => t.slug)).toEqual([
      "full",
      "year",
      "relationship",
      "career",
      "wealth",
    ]);
    expect(themeBySlug("career")?.productCode).toBe("RPT_FOCUS");
    expect(themeBySlug("full")?.productCode).toBe("RPT_FULL");
    expect(themeBySlug("nope")).toBeUndefined();
  });

  it("full → RPT_FULL with no topic, lifetime period from birth year", () => {
    const spec = buildReportSpec(themeBySlug("full")!, subject("a", "본인", "1990-03-03"));
    expect(spec.product_code).toBe("RPT_FULL");
    expect(spec.topic).toBeNull();
    expect(spec.period).toEqual({ start: "1990-01", end: "2080-12" });
    expect(spec.subjects).toHaveLength(1);
  });

  it("career → RPT_FOCUS topic career, period = 현재월~+5년(인생 전반 아님)", () => {
    const spec = buildReportSpec(themeBySlug("career")!, subject("a", "본인"));
    expect(spec.product_code).toBe("RPT_FOCUS");
    expect(spec.topic).toBe("career");
    // 집중(intent) 풀이는 현재 달부터 향후 5년 — 출생년 기반 인생 전반과 무관.
    const now = new Date();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    expect(spec.period).toEqual({
      start: `${now.getFullYear()}-${m}`,
      end: `${now.getFullYear() + 5}-12`,
    });
  });

  it("relationship(optional) includes registered companion ref when given", () => {
    const spec = buildReportSpec(themeBySlug("relationship")!, subject("a", "본인"), {
      mode: "registered",
      subject: subject("b", "상대"),
    });
    expect(spec.topic).toBe("relationship");
    expect(spec.subjects).toHaveLength(2);
    expect(spec.subjects[1]).toMatchObject({ kind: "companion", companion_id: "b" });
  });

  it("relationship with inline partner emits inline_temp + inline_birth", () => {
    const spec = buildReportSpec(themeBySlug("relationship")!, subject("a", "본인"), {
      mode: "inline",
      label: "상대",
      birth: { date: "1990-05-05", time: "10:30", calendar_type: "solar", gender: "F" },
    });
    expect(spec.subjects).toHaveLength(2);
    expect(spec.subjects[1]).toMatchObject({
      kind: "inline_temp",
      label: "상대",
      inline_birth: { date: "1990-05-05", gender: "F" },
    });
  });

  it("relationship without companion omits the second ref (단독 모드)", () => {
    const spec = buildReportSpec(themeBySlug("relationship")!, subject("a", "본인"));
    expect(spec.subjects).toHaveLength(1);
  });
});

// 상대와의 관계 → ReportSpec 전달(2026-07-03) — 명시 선택 > 등록 저장값 > 미지정(null).
import { RELATION_OPTIONS } from "@/lib/themes";

describe("relation type in report spec", () => {
  const theme = themeBySlug("relationship")!;
  const primary = subject("s1", "본인");
  it("explicit relation flows into companion subject", () => {
    const spec = buildReportSpec(theme, primary, {
      mode: "inline", label: "상대",
      birth: { date: "1985-03-08" }, relationType: "boss",
    });
    expect(spec.subjects[1].relation_type).toBe("boss");
  });
  it("falls back to registered relation_to_user when not chosen", () => {
    const comp = { ...subject("s2", "짝꿍"), relation_to_user: "spouse" };
    const spec = buildReportSpec(theme, primary, { mode: "registered", subject: comp });
    expect(spec.subjects[1].relation_type).toBe("spouse");
  });
  it("stays null when nothing provided (neutral tone)", () => {
    const spec = buildReportSpec(theme, primary, {
      mode: "inline", label: "상대", birth: { date: "1985-03-08" },
    });
    expect(spec.subjects[1].relation_type ?? null).toBeNull();
  });
  it("relation options mirror backend relation types", () => {
    expect(RELATION_OPTIONS.map((r) => r.value)).toEqual([
      "crush", "romance", "fiance", "spouse", "divorcing", "affair",
      "friend", "parent_child", "family", "coworker", "boss",
      "subordinate", "business_partner",
    ]);
  });
});
