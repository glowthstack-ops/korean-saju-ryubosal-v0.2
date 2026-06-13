import { afterEach, describe, expect, it, vi } from "vitest";
import { authHeaders, clearSession, getLoginId, getToken, isLoggedIn, login } from "@/lib/auth";

afterEach(() => {
  clearSession();
  vi.restoreAllMocks();
});

describe("auth token storage", () => {
  it("is logged-out by default", () => {
    expect(getToken()).toBeNull();
    expect(isLoggedIn()).toBe(false);
    expect(authHeaders()).toEqual({});
  });

  it("login persists token + login_id and yields auth header", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ token: "T.sig", owner_id: "alice", login_id: "alice" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await login("alice", "1234");
    expect(getToken()).toBe("T.sig");
    expect(getLoginId()).toBe("alice");
    expect(isLoggedIn()).toBe(true);
    expect(authHeaders()).toEqual({ Authorization: "Bearer T.sig" });
  });

  it("surfaces backend error detail on failed login", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "ID 또는 PIN이 올바르지 않습니다." }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(login("alice", "0000")).rejects.toThrow("올바르지 않습니다");
    expect(isLoggedIn()).toBe(false);
  });

  it("clearSession logs out", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ token: "T", owner_id: "a", login_id: "a" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await login("a", "1234");
    clearSession();
    expect(isLoggedIn()).toBe(false);
    expect(authHeaders()).toEqual({});
  });
});
