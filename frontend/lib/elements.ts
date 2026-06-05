// 오행 색상(명세 규칙) + 한자/한글 병기 유틸.

export const ELEMENT_KO: Record<string, string> = {
  "木": "목", "火": "화", "土": "토", "金": "금", "水": "수",
};

// 색만으로 구분하지 않도록 라벨을 항상 병기한다(명세 접근성 규칙).
export const ELEMENT_STYLE: Record<string, string> = {
  "木": "bg-green-600 text-white",
  "火": "bg-red-600 text-white",
  "土": "bg-yellow-500 text-black",
  "金": "bg-gray-100 text-black border border-gray-300",
  "水": "bg-gray-900 text-white",
};

export function elementStyle(element: string | null | undefined): string {
  return (element && ELEMENT_STYLE[element]) || "bg-gray-200 text-black";
}

export function elementLabel(element: string | null | undefined): string {
  if (!element) return "-";
  return `${element}(${ELEMENT_KO[element] ?? ""})`;
}

const STEM_KO: Record<string, string> = {
  "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
  "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
};
const BRANCH_KO: Record<string, string> = {
  "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진", "巳": "사",
  "午": "오", "未": "미", "申": "신", "酉": "유", "戌": "술", "亥": "해",
};

export function ganjiKo(ganji: string): string {
  return [...ganji].map((c) => STEM_KO[c] ?? BRANCH_KO[c] ?? c).join("");
}
