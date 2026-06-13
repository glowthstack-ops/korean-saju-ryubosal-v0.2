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
  it("exposes the four initial themes", () => {
    expect(THEMES.map((t) => t.slug)).toEqual(["full", "compatibility", "career", "wealth"]);
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

  it("career → RPT_FOCUS topic career", () => {
    const spec = buildReportSpec(themeBySlug("career")!, subject("a", "본인"));
    expect(spec.product_code).toBe("RPT_FOCUS");
    expect(spec.topic).toBe("career");
  });

  it("compatibility includes companion subject ref", () => {
    const spec = buildReportSpec(
      themeBySlug("compatibility")!,
      subject("a", "본인"),
      subject("b", "상대"),
    );
    expect(spec.topic).toBe("compatibility");
    expect(spec.subjects).toHaveLength(2);
    expect(spec.subjects[1]).toMatchObject({ kind: "companion", companion_id: "b" });
  });

  it("compatibility without companion omits the second ref", () => {
    const spec = buildReportSpec(themeBySlug("compatibility")!, subject("a", "본인"));
    expect(spec.subjects).toHaveLength(1);
  });
});
