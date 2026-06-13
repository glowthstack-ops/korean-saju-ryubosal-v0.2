// 테마사주 초기 4종(사용자 확정). 섹션 구성은 백엔드 build_section_plans가 고정하며,
// 여기서는 product_code·topic·동반자 필요 여부만 정의한다(docs/10).

import type { ReportSpec, SubjectRef, SubjectSummary } from "./types";

export interface Theme {
  slug: string; // 라우트 파라미터
  title: string;
  scope: string; // 표시용 부제
  productCode: "RPT_FULL" | "RPT_FOCUS";
  topic: string | null;
  requireCompanion: boolean;
  pages: string; // 분량 안내(docs/10)
  desc: string;
}

export const THEMES: Theme[] = [
  {
    slug: "full",
    title: "총운",
    scope: "인생 전반",
    productCode: "RPT_FULL",
    topic: null,
    requireCompanion: false,
    pages: "약 50쪽",
    desc: "명식·과거·현재·미래·조언까지 22개 장으로 엮은 종합 풀이.",
  },
  {
    slug: "compatibility",
    title: "궁합",
    scope: "연애 · 결혼",
    productCode: "RPT_FOCUS",
    topic: "compatibility",
    requireCompanion: true,
    pages: "약 15쪽",
    desc: "두 명식의 구조 대조와 관계 운영 시나리오.",
  },
  {
    slug: "career",
    title: "직장운",
    scope: "인생 전반",
    productCode: "RPT_FOCUS",
    topic: "career",
    requireCompanion: false,
    pages: "약 15쪽",
    desc: "직업·사업 흐름과 변화 시기, 행동 전략.",
  },
  {
    slug: "wealth",
    title: "금전·횡재운",
    scope: "인생 전반",
    productCode: "RPT_FOCUS",
    topic: "wealth",
    requireCompanion: false,
    pages: "약 15쪽",
    desc: "재물 흐름과 기회·리스크 시기.",
  },
];

export function themeBySlug(slug: string): Theme | undefined {
  return THEMES.find((t) => t.slug === slug);
}

/** 인생 전반 기간 — 출생년 ~ +90년(엔진이 가용 운 데이터로 클립). */
function lifetimePeriod(birthDate: string): { start: string; end: string } {
  const year = Number(birthDate.slice(0, 4)) || 1990;
  return { start: `${year}-01`, end: `${year + 90}-12` };
}

/** 테마 + 선택 사주(+동반자) → ReportSpec. */
export function buildReportSpec(
  theme: Theme,
  primary: SubjectSummary,
  companion?: SubjectSummary,
): ReportSpec {
  const subjects: SubjectRef[] = [{ kind: "self", label: primary.label }];
  if (theme.requireCompanion && companion) {
    subjects.push({
      kind: "companion",
      label: companion.label,
      companion_id: companion.subject_id,
    });
  }
  return {
    product_code: theme.productCode,
    subjects,
    topic: theme.topic,
    period: lifetimePeriod(primary.birth.birth_date),
    language: "ko",
  };
}
