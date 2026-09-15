// 프론트 Profile ↔ 백엔드 DTO 브리지.
// 로그인 사주는 백엔드(SubjectStore)에 BirthInput으로 저장되고, 화면·만세력 호출은 Profile을
// 쓰므로 두 표현을 무손실에 가깝게 변환한다. 저장용 BirthInput에는 reference_date를 넣지
// 않는다(질의 시점에 엔진이 부여). gender는 BirthInput male/female ↔ BasicProfile M/F로 매핑.

import {
  DEFAULT_JA_HOUR_RULE,
  type BasicProfile,
  type BirthInputDTO,
  type JaHourRule,
  type Profile,
  type SajuLocation,
  type SubjectSummary,
} from "./types";

/** Profile → 저장용 BirthInput(reference_date 제외).

  timeOptions를 주면 time_options로 함께 저장한다 — 챗·리포트 풀이는 저장된 birth를
  그대로 쓰므로, 만세력 화면의 균시차 토글과 같은 기준을 영속화하려면 반드시 전달해야 한다.
  (미전달 시 백엔드 기본값 = 모든 보정 적용으로 저장된다.) */
export function profileToBirthDTO(
  profile: Profile,
  timeOptions?: Record<string, unknown>,
): BirthInputDTO {
  const dto: BirthInputDTO = {
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
  if (timeOptions) dto.time_options = timeOptions;
  return dto;
}

/** 백엔드 birth_time('HH:MM[:SS]') → 'HH:MM'. */
function trimTime(t: string | null | undefined): string | null {
  if (!t) return null;
  return t.slice(0, 5);
}

/** 저장된 사주의 균시차 사용 여부 — 로그인 사주는 사주별 속성(birth.time_options)이
  진실 소스다(기기 로컬 토글은 비로그인 전용). 미저장(구 레코드)은 백엔드 기본값 false(미적용). */
export function subjectEotPreference(s: SubjectSummary): boolean {
  return s.birth.time_options?.["apply_equation_of_time"] === true;
}

/** 저장된 사주의 자시 처리 규칙 — 균시차와 같은 사주별 속성. 미저장(구 레코드)·미지원 값
  ("none" 포함)은 백엔드 기본값 정자시(standard_zi)로 해석해 기존 결과가 바뀌지 않는다. */
export function subjectJaHourRule(s: SubjectSummary): JaHourRule {
  return s.birth.time_options?.["ja_hour_rule"] === "early_late_zi"
    ? "early_late_zi"
    : DEFAULT_JA_HOUR_RULE;
}

/** 화면 상태(균시차·자시 규칙) → 만세력·월운·일운·검증 호출과 저장에 공통으로 쓰는 time_options.
  두 값을 항상 함께 실어 챗·리포트·간지달력·오늘의 운세가 만세력 화면과 같은 명식을 쓰게 한다. */
export function buildTimeOptions(
  applyEquationOfTime: boolean,
  jaHourRule: JaHourRule,
): { apply_equation_of_time: boolean; ja_hour_rule: JaHourRule } {
  return { apply_equation_of_time: applyEquationOfTime, ja_hour_rule: jaHourRule };
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
