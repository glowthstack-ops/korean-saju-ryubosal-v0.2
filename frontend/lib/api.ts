import type {
  CalendarMonth,
  CalibrationResult,
  LuckPillar,
  ManseResult,
  Profile,
} from "./types";

// 클라이언트 호출: 상대경로(빈 base) → Next 리라이트가 백엔드로 프록시(터널과 같은 출처).
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
// 서버사이드(getCalendar 등)는 상대경로 fetch 불가 → 호스트 내부 절대주소 사용.
const SERVER_BASE = process.env.SAJU_BACKEND_URL || "http://localhost:8000";

function profileToBirthInput(profile: Profile, referenceDate: string) {
  return {
    calendar_type: profile.calendarType,
    is_leap_month: profile.calendarType === "lunar" ? profile.isLeapMonth : null,
    birth_date: profile.birthDate,
    birth_time: profile.timeUnknown ? null : profile.birthTime,
    birth_time_unknown: profile.timeUnknown,
    birth_place_name: profile.place.name,
    latitude: profile.place.lat,
    longitude: profile.place.lon,
    timezone: profile.place.tz,
    gender: profile.gender,
    reference_date: referenceDate,
  };
}

function todayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${path} 실패 (${res.status})`);
  return res.json() as Promise<T>;
}

export async function calculateManse(
  profile: Profile,
  referenceDate: string = todayISO(),
  timeOptions?: Record<string, unknown>,
): Promise<ManseResult> {
  const body: Record<string, unknown> = profileToBirthInput(profile, referenceDate);
  // 부분 지정: 명시하지 않은 시간옵션은 백엔드 기본값(모두 적용)을 따른다.
  if (timeOptions) body.time_options = timeOptions;
  return postJSON<ManseResult>("/api/v2/manse/calculate", body);
}

export interface FeedbackAnswer {
  question_id: string;
  overall_rating: string;
  selected_events: string[];
}

export async function submitCalibration(
  profile: Profile,
  answers: FeedbackAnswer[],
  referenceDate: string = todayISO(),
): Promise<CalibrationResult> {
  return postJSON<CalibrationResult>("/api/v2/manse/calibration/feedback", {
    birth: profileToBirthInput(profile, referenceDate),
    answers,
  });
}

export async function fetchLuckMonths(
  profile: Profile,
  year: number,
  referenceDate: string = todayISO(),
): Promise<LuckPillar[]> {
  return postJSON<LuckPillar[]>("/api/v2/manse/luck/months", {
    birth: profileToBirthInput(profile, referenceDate),
    year,
  });
}

export async function fetchLuckDays(
  profile: Profile,
  year: number,
  month: number,
  referenceDate: string = todayISO(),
): Promise<LuckPillar[]> {
  return postJSON<LuckPillar[]>("/api/v2/manse/luck/days", {
    birth: profileToBirthInput(profile, referenceDate),
    year,
    month,
  });
}

export async function getCalendar(
  year: number,
  month: number,
  revalidateSeconds = 3600,
): Promise<CalendarMonth> {
  const res = await fetch(`${SERVER_BASE}/api/v2/calendar/${year}/${month}`, {
    next: { revalidate: revalidateSeconds },
  });
  if (!res.ok) throw new Error(`달력 조회 실패 (${res.status})`);
  return res.json() as Promise<CalendarMonth>;
}

export { todayISO };
