"use client";

// 계정(ID+PIN) 인증 컨텍스트 — 토큰 보관은 lib/auth(localStorage)에 위임한다.
// OAuth 도입 시 lib/auth와 본 프로바이더 내부만 교체하면 화면은 그대로 동작한다.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  clearSession,
  getLoginId,
  isLoggedIn as tokenPresent,
  login as apiLogin,
  register as apiRegister,
} from "@/lib/auth";

interface AuthState {
  ready: boolean; // 최초 토큰 확인 완료 여부(깜빡임 방지)
  isLoggedIn: boolean;
  loginId: string | null;
  login: (loginId: string, pin: string) => Promise<void>;
  register: (loginId: string, pin: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [loginId, setLoginId] = useState<string | null>(null);

  useEffect(() => {
    setIsLoggedIn(tokenPresent());
    setLoginId(getLoginId());
    setReady(true);
  }, []);

  const login = useCallback(async (id: string, pin: string) => {
    const auth = await apiLogin(id, pin);
    setIsLoggedIn(true);
    setLoginId(auth.login_id);
  }, []);

  const register = useCallback(async (id: string, pin: string) => {
    const auth = await apiRegister(id, pin);
    setIsLoggedIn(true);
    setLoginId(auth.login_id);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setIsLoggedIn(false);
    setLoginId(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ ready, isLoggedIn, loginId, login, register, logout }),
    [ready, isLoggedIn, loginId, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
