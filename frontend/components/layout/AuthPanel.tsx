"use client";

// ID+PIN 로그인/등록 패널(드로어 내부). 로그인 상태면 계정 표시 + 로그아웃.
// 임시 인증임을 안내한다(추후 OAuth 대치).

import { useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";

export function AuthPanel() {
  const { ready, isLoggedIn, loginId, login, register, logout } = useAuth();
  const [id, setId] = useState("");
  const [pin, setPin] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ready) return <p className="text-xs text-gray-400">계정 확인 중…</p>;

  if (isLoggedIn) {
    return (
      <div className="space-y-2 text-sm">
        <p className="text-gray-600">
          <span className="font-medium text-gray-800">{loginId}</span>님으로 로그인됨
        </p>
        <button
          onClick={logout}
          className="rounded border px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          로그아웃
        </button>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(id, pin);
      else await register(id, pin);
    } catch (err) {
      setError(err instanceof Error ? err.message : "실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 text-sm">
      <div className="flex gap-2 text-xs">
        {(["login", "register"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded px-2 py-1 ${
              mode === m ? "bg-gray-800 text-white" : "border text-gray-600"
            }`}
          >
            {m === "login" ? "로그인" : "새 계정"}
          </button>
        ))}
      </div>
      <input
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder="아이디(영문/숫자 3~30자)"
        className="w-full rounded border px-2 py-1"
        autoComplete="username"
      />
      <input
        value={pin}
        onChange={(e) => setPin(e.target.value)}
        placeholder="PIN(숫자 4~12자)"
        type="password"
        inputMode="numeric"
        className="w-full rounded border px-2 py-1"
        autoComplete={mode === "login" ? "current-password" : "new-password"}
      />
      {mode === "register" && (
        <p className="text-[11px] leading-snug text-gray-400">
          PIN은 숫자만 입력할 수 있어요 (4~12자).
        </p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="w-full rounded bg-gray-800 px-3 py-1.5 text-white disabled:opacity-50"
      >
        {busy ? "처리 중…" : mode === "login" ? "로그인" : "계정 만들기"}
      </button>
      <p className="text-[11px] leading-snug text-gray-400">
        같은 아이디·PIN으로 어느 기기에서나 사주목록이 이어집니다. 임시 본인 확인 수단이며 추후
        소셜 로그인으로 대체됩니다.
      </p>
    </form>
  );
}
