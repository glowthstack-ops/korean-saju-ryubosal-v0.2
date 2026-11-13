// 신살 표시 필터 — 만세력·간지달력 공용.
// 화면에 띄우지 않는 것은 두 가지다. 데이터는 엔진이 쓰므로 API 응답에는 남기고 렌더에서만 거른다.
// ① 지지 유형 보유 표지(寅申巳亥=이동지·子午卯酉=사정지·辰戌丑未=사고지) — 단순 지지 분류
//    (데굴님 지시 2026-10-10). 백엔드 sinsal_modifier_config.BRANCH_MARKER_NAMES 와 동일 목록.
// ② 숨김 항목(hidden=true) — 현대 자료에서 거의 쓰이지 않는 신살(데굴님 지시 2026-11-12).
//    목록은 백엔드 sinsal_catalog.HIDDEN_NAMES 가 정하고 응답의 hidden 값으로 내려온다.

export const BRANCH_MARKER_NAMES: ReadonlySet<string> = new Set(["이동지", "사정지", "사고지"]);

/** 표시용 신살 목록 — 지지 유형 보유 표지와 숨김 항목을 제외한다. */
export function visibleSinsal<T extends { name: string; hidden?: boolean }>(items: T[]): T[] {
  return items.filter((s) => !BRANCH_MARKER_NAMES.has(s.name) && !s.hidden);
}
