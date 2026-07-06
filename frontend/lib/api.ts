import { authHeaders } from "./auth";
import type {
  CalendarMonth,
  CalibrationResult,
  ChatApiResponse,
  ChatMessageDTO,
  ChatPartner,
  ChatThreadSummary,
  LuckPillar,
  ManseResult,
  PersonaConfig,
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

async function failure(path: string, res: Response): Promise<never> {
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

// 로그인 토큰이 있으면 Authorization 헤더를 자동 첨부한다(없으면 비로그인 호출).
async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), ...authHeaders() },
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) return failure(path, res);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function getJSON<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

async function putJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function deleteJSON(path: string): Promise<void> {
  await request<void>(path, { method: "DELETE" });
}

export { getJSON, putJSON, deleteJSON, postJSON };

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
  overall_rating: string; // 전체 체감 7상태(ExperienceRating). 레거시 unknown 호환.
  selected_events: string[];
  // 이벤트형 질문 응답 — event_key → ExperienceRating(레거시 'positive'|'negative'|'na' 호환).
  event_ratings?: Record<string, string>;
  // 영역별 체감(docs/14) — domain → ExperienceRating.
  domain_ratings?: Record<string, string>;
  // 사건별 강도(선택, 1~3).
  event_intensity?: Record<string, number>;
  // trait_probe 응답(CAL-P0) — agreed/mixed/denied/unclear. 채점 비반영(표현 보정용).
  trait_response?: string | null;
  trait_statement?: string | null;
  // CAL-P1 pair 응답 — A(평소 체감)/B(해당 시기 체감). 채점 비반영.
  static_response?: string | null;
  transit_response?: string | null;
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

export async function postChat(
  profile: Profile,
  question: string,
  threadId?: string,
  persona?: PersonaConfig,
  subjectLabel?: string,
  subjectId?: string,
  partner?: ChatPartner,
): Promise<ChatApiResponse> {
  return postJSON<ChatApiResponse>("/api/v2/chat", {
    birth: profileToBirthInput(profile, todayISO()),
    question,
    thread_id: threadId ?? null,
    persona: persona ?? null,
    subject_label: subjectLabel ?? null,
    subject_id: subjectId ?? null, // 개인화(현실 신호 시그니처·코호트) 키
    // 궁합(pairwise) — 상대 첨부 시 두 명식 궁합으로 답한다.
    partner_subject_id: partner?.mode === "registered" ? partner.subjectId : null,
    partner_inline: partner?.mode === "inline" ? partner.birth : null,
    partner_label: partner?.label ?? null,
    dry_run: false,
  });
}

// ── 대화 저장/열람/삭제 (로그인 전용) ──────────────────────────
export function listChatThreads(): Promise<ChatThreadSummary[]> {
  return getJSON<ChatThreadSummary[]>("/api/v2/chat/threads");
}

export function getChatThread(threadId: string): Promise<ChatMessageDTO[]> {
  return getJSON<ChatMessageDTO[]>(`/api/v2/chat/threads/${threadId}`);
}

// 스레드에 서버 저장된 궁합 상대 첨부(크로스 디바이스 재개 복원). 없거나 권한 밖이면 null.
export async function getChatPartner(threadId: string): Promise<ChatPartner | null> {
  try {
    const r = await getJSON<{ partner: ChatPartner | null }>(
      `/api/v2/chat/threads/${threadId}/partner`,
    );
    return r.partner ?? null;
  } catch {
    return null;
  }
}

export function deleteChatThread(threadId: string): Promise<void> {
  return deleteJSON(`/api/v2/chat/threads/${threadId}`);
}

// 미열람 완료 답변이 있는 스레드 수(전역 뱃지) — 이탈 후 백그라운드 완료 알림용.
export async function getChatUnseenCount(): Promise<number> {
  try {
    const r = await getJSON<{ count: number }>("/api/v2/chat/unseen");
    return r.count ?? 0;
  } catch {
    return 0;
  }
}

export { profileToBirthInput };
