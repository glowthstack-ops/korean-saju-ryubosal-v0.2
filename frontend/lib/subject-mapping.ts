// 프론트 Profile ↔ 백엔드 DTO 브리지.
// 로그인 사주는 백엔드(SubjectStore)에 BirthInput으로 저장되고, 화면·만세력 호출은 Profile을
// 쓰므로 두 표현을 무손실에 가깝게 변환한다. 저장용 BirthInput에는 reference_date를 넣지
// 않는다(질의 시점에 엔진이 부여). gender는 BirthInput male/female ↔ BasicProfile M/F로 매핑.

import type { BasicProfile, BirthInputDTO, Profile, SajuLocation, SubjectSummary } from "./types";

/** Profile → 저장용 BirthInput(reference_date 제외). */
export function profileToBirthDTO(profile: Profile): BirthInputDTO {
  return {
    calendar_type: profile.calendarType,
    is_leap_month: profile.calendarType === "lunar" ? profile.isLeapMonth : null,
    birth_date: profile.birthDate,
    birth_time: profile.timeUnknown ? null : profile.birthTime,
    birth_time_unknown: profile.timeUnknown,
    birth_place_name: profile.place.name,
    latitude: profile.place.lat,
    longitude: profile.place.lon,
    timezone: profile.place.tz,
    gender: profile.gender,
  };
}

/** 백엔드 birth_time('HH:MM[:SS]') → 'HH:MM'. */
function trimTime(t: string | null | undefined): string | null {
  if (!t) return null;
  return t.slice(0, 5);
}

/** SubjectSummary.birth → Profile(화면·만세력 호출용). region은 저장되지 않아 빈 값. */
export function summaryToProfile(s: SubjectSummary): Profile {
  const b = s.birth;
  const place: SajuLocation = {
    name: b.birth_place_name,
    region: "",
    lat: b.latitude ?? 0,
    lon: b.longitude ?? 0,
    tz: b.timezone ?? "Asia/Seoul",
  };
  const gender: Profile["gender"] =
    b.gender === "female" || s.gender === "female" ? "female" : "male";
  return {
    gender,
    calendarType: b.calendar_type,
    isLeapMonth: b.is_leap_month ?? false,
    birthDate: b.birth_date,
    birthTime: trimTime(b.birth_time),
    timeUnknown: b.birth_time_unknown ?? false,
    place,
  };
}

/** Profile + 별명 → BasicProfile(1단계 프로필 저장용). */
export function profileToBasic(profile: Profile, displayName: string): BasicProfile {
  return {
    birth_date: profile.birthDate,
    calendar_type: profile.calendarType,
    is_leap_month: profile.calendarType === "lunar" ? profile.isLeapMonth : false,
    birth_time: profile.timeUnknown ? null : profile.birthTime,
    birth_time_unknown: profile.timeUnknown,
    birth_place: { country: "KR", city: profile.place.name, longitude: profile.place.lon },
    gender: profile.gender === "female" ? "F" : "M",
    display_name: displayName,
  };
}
