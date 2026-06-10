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

function profileToBirthInput(
  profile: Profile,
  referenceDate: string,
  timeOptions?: Record<string, unknown>,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
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
  // 부분 지정: 명시하지 않은 시간옵션은 백엔드 기본값(모두 적용)을 따른다.
  // 월운/일운/검증도 화면에 표시 중인 차트(균시차 토글 상태)와 같은 기준으로 계산되도록 포함.
  if (timeOptions) body.time_options = timeOptions;
  return body;
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
  if (!res.ok) {
    // FastAPI 에러 본문의 detail 문자열을 메시지로 노출(없으면 기본 메시지). 상태코드는 유지.
    let message = `API ${path} 실패 (${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data?.detail === "string" && data.detail) {
        message = `${data.detail} (${res.status})`;
      }
    } catch {
      /* 본문 없음/JSON 아님 → 기본 메시지 유지 */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function calculateManse(
  profile: Profile,
  referenceDate: string = todayISO(),
  timeOptions?: Record<string, unknown>,
): Promise<ManseResult> {
  return postJSON<ManseResult>(
    "/api/v2/manse/calculate",
    profileToBirthInput(profile, referenceDate, timeOptions),
  );
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
  timeOptions?: Record<string, unknown>,
): Promise<CalibrationResult> {
  return postJSON<CalibrationResult>("/api/v2/manse/calibration/feedback", {
    birth: profileToBirthInput(profile, referenceDate, timeOptions),
    answers,
  });
}

export async function fetchLuckMonths(
  profile: Profile,
  year: number,
  referenceDate: string = todayISO(),
  timeOptions?: Record<string, unknown>,
): Promise<LuckPillar[]> {
  return postJSON<LuckPillar[]>("/api/v2/manse/luck/months", {
    birth: profileToBirthInput(profile, referenceDate, timeOptions),
    year,
  });
}

export async function fetchLuckDays(
  profile: Profile,
  year: number,
  month: number,
  referenceDate: string = todayISO(),
  timeOptions?: Record<string, unknown>,
): Promise<LuckPillar[]> {
  return postJSON<LuckPillar[]>("/api/v2/manse/luck/days", {
    birth: profileToBirthInput(profile, referenceDate, timeOptions),
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
