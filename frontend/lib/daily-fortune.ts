// 일주별 오늘의 운세 — API 타입·클라이언트/서버 래퍼.
// 표시 날짜·요일은 반드시 API 응답 값(fortune_date·weekday_ko)을 쓴다(클라이언트 재계산 금지).

import { getJSON } from "./api";

export interface DailyEventForecast {
  slot: "good" | "caution" | "support";
  event_key: string;
  domain: string;
  probability: number;
  phrase: string;
}

export interface LuckyPlace {
  place_key: string;
  name: string;
  phrase: string;
}

export interface DailyIljuFortune {
  ilju: string; // 한자 2자 "甲子"
  ilju_ko: string; // "갑자"
  day_stem_ko: string; // 일간 탭 그룹핑용 "갑"
  headline: string;
  headline_event_key: string;
  events: DailyEventForecast[];
  lucky_place: LuckyPlace;
  lotto_phrase: string | null;
  love_line: string | null; // 강한 love 전용 신호일 때만(게이트) — 없으면 미표시
  advice: string | null; // 조언 줄 — 과거 계약 보드는 null
  polished: boolean;
}

export interface DailyMonthIljuFlow {
  ilju: string;
  ilju_ko: string;
  note: string;
}

export interface DailyMonthStemFlow {
  day_stem_ko: string;
  common: string; // 천간 공통 흐름(십성 쌍 + 행동 + 12운성 + 다음 달·내년)
  ilju_notes: DailyMonthIljuFlow[]; // 일주별 흐름 — 일지↔월운 지지 관계가 있는 일주만(없으면 빈 배열)
  next_preview?: string | null; // 다음 달 미리보기 — 월운 전환 7일 전부터, 그 밖은 null
  same_group_note?: string | null; // 단식 같은 결 강조(docs/17 §26) — 같은 군인 달에만, 과거 계약은 null
}

/** 올해의 결(단식, docs/17 §26) — 일간 1개. 길흉 없음(양면 어휘). */
export interface DailyYearStemFlow {
  day_stem_ko: string;
  tone: string;
  emphasis?: string | null;
  points: string[];
  peak_months?: string | null;
}

export interface DailyTop5 {
  money: string[];
  love: string[];
  news: string[];
}

export interface DailyFortuneBoard {
  fortune_date: string;
  weekday: number;
  weekday_ko: string;
  content_version: string;
  polish_status: string;
  top5: DailyTop5;
  fortunes: DailyIljuFortune[];
  season_band: string | null; // 12절기 입절일에만
  month_label?: string | null; // "기해월(己亥) 11월 8일~12월 6일" — 과거 계약은 null
  next_month_label?: string | null; // "기해월(己亥) 11월 8일부터" — 전환 7일 전부터
  month_flow: DailyMonthStemFlow[] | null; // 과거 계약 보드는 null
  year_flow?: DailyYearStemFlow[] | null; // 올해의 결(dict.v1.19~) — 과거 계약은 null
  year_label?: string | null; // "병오년(丙午) 2026년 2월 4일~2027년 2월 3일"
  year_direction_note?: string | null; // 발판/소모 기준 안내(docs/17 §26-5) — 과거 계약은 null
}

export interface DailyFortuneSingle {
  fortune_date: string;
  weekday: number;
  weekday_ko: string;
  fortune: DailyIljuFortune;
}

/** 오늘의 60일주 보드(클라이언트). */
export async function getDailyBoard(): Promise<DailyFortuneBoard> {
  return getJSON<DailyFortuneBoard>("/api/v2/daily-fortune/today");
}

/** 일주 단건(메인 카드) — 한자·한글 표기 모두 허용. */
export async function getDailyFortune(ilju: string): Promise<DailyFortuneSingle> {
  return getJSON<DailyFortuneSingle>(
    `/api/v2/daily-fortune/today/${encodeURIComponent(ilju)}`,
  );
}

/** 서버 컴포넌트용 보드 프리페치 — 프레임워크 캐시 잔존 방지(no-store). */
export async function getDailyBoardServer(): Promise<DailyFortuneBoard | null> {
  const base = process.env.SAJU_BACKEND_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${base}/api/v2/daily-fortune/today`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as DailyFortuneBoard;
  } catch {
    return null;
  }
}

/** "2026-07-23" + "수요일" → "7월 23일 수요일" (API 값 그대로 조합). */
export function formatFortuneDate(iso: string, weekdayKo: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}월 ${Number(d)}일 ${weekdayKo}`;
}
