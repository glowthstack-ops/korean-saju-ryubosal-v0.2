import { describe, expect, it } from "vitest";
import { profileToBasic, profileToBirthDTO, summaryToProfile } from "@/lib/subject-mapping";
import type { Profile, SubjectSummary } from "@/lib/types";

const PROFILE: Profile = {
  gender: "female",
  calendarType: "solar",
  isLeapMonth: false,
  birthDate: "1992-03-04",
  birthTime: "08:30",
  timeUnknown: false,
  place: { name: "부산", region: "부산광역시", lat: 35.1, lon: 129.0, tz: "Asia/Seoul" },
};

describe("subject-mapping", () => {
  it("profile → birth DTO omits reference_date and maps place/gender", () => {
    const dto = profileToBirthDTO(PROFILE);
    expect(dto).not.toHaveProperty("reference_date");
    expect(dto.birth_place_name).toBe("부산");
    expect(dto.latitude).toBe(35.1);
    expect(dto.gender).toBe("female");
    expect(dto.is_leap_month).toBeNull(); // solar
  });

  it("lunar profile carries is_leap_month", () => {
    const dto = profileToBirthDTO({ ...PROFILE, calendarType: "lunar", isLeapMonth: true });
    expect(dto.is_leap_month).toBe(true);
  });

  it("summary → profile round-trips the birth essentials", () => {
    const summary: SubjectSummary = {
      subject_id: "s1",
      owner_id: "u1",
      kind: "self",
      label: "본인",
      aliases: [],
      relation_to_user: null,
      birth: profileToBirthDTO(PROFILE),
      gender: "female",
      is_minor: false,
      subscribed: false,
      yongsin_registered: false,
      mulsang_registered: false,
    };
    const back = summaryToProfile(summary);
    expect(back.birthDate).toBe(PROFILE.birthDate);
    expect(back.birthTime).toBe("08:30");
    expect(back.gender).toBe("female");
    expect(back.calendarType).toBe("solar");
    expect(back.place.name).toBe("부산");
    expect(back.place.lat).toBe(35.1);
  });

  it("trims HH:MM:SS time from backend", () => {
    const summary = summaryToProfile({
      subject_id: "s",
      owner_id: "u",
      kind: "self",
      label: "x",
      aliases: [],
      relation_to_user: null,
      birth: { calendar_type: "solar", birth_date: "2000-01-01", birth_time: "23:59:00",
        birth_place_name: "서울", gender: "male" },
      gender: "male",
      is_minor: false,
      subscribed: false,
      yongsin_registered: false,
      mulsang_registered: false,
    });
    expect(summary.birthTime).toBe("23:59");
  });

  it("profile → basic maps gender to M/F and city/display_name", () => {
    const basic = profileToBasic(PROFILE, "별명이");
    expect(basic.gender).toBe("F");
    expect(basic.display_name).toBe("별명이");
    expect(basic.birth_place.city).toBe("부산");
  });
});
