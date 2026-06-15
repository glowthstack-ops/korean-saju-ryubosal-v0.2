// 테마사주 초기 4종(사용자 확정). 섹션 구성은 백엔드 build_section_plans가 고정하며,
// 여기서는 product_code·topic·동반자 필요 여부만 정의한다(docs/10).

import type { InlineBirthDTO, ReportSpec, SubjectRef, SubjectSummary } from "./types";

// 상대 선택 결과: 등록 동반자 / 즉석 입력(미등록). 관계운 optional·required에서 사용.
export type CompanionChoice =
  | { mode: "registered"; subject: SubjectSummary }
  | { mode: "inline"; label: string; birth: InlineBirthDTO };

// 동반자(상대) 선택 정책: none=단독 전용 / optional=상대 추가 선택 가능(내 명식만도 가능) /
// required=상대 필수(두 사람 분석). 관계·애정운은 optional — 상대 등록 시 궁합 모드(RP-*),
// 미선택 시 단독 모드(R-*)로 백엔드가 분기한다.
export type CompanionMode = "none" | "optional" | "required";

export interface Theme {
  slug: string; // 라우트 파라미터
  title: string;
  scope: string; // 표시용 부제
  productCode: "RPT_FULL" | "RPT_FOCUS" | "RPT_YEAR";
  topic: string | null;
  companionMode: CompanionMode;
  pages: string; // 분량 안내(docs/10)
  desc: string;
  needsYear?: boolean; // 진입 시 년도 선택(한해풀이) — period를 그 해 1~12월로 고정
}

export const THEMES: Theme[] = [
  {
    slug: "full",
    title: "총운",
    scope: "인생 전반",
    productCode: "RPT_FULL",
    topic: null,
    companionMode: "none",
    pages: "약 50쪽",
    desc: "명식·과거·현재·미래·조언까지 22개 장으로 엮은 종합 풀이.",
  },
  {
    slug: "year",
    title: "한해풀이",
    scope: "선택한 한 해",
    productCode: "RPT_YEAR",
    topic: null,
    companionMode: "none",
    pages: "약 14~18쪽",
    desc: "올해(또는 선택한 해) 1년의 세운·월별 흐름과 도메인별 전망을 압축한 풀이.",
    needsYear: true,
  },
  {
    slug: "relationship",
    title: "애정·관계운",
    scope: "연애 · 결혼 · 궁합",
    productCode: "RPT_FOCUS",
    topic: "relationship",
    companionMode: "optional",
    pages: "약 15쪽",
    desc: "내 명식만으로 보거나, 상대를 더하면 두 사람의 궁합·극복 전략까지.",
  },
  {
    slug: "career",
    title: "직장운",
    scope: "인생 전반",
    productCode: "RPT_FOCUS",
    topic: "career",
    companionMode: "none",
    pages: "약 15쪽",
    desc: "직업·사업 흐름과 변화 시기, 행동 전략.",
  },
  {
    slug: "wealth",
    title: "금전·횡재운",
    scope: "인생 전반",
    productCode: "RPT_FOCUS",
    topic: "wealth",
    companionMode: "none",
    pages: "약 15쪽",
    desc: "재물 흐름과 기회·리스크 시기.",
  },
];

export function themeBySlug(slug: string): Theme | undefined {
  return THEMES.find((t) => t.slug === slug);
}

/** product_code+topic → 표시용 테마 이름(내역 등). 매칭 없으면 코드 그대로. */
export function themeLabel(productCode: string, topic: string | null): string {
  if (productCode === "RPT_FULL") return "총운";
  if (topic === "compatibility") return "궁합"; // 레거시 저장분(현 애정·관계운으로 통합)
  const t = THEMES.find((x) => x.productCode === productCode && x.topic === topic);
  return t ? t.title : (topic ?? productCode);
}

/** 인생 전반 기간 — 출생년 ~ +90년(엔진이 가용 운 데이터로 클립). */
function lifetimePeriod(birthDate: string): { start: string; end: string } {
  const year = Number(birthDate.slice(0, 4)) || 1990;
  return { start: `${year}-01`, end: `${year + 90}-12` };
}

/** 한해풀이 기간 — 선택한 해의 달력연도 1~12월(세운 기준은 엔진 내부에서 입춘 처리). */
function calendarYearPeriod(year: number): { start: string; end: string } {
  return { start: `${year}-01`, end: `${year}-12` };
}

/** 테마 + 선택 사주(+상대) → ReportSpec. 상대는 companionMode!=none이고 선택됐을 때만 포함.
 *  상대는 등록 동반자(companion_id) 또는 즉석 입력(inline_birth) 둘 다 가능.
 *  needsYear 테마(한해풀이)는 year를 받아 그 해 1~12월로 기간을 고정한다. */
export function buildReportSpec(
  theme: Theme,
  primary: SubjectSummary,
  companion?: CompanionChoice,
  year?: number,
): ReportSpec {
  const subjects: SubjectRef[] = [{ kind: "self", label: primary.label }];
  if (theme.companionMode !== "none" && companion) {
    if (companion.mode === "registered") {
      subjects.push({
        kind: "companion",
        label: companion.subject.label,
        companion_id: companion.subject.subject_id,
      });
    } else {
      subjects.push({
        kind: "inline_temp",
        label: companion.label,
        inline_birth: companion.birth,
      });
    }
  }
  const period =
    theme.needsYear && year
      ? calendarYearPeriod(year)
      : lifetimePeriod(primary.birth.birth_date);
  return {
    product_code: theme.productCode,
    subjects,
    topic: theme.topic,
    period,
    language: "ko",
  };
}
