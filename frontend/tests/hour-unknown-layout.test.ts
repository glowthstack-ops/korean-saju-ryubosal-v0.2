// 시주 미상 화면(2026-11-28 데굴님 화면 지적) — 안내 층이 영역 밖으로 넘치지 않는 구조와 검증 질문 숨김.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CalibrationPanel } from "@/components/manse/CalibrationPanel";
import { GhostInline, GhostOverlay } from "@/components/manse/HourUnknown";
import type { ManseResult, Profile } from "@/lib/types";

const result = (hour: unknown): ManseResult =>
  ({ pillars: { hour }, calibration: { questions: [] } }) as unknown as ManseResult;
const panel = (r: ManseResult, registered = false) =>
  renderToStaticMarkup(
    createElement(CalibrationPanel, {
      result: r, profile: {} as Profile, referenceDate: "2026-11-28", onResult: () => {}, registered,
    }),
  );

describe("고스트 레이어", () => {
  it("두 층을 같은 격자 칸에 쌓는다 — 절대 배치로 덮지 않는다", () => {
    const html = renderToStaticMarkup(
      createElement(GhostOverlay, { label: "미확정 · 시주 미상", sub: "안내 문구", children: "값" }),
    );
    expect(html).toContain('class="grid ');
    expect(html.match(/col-start-1 row-start-1/g)?.length).toBe(2);
    expect(html).not.toContain("absolute");
    expect(html).toContain("안내 문구");
  });

  it("한 줄 값용은 값만 흐리게 두고 안내 문구를 싣지 않는다", () => {
    const html = renderToStaticMarkup(
      createElement(GhostInline, { label: "미확정 · 시주 미상", children: "신약" }),
    );
    expect(html).toContain("blur-[3px]");
    expect(html).toContain('aria-label="미확정 · 시주 미상"');
    // 반례: 라벨이 화면 글자로 나오지 않는다(값 옆 뱃지가 맡는다).
    expect(html.replace(/aria-label="[^"]*"/g, "")).not.toContain("미확정");
  });
});

describe("용신 검증 질문", () => {
  it("시주 미상이면 질문을 열지 않고 안내만 보여 준다", () => {
    const html = panel(result(null));
    expect(html).toContain("출생시간이 없으면 용신 검증 질문을 열지 않아요");
    expect(html).not.toContain("<button");
  });

  it("시주 미상이고 등록된 용신이 있어도 다시 검증 버튼을 내지 않는다", () => {
    const html = panel(result(null), true);
    expect(html).toContain("등록된 용신이 있어요");
    expect(html).not.toContain("다시 검증</button>");
  });

  it("반례: 시주가 있으면 종전 분기를 그대로 탄다", () => {
    expect(panel(result({ stem: "丙", branch: "午" }))).toContain("용신 검증 질문을");
    expect(panel(result({ stem: "丙", branch: "午" }))).not.toContain("출생시간이 없으면");
    expect(panel(result({ stem: "丙", branch: "午" }), true)).toContain("다시 검증</button>");
  });
});
