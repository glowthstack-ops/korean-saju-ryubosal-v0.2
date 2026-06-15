// 운영 관리자 콘솔 API 클라이언트 (Phase D). 백엔드 /api/v2/admin/* — require_admin 가드.

import { getJSON, postJSON, putJSON } from "./api";

export interface UsageTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  chat_calls: number;
  report_calls: number;
  cost_krw: number;
}

export interface AdminOverview {
  exchange_rate_usd_krw: number;
  today: UsageTotals;
  last_7d: UsageTotals;
  last_30d: UsageTotals;
  projection_month_usd: number;
  projection_month_krw: number;
  unit_cost_chat_usd: number;
  unit_cost_report_section_usd: number;
  job_status_counts: Record<string, number>;
  unresolved_errors: number;
}

export interface UsageRow {
  key: string | null;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  cost_krw: number;
}

export interface JobRow {
  job_id: string;
  owner_id: string;
  product_code: string | null;
  status: string;
  sections_done: number;
  sections_total: number;
  error: string | null;
  created_at: string | null;
}

export interface PricingRow {
  model: string;
  input_per_1m: number;
  output_per_1m: number;
  cached_per_1m: number;
  updated_at: string | null;
  updated_by: string | null;
}

export type GroupBy = "day" | "surface" | "product" | "model" | "owner";

export const getOverview = () => getJSON<AdminOverview>("/api/v2/admin/overview");

export const getUsageSummary = (groupBy: GroupBy, start?: string, end?: string) => {
  const q = new URLSearchParams({ group_by: groupBy });
  if (start) q.set("start", start);
  if (end) q.set("end", end);
  return getJSON<{ exchange_rate_usd_krw: number; group_by: string; rows: UsageRow[] }>(
    `/api/v2/admin/usage/summary?${q}`,
  );
};

export const getTimeseries = (days = 30) =>
  getJSON<{ exchange_rate_usd_krw: number; rows: UsageRow[] }>(
    `/api/v2/admin/usage/timeseries?days=${days}`,
  );

export const getEvents = (status?: string, limit = 100) => {
  const q = new URLSearchParams({ limit: String(limit) });
  if (status) q.set("status", status);
  return getJSON<{ jobs: JobRow[] }>(`/api/v2/admin/events?${q}`);
};

export const getPricing = () =>
  getJSON<{ pricing: PricingRow[]; usd_krw: number }>("/api/v2/admin/pricing");

export const putPricing = (
  model: string,
  body: { input_per_1m: number; output_per_1m: number; cached_per_1m: number },
) => putJSON<{ ok: boolean }>(`/api/v2/admin/pricing/${encodeURIComponent(model)}`, body);

export const putRate = (usd_krw: number) =>
  putJSON<{ ok: boolean }>("/api/v2/admin/settings/usd_krw", { usd_krw });

export interface ErrorRow {
  id: number;
  created_at: string | null;
  source: string;
  severity: string;
  kind: string;
  message: string;
  detail: string | null;
  path: string | null;
  owner_id: string | null;
  ref_id: string | null;
  fingerprint: string;
  resolved: boolean;
}

export interface ErrorGroup {
  fingerprint: string;
  count: number;
  unresolved: number;
  last_seen: string | null;
  first_seen: string | null;
  source: string;
  severity: string;
  kind: string;
  message: string;
  path: string | null;
}

export const getErrorGroups = (days = 7, unresolved = false) => {
  const q = new URLSearchParams({ days: String(days) });
  if (unresolved) q.set("unresolved", "true");
  return getJSON<{ groups: ErrorGroup[]; counts: { total: number; unresolved: number } }>(
    `/api/v2/admin/errors/groups?${q}`,
  );
};

export const getErrors = (
  opts: { source?: string; severity?: string; fingerprint?: string; unresolved?: boolean; limit?: number } = {},
) => {
  const q = new URLSearchParams();
  if (opts.source) q.set("source", opts.source);
  if (opts.severity) q.set("severity", opts.severity);
  if (opts.fingerprint) q.set("fingerprint", opts.fingerprint);
  if (opts.unresolved) q.set("unresolved", "true");
  if (opts.limit) q.set("limit", String(opts.limit));
  return getJSON<{ errors: ErrorRow[] }>(`/api/v2/admin/errors?${q}`);
};

export const resolveErrors = (body: { ids?: number[]; fingerprint?: string }) =>
  postJSON<{ ok: boolean; resolved: number }>("/api/v2/admin/errors/resolve", body);
