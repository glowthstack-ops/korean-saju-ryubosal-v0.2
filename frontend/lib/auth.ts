// 계정(ID+PIN) 경량 인증 — 세션 토큰을 localStorage에 보관하고 요청 헤더로 전달한다.
// OAuth 도입 전 임시 수단(낮은 보안 등급). 토큰은 비식별 owner_id 서명값이라 사주 식별정보를
// 포함하지 않는다. 추후 OAuth로 대치 시 본 모듈의 login/register/token 보관만 교체한다.

import type { AccountRecord, AuthToken } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const TOKEN_KEY = "ryubosal:authToken";
const LOGIN_KEY = "ryubosal:loginId";

/** 저장된 세션 토큰(없으면 null). SSR/접근 불가 시 null. */
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** 로그인 ID(표시용). */
export function getLoginId(): string | null {
  try {
    return localStorage.getItem(LOGIN_KEY);
  } catch {
    return null;
  }
}

/** 로그인 여부(토큰 존재). */
export function isLoggedIn(): boolean {
  return getToken() !== null;
}

function setSession(auth: AuthToken): void {
  try {
    localStorage.setItem(TOKEN_KEY, auth.token);
    localStorage.setItem(LOGIN_KEY, auth.login_id);
  } catch {
    /* 접근 불가 시 무시(이후 호출은 비로그인 처리) */
  }
}

/** 토큰 폐기(로그아웃). */
export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(LOGIN_KEY);
  } catch {
    /* 무시 */
  }
}

/** Authorization 헤더(토큰 없으면 빈 객체). */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postAuth(path: string, body: unknown): Promise<AuthToken> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let message = path.endsWith("register") ? "등록 실패" : "로그인 실패";
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data?.detail === "string" && data.detail) message = data.detail;
    } catch {
      /* 본문 없음 → 기본 메시지 */
    }
    throw new Error(message);
  }
  return res.json() as Promise<AuthToken>;
}

/** 신규 계정 등록 → 토큰 보관. */
export async function register(loginId: string, pin: string): Promise<AuthToken> {
  const auth = await postAuth("/api/v2/auth/register", { login_id: loginId, pin });
  setSession(auth);
  return auth;
}

/** 로그인 → 토큰 보관(같은 ID+PIN이면 사주목록 복원). */
export async function login(loginId: string, pin: string): Promise<AuthToken> {
  const auth = await postAuth("/api/v2/auth/login", { login_id: loginId, pin });
  setSession(auth);
  return auth;
}

/** 현재 계정 조회(토큰 검증). */
export async function fetchMe(): Promise<AccountRecord | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${BASE}/api/v2/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json() as Promise<AccountRecord>;
}
