// 명식별 '나와의 관계' — 서버 키(RELATION_TO_USER_KEYS, 17종)와 한글 라벨(2026-10-14 데굴님 승인).
// 키는 백엔드 별칭 해소 동의어표와 같아 "남편"·"엄마" 지칭이 등록 동반자로 바로 해소된다.

import type { SubjectSummary } from "@/lib/types";

export type RelationKey =
  | "self" | "spouse" | "husband" | "wife" | "father" | "mother" | "child" | "son" | "daughter"
  | "brother" | "sister" | "lover" | "friend" | "coworker" | "boss" | "business_partner" | "other";

export const RELATION_OPTIONS: readonly { key: RelationKey; label: string }[] = [
  { key: "self", label: "본인" },
  { key: "spouse", label: "배우자" },
  { key: "husband", label: "남편" },
  { key: "wife", label: "아내" },
  { key: "father", label: "아버지" },
  { key: "mother", label: "어머니" },
  { key: "child", label: "자녀" },
  { key: "son", label: "아들" },
  { key: "daughter", label: "딸" },
  { key: "brother", label: "형제" },
  { key: "sister", label: "자매" },
  { key: "lover", label: "연인" },
  { key: "friend", label: "친구" },
  { key: "coworker", label: "동료" },
  { key: "boss", label: "상사" },
  { key: "business_partner", label: "동업자" },
  { key: "other", label: "기타" },
];

const LABEL_BY_KEY: Record<string, string> = Object.fromEntries(
  RELATION_OPTIONS.map((o) => [o.key, o.label]),
);

/** 관계 키 → 한글. 미설정(null)이나 모르는 값은 "관계 미설정" — kind 로 '본인'을 추정하지 않는다. */
export function relationLabel(s: Pick<SubjectSummary, "relation_to_user">): string {
  return (s.relation_to_user && LABEL_BY_KEY[s.relation_to_user]) || "관계 미설정";
}

export function hasRelation(s: Pick<SubjectSummary, "relation_to_user">): boolean {
  return !!(s.relation_to_user && LABEL_BY_KEY[s.relation_to_user]);
}

/** 관계 → kind(서버도 같은 규칙으로 파생한다). 미설정이면 기존 kind 유지. */
export function kindForRelation(
  relation: string | null | undefined,
  fallback: "self" | "companion",
): "self" | "companion" {
  if (!relation) return fallback;
  return relation === "self" ? "self" : "companion";
}
