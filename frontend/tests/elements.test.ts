import { describe, expect, it } from "vitest";
import { elementLabel, elementStyle, ganjiKo } from "@/lib/elements";
import { searchLocations } from "@/lib/locations";

describe("elements util", () => {
  it("converts ganji hanja to korean", () => {
    expect(ganjiKo("庚申")).toBe("경신");
    expect(ganjiKo("己亥")).toBe("기해");
  });
  it("labels elements with korean reading", () => {
    expect(elementLabel("木")).toBe("木(목)");
    expect(elementLabel(null)).toBe("-");
  });
  it("returns a style class per element", () => {
    expect(elementStyle("水")).toContain("bg-");
    expect(elementStyle("unknown")).toContain("bg-");
  });
});

describe("location search", () => {
  it("filters by name/region", () => {
    expect(searchLocations("서울").some((l) => l.name === "서울")).toBe(true);
    expect(searchLocations("일본").every((l) => l.region === "일본")).toBe(true);
    expect(searchLocations("").length).toBeGreaterThan(5);
  });
});
