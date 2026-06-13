// 로그인 사용자의 사주(대상)·프로필·페르소나·리포트 API 래퍼.
// 모든 호출은 lib/api의 인증 헤더 주입을 거친다(토큰 없으면 401 → 비로그인 처리).

import { deleteJSON, getJSON, postJSON, putJSON } from "./api";
import type {
  PersonaConfig,
  ProfileResponse,
  ProfileUpsert,
  ReportJobStatus,
  ReportJobSummary,
  ReportSpec,
  SubjectSummary,
  SubjectUpsert,
} from "./types";

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
