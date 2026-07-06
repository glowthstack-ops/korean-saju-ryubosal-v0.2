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

// CAL-QA(docs/14 §8) — 무신호 상태. '기억 안 남(unknown)'과 구분되는 실제 무신호 값.
// 채점·분모 제외(백엔드 보장), 응답 blob에는 값 그대로 축적된다.
export type NoSignalRating = "no_domain_activity" | "not_occurred";
export type CalibrationRating = ExperienceRating | NoSignalRating;

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

// 영역별 체감 — 5상태 + 무신호(CAL-QA). '특별한 일 없었음'은 모름(기억 안 남)과 구분되는
// 비활성 신호로 저장되며 채점에는 들어가지 않는다.
export const DOMAIN_OPTIONS: { value: CalibrationRating; label: string }[] = [
  { value: "positive", label: "좋음" },
  { value: "neutral", label: "보통" },
  { value: "mixed", label: "반반" },
  { value: "negative", label: "힘듦" },
  { value: "no_domain_activity", label: "특별한 일 없었음" },
  { value: "unknown", label: "모름" },
];

// 사건별 결과 — 4상태(발생을 전제한 결과 평가 — 현실 캘리브레이션의 '발생 체크 후 결과'용).
export const EVENT_OPTIONS: { value: CalibrationRating; label: string }[] = [
  { value: "positive", label: "좋았다" },
  { value: "negative", label: "힘들었다" },
  { value: "mixed", label: "좋고 나쁨이 섞였다" },
  { value: "unknown", label: "아직 판단 어렵다" },
];

// 용신 검증 이벤트 질문 전용(CAL-QA) — 발생 체크 단계가 없으므로 '그런 일 없었다'
// (not_occurred, 발생 반증)를 선택지로 노출한다. 채점 제외·축적만(docs/14 §8, 승격은
// CAL-P2 판단). 현실 캘리브레이션(StepRealityCalibration)은 발생 체크가 따로 있어 미사용.
export const YONGSIN_EVENT_OPTIONS: { value: CalibrationRating; label: string }[] = [
  { value: "positive", label: "좋았다" },
  { value: "negative", label: "힘들었다" },
  { value: "mixed", label: "좋고 나쁨이 섞였다" },
  { value: "not_occurred", label: "그런 일 없었다" },
  { value: "unknown", label: "아직 판단 어렵다" },
];

// 강도 — 보조값(필수 아님).
export const INTENSITY_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "약함" },
  { value: 2, label: "보통" },
  { value: 3, label: "강함" },
];

// trait_probe(성향 확인, CAL-P0) — 백엔드 TRAIT_PROBE_OPTIONS↔TRAIT_RESPONSES 미러.
// 채점 비반영(표현 보정용) — 용신·점수를 바꾸지 않는다.
export const TRAIT_OPTIONS: { value: string; label: string }[] = [
  { value: "agreed", label: "대체로 그렇다" },
  { value: "mixed", label: "상황에 따라 다르다" },
  { value: "denied", label: "그렇지 않다" },
  { value: "unclear", label: "잘 모르겠다" },
];

// static_deficiency_probe(평소 체감, CAL-P1) — 응답 체계는 trait와 동일 4지.
export const STATIC_DEFICIENCY_OPTIONS = TRAIT_OPTIONS;

// transit_activation_probe(해당 시기 체감, CAL-P1) — 백엔드 TRANSIT_PROBE_OPTIONS↔
// TRANSIT_ACTIVATION_RESPONSES 미러. 채점 비반영.
export const TRANSIT_OPTIONS: { value: string; label: string }[] = [
  { value: "strong", label: "강하게 있었다" },
  { value: "partial", label: "일부 있었다" },
  { value: "none", label: "거의 없었다" },
  { value: "unknown", label: "잘 모르겠다" },
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
    trait_response?: string; // trait_probe 응답(agreed/mixed/denied/unclear — 채점 비반영)
    trait_statement?: string; // trait_probe 자유 한 줄(선택)
    static_response?: string; // CAL-P1 A(평소 체감) 응답 — 채점 비반영
    transit_response?: string; // CAL-P1 B(해당 시기 체감) 응답 — 채점 비반영
  }
>;

const _VALID: ReadonlySet<string> = new Set([
  "very_positive", "positive", "neutral", "mixed", "negative", "very_negative", "unknown",
  "no_domain_activity", "not_occurred", // CAL-QA 무신호 — 저장 값 유지(unknown과 혼합 금지)
]);

/** 레거시/저장값 → CalibrationRating. 'na'(해당없음/모름)→'unknown', 미상은 undefined. */
export function normalizeEventRating(v: string | undefined | null): CalibrationRating | undefined {
  if (!v) return undefined;
  if (v === "na") return "unknown";
  return _VALID.has(v) ? (v as CalibrationRating) : undefined;
}
