// 큐레이션 출생지 목록(좌표 + IANA timezone). 엔진은 좌표·tz를 사용한다.
import { KR_SIGUNGU } from "./locations-kr";
import type { SajuLocation } from "./types";

export const LOCATIONS: SajuLocation[] = [
  // 국내 광역시·주요 도시(빠른 선택)
  { name: "서울", region: "대한민국", lat: 37.5665, lon: 126.978, tz: "Asia/Seoul" },
  { name: "부산", region: "대한민국", lat: 35.1796, lon: 129.0756, tz: "Asia/Seoul" },
  { name: "대구", region: "대한민국", lat: 35.8714, lon: 128.6014, tz: "Asia/Seoul" },
  { name: "인천", region: "대한민국", lat: 37.4563, lon: 126.7052, tz: "Asia/Seoul" },
  { name: "광주", region: "대한민국", lat: 35.1595, lon: 126.8526, tz: "Asia/Seoul" },
  { name: "대전", region: "대한민국", lat: 36.3504, lon: 127.3845, tz: "Asia/Seoul" },
  { name: "울산", region: "대한민국", lat: 35.5384, lon: 129.3114, tz: "Asia/Seoul" },
  { name: "수원", region: "대한민국", lat: 37.2636, lon: 127.0286, tz: "Asia/Seoul" },
  { name: "춘천", region: "대한민국", lat: 37.8813, lon: 127.7298, tz: "Asia/Seoul" },
  { name: "전주", region: "대한민국", lat: 35.8242, lon: 127.148, tz: "Asia/Seoul" },
  { name: "청주", region: "대한민국", lat: 36.6424, lon: 127.489, tz: "Asia/Seoul" },
  { name: "제주", region: "대한민국", lat: 33.4996, lon: 126.5312, tz: "Asia/Seoul" },
  // 전국 시군구(상세) — 시도명·시군구명으로 검색
  ...KR_SIGUNGU,
  // 주요 해외 도시
  { name: "Tokyo (도쿄)", region: "일본", lat: 35.6762, lon: 139.6503, tz: "Asia/Tokyo" },
  { name: "Beijing (베이징)", region: "중국", lat: 39.9042, lon: 116.4074, tz: "Asia/Shanghai" },
  { name: "New York (뉴욕)", region: "미국", lat: 40.7128, lon: -74.006, tz: "America/New_York" },
  { name: "Los Angeles (LA)", region: "미국", lat: 34.0522, lon: -118.2437, tz: "America/Los_Angeles" },
  { name: "London (런던)", region: "영국", lat: 51.5074, lon: -0.1278, tz: "Europe/London" },
  { name: "Sydney (시드니)", region: "호주", lat: -33.8688, lon: 151.2093, tz: "Australia/Sydney" },
];

const MAX_RESULTS = 40; // 시군구 다수 매칭 시 표시 상한(더 좁히려면 입력 추가).

export function searchLocations(query: string): SajuLocation[] {
  const q = query.trim().toLowerCase();
  if (!q) return LOCATIONS.slice(0, MAX_RESULTS);
  return LOCATIONS.filter(
    (l) => l.name.toLowerCase().includes(q) || l.region.toLowerCase().includes(q),
  ).slice(0, MAX_RESULTS);
}
