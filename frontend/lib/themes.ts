// 테마사주 초기 4종(사용자 확정). 섹션 구성은 백엔드 build_section_plans가 고정하며,
// 여기서는 product_code·topic·동반자 필요 여부만 정의한다(docs/10).

import type { InlineBirthDTO, ReportSpec, SubjectRef, SubjectSummary } from "./types";

// 상대 선택 결과: 등록 동반자 / 즉석 입력(미등록). 관계운 optional·required에서 사용.
// relationType: 기준 사주와 상대의 관계(사용자 명시 선택) — 궁합(RP) 풀이 방향에 반영.
export type CompanionChoice =
  | { mode: "registered"; subject: SubjectSummary; relationType?: string | null }
  | { mode: "inline"; label: string; birth: InlineBirthDTO; relationType?: string | null };

// 상대와의 관계 선택지 — 백엔드 relationship_hints.RELATION_TYPES/RELATION_KO 미러.
// 관계에 따라 풀이 방향이 달라진다(연인/배우자/결혼예정/이혼예정/외도/상사·부하 등).
export const RELATION_OPTIONS: { value: string; label: string }[] = [
  { value: "crush", label: "썸·호감 단계" },
  { value: "romance", label: "연인" },
  { value: "fiance", label: "결혼 예정(약혼)" },
  { value: "spouse", label: "배우자(기혼)" },
  { value: "divorcing", label: "이혼 예정·진행 중" },
  { value: "affair", label: "외도 관계" },
  { value: "friend", label: "친구" },
  { value: "parent_child", label: "부모·자녀" },
  { value: "family", label: "가족·친척" },
  { value: "coworker", label: "직장 동료" },
  { value: "boss", label: "상사" },
  { value: "subordinate", label: "부하 직원" },
  { value: "business_partner", label: "사업 파트너" },
];

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
    desc: "타고난 기질부터 지나온 흐름, 앞으로의 큰 그림과 실천 조언까지 — 내 인생 전체를 한 권으로 읽어보세요.",
  },
  {
    slug: "year",
    title: "한해풀이",
    scope: "선택한 한 해",
    productCode: "RPT_YEAR",
    topic: null,
    companionMode: "none",
    desc: "선택한 해의 전체 흐름과 달별 좋은 시기·주의할 시기, 직업·재물·관계·건강 전망을 한 번에 확인해 보세요.",
    needsYear: true,
  },
  {
    slug: "relationship",
    title: "애정·관계운",
    scope: "향후 5년 · 연애 · 결혼 · 궁합",
    productCode: "RPT_FOCUS",
    topic: "relationship",
    companionMode: "optional",
    desc: "앞으로 5년, 인연이 열리는 시기와 관계의 흐름을 알려드려요. 마음에 둔 상대를 더하면 두 사람의 궁합과 잘 지내는 법까지 볼 수 있어요.",
  },
  {
    slug: "career",
    title: "직장운",
    scope: "향후 5년",
    productCode: "RPT_FOCUS",
    topic: "career",
    companionMode: "none",
    desc: "이직·승진·사업, 언제 움직이면 좋을까? 앞으로 5년의 직업 흐름과 변화가 열리는 시기, 시기별 행동 전략을 담아드려요.",
  },
  {
    slug: "wealth",
    title: "금전·횡재운",
    scope: "향후 5년",
    productCode: "RPT_FOCUS",
    topic: "wealth",
    companionMode: "none",
    desc: "돈이 들어오고 나가는 앞으로 5년의 흐름과 기회의 시기, 조심할 시기를 미리 짚어드려요.",
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

/** intent(집중) 풀이 기간 — 현재 달부터 향후 5년(현재월 ~ +5년 12월). 인생 전반이 아니라
 *  '지정기간 intent운'으로 운영(2026-06-16 사용자 확정). 백엔드 예측창 필터와 정합. */
function currentForwardPeriod(): { start: string; end: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  return { start: `${y}-${m}`, end: `${y + 5}-12` };
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
    // 관계(사용자 명시 > 등록 동반자 저장값) — 궁합(RP) 풀이 방향에 반영.
    const relation =
      companion.relationType ??
      (companion.mode === "registered" ? companion.subject.relation_to_user : null) ??
      null;
    if (companion.mode === "registered") {
      subjects.push({
        kind: "companion",
        label: companion.subject.label,
        companion_id: companion.subject.subject_id,
        relation_type: relation,
      });
    } else {
      subjects.push({
        kind: "inline_temp",
        label: companion.label,
        inline_birth: companion.birth,
        relation_type: relation,
      });
    }
  }
  // 기간: 한해풀이=선택 연도 / 집중(intent)=현재~+5년 / 총운=인생 전반.
  const period =
    theme.needsYear && year
      ? calendarYearPeriod(year)
      : theme.productCode === "RPT_FOCUS"
        ? currentForwardPeriod()
        : lifetimePeriod(primary.birth.birth_date);
  return {
    product_code: theme.productCode,
    subjects,
    topic: theme.topic,
    period,
    language: "ko",
  };
}
