// 신살 표시 필터 — 만세력·간지달력 공용.
// 지지 유형 보유 표지(寅申巳亥=이동지·子午卯酉=사정지·辰戌丑未=사고지)는 단순 지지 분류라 화면에
// 띄우지 않는다(데굴님 지시 2026-10-10). 백엔드 sinsal_modifier_config.BRANCH_MARKER_NAMES 와 동일 목록.
// 데이터는 엔진(이동·사고수 패턴)이 쓰므로 API 응답에서는 유지하고 렌더에서만 거른다.

export const BRANCH_MARKER_NAMES: ReadonlySet<string> = new Set(["이동지", "사정지", "사고지"]);

/** 표시용 신살 목록 — 지지 유형 보유 표지를 제외한다. */
export function withoutBranchMarkers<T extends { name: string }>(items: T[]): T[] {
  return items.filter((s) => !BRANCH_MARKER_NAMES.has(s.name));
}
