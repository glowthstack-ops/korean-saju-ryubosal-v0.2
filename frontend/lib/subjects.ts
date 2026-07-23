// 로그인 사용자의 사주(대상)·프로필·페르소나·리포트 API 래퍼.
// 모든 호출은 lib/api의 인증 헤더 주입을 거친다(토큰 없으면 401 → 비로그인 처리).

import { deleteJSON, getJSON, postJSON, putJSON } from "./api";
import type {
  CalibrationResult,
  PersonaConfig,
  ProfileResponse,
  ProfileUpsert,
  ReportJobStatus,
  ReportJobSummary,
  RealityCalibrationQuestionSet,
  RealityCalibrationYearAnswer,
  ReportSpec,
  SubjectSummary,
  SubjectUpsert,
} from "./types";

// ── 선택된 사주(subject 비지정 화면의 오버레이 기준) ───────────
// 간지달력처럼 URL에 ?subject가 없는 화면이 "현재 선택한 사주"를 알 수 있도록 로컬에 보관한다.
// 사주를 실제로 조회한 시점(manse/result의 ?subject 해석)에 갱신한다. 로그아웃 시 clearSession이 지운다.
export const SELECTED_SUBJECT_KEY = "ryubosal.selectedSubject";

/** 현재 선택된 사주 id 저장(null이면 선택 해제). */
export function setSelectedSubjectId(id: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (id) localStorage.setItem(SELECTED_SUBJECT_KEY, id);
    else localStorage.removeItem(SELECTED_SUBJECT_KEY);
  } catch {
    /* 접근 불가 무시 */
  }
}

/** 현재 선택된 사주 id(없으면 null). */
export function getSelectedSubjectId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(SELECTED_SUBJECT_KEY);
  } catch {
    return null;
  }
}

// ── 마지막 선택 사주(서버 영속 — 재로그인 복원) ────────────────

/** 서버에 저장된 마지막 선택 사주 id — 없거나 무효(삭제·타 소유)면 null. */
export async function getLastSubject(): Promise<string | null> {
  const r = await getJSON<{ subject_id: string | null }>("/api/v2/account/last-subject");
  return r.subject_id;
}

/** 마지막 선택 사주 서버 저장(null=선택 해제). */
export async function putLastSubject(subjectId: string | null): Promise<void> {
  await putJSON("/api/v2/account/last-subject", { subject_id: subjectId });
}

// ── 사주(대상) ───────────────────────────────────────────────

export function listSubjects(): Promise<SubjectSummary[]> {
  return getJSON<SubjectSummary[]>("/api/v2/subjects");
}

export function getSubject(subjectId: string): Promise<SubjectSummary> {
  return getJSON<SubjectSummary>(`/api/v2/subjects/${subjectId}`);
}

export function createSubject(body: SubjectUpsert): Promise<SubjectSummary> {
  return postJSON<SubjectSummary>("/api/v2/subjects", body);
}

export function updateSubject(subjectId: string, body: SubjectUpsert): Promise<SubjectSummary> {
  return putJSON<SubjectSummary>(`/api/v2/subjects/${subjectId}`, body);
}

export function deleteSubject(subjectId: string): Promise<void> {
  return deleteJSON(`/api/v2/subjects/${subjectId}`);
}

// ── 사주별 프로필(물상·용신) ─────────────────────────────────

export function getProfile(subjectId: string): Promise<ProfileResponse> {
  return getJSON<ProfileResponse>(`/api/v2/profile/${subjectId}`);
}

export function saveProfile(subjectId: string, body: ProfileUpsert): Promise<ProfileResponse> {
  return putJSON<ProfileResponse>(`/api/v2/profile/${subjectId}`, body);
}

// 용신 검증 답변(서버 저장) — 어느 기기에서든 재검증 시 수정 프리필용. answers는 CalibrationPanel
// AnswerMap 구조이나 여기서는 느슨하게 둔다(직렬화 그대로 왕복).
export interface YongsinCalibration {
  answers?: Record<string, unknown>;
  result?: CalibrationResult | null;
}
export interface SubjectYongsinDetail {
  subject_id: string;
  confirmed_yongsin: string | null;
  calibration?: YongsinCalibration | null;
}

// 확정 용신(+선택적 검증 답변) 저장 — 프로필 행 없어도 DB에 영속. calibration이 있으면 함께 저장.
export function setSubjectYongsin(
  subjectId: string,
  element: string | null,
  calibration?: YongsinCalibration | null,
): Promise<SubjectYongsinDetail> {
  return putJSON(`/api/v2/profile/${subjectId}/yongsin`, {
    confirmed_yongsin: element,
    calibration: calibration ?? null,
  });
}

// 확정 용신 + 저장된 검증 답변 조회 — 재검증 시 수정 모드 프리필(교차 기기).
export function getSubjectYongsin(subjectId: string): Promise<SubjectYongsinDetail> {
  return getJSON(`/api/v2/profile/${subjectId}/yongsin`);
}

export function deleteExtendedField(subjectId: string, field: string): Promise<void> {
  return deleteJSON(`/api/v2/profile/${subjectId}/extended/${field}`);
}

// ── 계정 전역 페르소나 ───────────────────────────────────────

export function getPersona(): Promise<PersonaConfig> {
  return getJSON<PersonaConfig>("/api/v2/account/persona");
}

export function savePersona(persona: PersonaConfig): Promise<PersonaConfig> {
  return putJSON<PersonaConfig>("/api/v2/account/persona", persona);
}

// ── 리포트(테마사주) 비동기 잡 — Phase 6 백엔드 노출 후 사용 ──

export function createReportJob(
  subjectId: string,
  spec: ReportSpec,
): Promise<{ job_id: string }> {
  return postJSON<{ job_id: string }>("/api/v2/report/jobs", { subject_id: subjectId, spec });
}

export function getReportJob(jobId: string): Promise<ReportJobStatus> {
  return getJSON<ReportJobStatus>(`/api/v2/report/jobs/${jobId}`);
}

export function listReportJobs(): Promise<ReportJobSummary[]> {
  return getJSON<ReportJobSummary[]>("/api/v2/report/jobs");
}

// ── 현실 신호 캘리브레이션(개인 현실 사건 수집 — LEI) ──────────
export function getRealityCalibration(
  subjectId: string,
): Promise<RealityCalibrationQuestionSet> {
  return getJSON<RealityCalibrationQuestionSet>(
    `/api/v2/reality-calibration/${subjectId}/questions`,
  );
}

export function submitRealityCalibration(
  subjectId: string,
  answers: RealityCalibrationYearAnswer[],
): Promise<{ stored: number }> {
  return postJSON<{ stored: number }>(
    `/api/v2/reality-calibration/${subjectId}/submit`,
    { subject_id: subjectId, answers },
  );
}
