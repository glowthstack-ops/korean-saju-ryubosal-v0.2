// 민속 흉방 24방위 나침반(docs/19 §5-6, 2026-11-24) — 칠해지는 칸은 엔진 값(mountains)만 따른다.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FolkCompass, folkDegreeLabel } from "@/components/manse/FolkCompass";
import type { FolkTabooHit } from "@/lib/types";

const hit = (over: Partial<FolkTabooHit>): FolkTabooHit => ({
  key: "samsal", name_ko: "삼살방", direction: "북", branches: [], reason_ko: "", period: "year",
  basis_ko: "2026 丙午년", ...over,
});

// 2026 丙午년 엔진 값 그대로.
const SAMSAL = hit({
  mountains: ["亥", "壬", "子", "癸", "丑"], degree_from: 322.5, degree_to: 37.5,
  range_ko: "북 전체(壬·子·癸)와 북서쪽 亥 구간·북동쪽 丑 구간",
});
const DAEJANGGUN = hit({
  key: "daejanggun", name_ko: "대장군방", direction: "동", mountains: ["甲", "卯", "乙"],
  degree_from: 67.5, degree_to: 112.5, range_ko: "동 한 칸(甲·卯·乙, 卯 중심)",
});
const SEPA = hit({
  key: "sepa", name_ko: "세파방", tier: "GROUND", mountains: ["子"], degree_from: 352.5, degree_to: 7.5,
  range_ko: "정북 子 구간",
});

// 칸 글자 → 그 칸의 채움색(글자 바로 앞 path 의 fill).
function fills(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of html.matchAll(/<g><path d="[^"]+" fill="(#[0-9a-f]+)"[^>]*><\/path><text[^>]*>(.)<\/text><\/g>/g)) {
    out[m[2]] = m[1];
  }
  return out;
}

describe("folkDegreeLabel", () => {
  it("정북을 넘는 구간은 시작 각이 더 크다", () => {
    expect(folkDegreeLabel(SAMSAL)).toBe("322.5°~37.5°");
    expect(folkDegreeLabel(hit({ degree_from: 90, degree_to: 105 }))).toBe("90°~105°");
  });
  it("범위가 없는 흉방(손방)은 빈 문자열", () => {
    expect(folkDegreeLabel(hit({ key: "son", degree_from: null, degree_to: null }))).toBe("");
    expect(folkDegreeLabel(hit({ key: "son" }))).toBe("");
  });
});

describe("FolkCompass", () => {
  const html = renderToStaticMarkup(createElement(FolkCompass, { move: [SAMSAL, DAEJANGGUN], ground: [SEPA] }));
  const f = fills(html);

  it("24칸을 모두 그리고 엔진이 준 칸만 칠한다", () => {
    expect(Object.keys(f)).toHaveLength(24);
    for (const m of ["亥", "壬", "子", "癸", "丑"]) expect(f[m]).toBe("#fecdd3");
    for (const m of ["甲", "卯", "乙"]) expect(f[m]).toBe("#fde68a");
    // 반례: 같은 북서·북동·동쪽 사분면이라도 범위 밖 칸은 칠하지 않는다.
    for (const m of ["戌", "乾", "艮", "寅", "辰", "午"]) expect(f[m]).toBe("#fafaf9");
  });

  it("참고층은 채우지 않고 점선 테두리 한 칸만 겹쳐 그린다", () => {
    expect(html.match(/stroke-dasharray="3 2"/g)).toHaveLength(1);
    expect(f["子"]).toBe("#fecdd3"); // 이사 판정층 색을 가리지 않는다
    expect(html).toContain("태세·세파(참고)");
    expect(html).not.toContain("두 종 겹침");
  });

  it("이사 판정층 두 종이 같은 칸에 겹치면 겹침 색과 범례를 쓴다(2022 壬寅 북)", () => {
    const north = hit({ key: "daejanggun", name_ko: "대장군방", mountains: ["壬", "子", "癸"] });
    const h2 = renderToStaticMarkup(createElement(FolkCompass, { move: [SAMSAL, north], ground: [] }));
    const f2 = fills(h2);
    for (const m of ["壬", "子", "癸"]) expect(f2[m]).toBe("#fb7185");
    for (const m of ["亥", "丑"]) expect(f2[m]).toBe("#fecdd3");
    expect(h2).toContain("두 종 겹침");
    expect(h2).not.toContain("태세·세파(참고)");
  });
});
