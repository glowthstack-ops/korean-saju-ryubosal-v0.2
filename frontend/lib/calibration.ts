// 캘리브레이션 해상도(docs/14) 공용 enum·매핑·정규화. 용신·현실 문항이 공유한다.
// 내부 저장값은 항상 ExperienceRating — UI 노출 라벨과 분리한다(레거시 positive/negative/na 호환).

export type ExperienceRating =
  | "very_positive"
  | "positive"
  | "neutral"
  | "mixed"
  | "negative"
  | "very_negative"
  | "unknown";

// 4개 도메인만 노출(확장 도메인은 후속).
export const CALIB_DOMAINS: { key: string; label: string }[] = [
  { key: "career", label: "직업/학업" },
  { key: "money", label: "재물/소득" },
  { key: "relationship", label: "관계/연애/가족" },
  { key: "health", label: "건강/컨디션" },
];

// 연도/문항 전체 체감 — 7상태.
export const OVERALL_OPTIONS: { value: ExperienceRating; label: string }[] = [
  { value: "very_positive", label: "매우 좋았다" },
  { value: "positive", label: "대체로 좋았다" },
  { value: "neutral", label: "평이했다" },
  { value: "mixed", label: "좋고 나쁨이 섞였다" },
  { value: "negative", label: "대체로 힘들었다" },
  { value: "very_negative", label: "매우 힘들었다" },
  { value: "unknown", label: "잘 모르겠다" },
];

// 영역별 체감 — 5상태(매우±는 제외해 가볍게).
export const DOMAIN_OPTIONS: { value: ExperienceRating; label: string }[] = [
  { value: "positive", label: "좋음" },
  { value: "neutral", label: "보통" },
  { value: "mixed", label: "반반" },
  { value: "negative", label: "힘듦" },
  { value: "unknown", label: "모름" },
];

// 사건별 결과 — 4상태.
export const EVENT_OPTIONS: { value: ExperienceRating; label: string }[] = [
  { value: "positive", label: "좋았다" },
  { value: "negative", label: "힘들었다" },
  { value: "mixed", label: "좋고 나쁨이 섞였다" },
  { value: "unknown", label: "아직 판단 어렵다" },
];

// 강도 — 보조값(필수 아님).
export const INTENSITY_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "약함" },
  { value: 2, label: "보통" },
  { value: 3, label: "강함" },
];

// 캘리브레이션 답변 상태맵(문항 id → 응답). 용신 CalibrationPanel·manse 복원이 공유한다.
export type AnswerMap = Record<
  string,
  {
    rating: string; // 전체 체감(ExperienceRating 7상태)
    events: string[]; // 레거시 영향 영역 multi-select
    event_ratings?: Record<string, string>; // 사건별 결과(ExperienceRating)
    domain_ratings?: Record<string, string>; // 영역별 체감(domain → ExperienceRating)
    event_intensity?: Record<string, number>; // 사건별 강도(1~3, 선택)
  }
>;

const _VALID: ReadonlySet<string> = new Set([
  "very_positive", "positive", "neutral", "mixed", "negative", "very_negative", "unknown",
]);

/** 레거시/저장값 → ExperienceRating. 'na'(해당없음/모름)→'unknown', 미상은 undefined. */
export function normalizeEventRating(v: string | undefined | null): ExperienceRating | undefined {
  if (!v) return undefined;
  if (v === "na") return "unknown";
  return _VALID.has(v) ? (v as ExperienceRating) : undefined;
}
