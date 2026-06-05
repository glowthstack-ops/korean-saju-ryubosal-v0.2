import { beforeEach, describe, expect, it } from "vitest";
import { clearProfile, loadProfile, saveProfile } from "@/lib/storage";
import type { Profile } from "@/lib/types";

const PROFILE: Profile = {
  gender: "male",
  calendarType: "solar",
  isLeapMonth: false,
  birthDate: "1980-11-22",
  birthTime: "09:08",
  timeUnknown: false,
  place: { name: "서울", region: "대한민국", lat: 37.5665, lon: 126.978, tz: "Asia/Seoul" },
};

describe("encrypted profile storage", () => {
  beforeEach(async () => {
    await clearProfile();
  });

  it("round-trips the profile through encryption", async () => {
    expect(await loadProfile()).toBeNull();
    await saveProfile(PROFILE);
    expect(await loadProfile()).toEqual(PROFILE);
  });

  it("stores ciphertext, not plaintext", async () => {
    await saveProfile(PROFILE);
    // 저장된 레코드를 직접 열어 평문이 노출되지 않는지 확인.
    const rec = await new Promise<{ ciphertext: ArrayBuffer }>((resolve, reject) => {
      const req = indexedDB.open("ryubosal", 1);
      req.onsuccess = () => {
        const g = req.result.transaction("profile", "readonly").objectStore("profile").get("current");
        g.onsuccess = () => resolve(g.result);
        g.onerror = () => reject(g.error);
      };
      req.onerror = () => reject(req.error);
    });
    const bytes = new TextDecoder().decode(new Uint8Array(rec.ciphertext));
    expect(bytes).not.toContain("서울");
    expect(bytes).not.toContain("1980");
  });

  it("clears profile", async () => {
    await saveProfile(PROFILE);
    await clearProfile();
    expect(await loadProfile()).toBeNull();
  });
});
