import { describe, expect, it } from "vitest";
import {
  buildTimeOptions, profileToBasic, profileToBirthDTO, subjectEotPreference, subjectJaHourRule,
  summaryToProfile,
} from "@/lib/subject-mapping";
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

  it("timeOptions가 주어지면 time_options로 영속, 없으면 필드 자체를 생략한다", () => {
    // 미전달 시 백엔드가 기본값(모든 보정 적용)으로 저장하므로, 균시차 미사용 사주는
    // 반드시 time_options를 실어야 챗·리포트 풀이가 같은 시주를 쓴다.
    const withOpts = profileToBirthDTO(PROFILE, { apply_equation_of_time: false });
    expect(withOpts.time_options).toEqual({ apply_equation_of_time: false });
    const without = profileToBirthDTO(PROFILE);
    expect(without).not.toHaveProperty("time_options");
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

  it("사주별 균시차: 저장값 false만 false, 미저장·true·부분 옵션은 true", () => {
    const base: SubjectSummary = {
      subject_id: "s", owner_id: "u", kind: "self", label: "x", aliases: [],
      relation_to_user: null, gender: "male", is_minor: false, subscribed: false,
      yongsin_registered: false, mulsang_registered: false,
      birth: { calendar_type: "solar", birth_date: "2015-03-01", birth_place_name: "서울" },
    };
    expect(subjectEotPreference(base)).toBe(false); // 구 레코드(time_options 없음) = 백엔드 기본값(미적용)
    expect(subjectEotPreference({
      ...base, birth: { ...base.birth, time_options: { apply_equation_of_time: false } },
    })).toBe(false);
    expect(subjectEotPreference({
      ...base, birth: { ...base.birth, time_options: { apply_equation_of_time: true } },
    })).toBe(true);
    expect(subjectEotPreference({
      ...base, birth: { ...base.birth, time_options: { day_boundary_rule: "23:00" } },
    })).toBe(false); // 부분 옵션 — eot 미지정이면 기본 미적용
  });

  it("profile → basic maps gender to M/F and city/display_name", () => {
    const basic = profileToBasic(PROFILE, "별명이");
    expect(basic.gender).toBe("F");
    expect(basic.display_name).toBe("별명이");
    expect(basic.birth_place.city).toBe("부산");
  });

  it("사주별 자시 규칙: early_late_zi만 구분, 미저장·none·standard_zi·미지원 값은 정자시", () => {
    // 백엔드 "none"은 standard_zi와 동작이 같으므로 UI에서는 정자시로 해석한다.
    const base: SubjectSummary = {
      subject_id: "s", owner_id: "u", kind: "self", label: "x", aliases: [],
      relation_to_user: null, gender: "male", is_minor: false, subscribed: false,
      yongsin_registered: false, mulsang_registered: false,
      birth: { calendar_type: "solar", birth_date: "1981-03-10", birth_place_name: "청주" },
    };
    const withRule = (rule: unknown): SubjectSummary => ({
      ...base, birth: { ...base.birth, time_options: { ja_hour_rule: rule } },
    });
    expect(subjectJaHourRule(base)).toBe("standard_zi"); // 구 레코드 = 백엔드 기본값
    expect(subjectJaHourRule(withRule("standard_zi"))).toBe("standard_zi");
    expect(subjectJaHourRule(withRule("none"))).toBe("standard_zi");
    expect(subjectJaHourRule(withRule("early_late_zi"))).toBe("early_late_zi");
    expect(subjectJaHourRule(withRule("bogus"))).toBe("standard_zi");
  });

  it("buildTimeOptions는 균시차·자시 규칙을 항상 함께 싣는다", () => {
    expect(buildTimeOptions(false, "early_late_zi")).toEqual({
      apply_equation_of_time: false, ja_hour_rule: "early_late_zi",
    });
    const dto = profileToBirthDTO(PROFILE, buildTimeOptions(true, "standard_zi"));
    expect(dto.time_options).toEqual({ apply_equation_of_time: true, ja_hour_rule: "standard_zi" });
  });
});
