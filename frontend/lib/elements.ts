// 오행 색상(명세 규칙) + 한자/한글 병기 유틸.

export const ELEMENT_KO: Record<string, string> = {
  "木": "목", "火": "화", "土": "토", "金": "금", "水": "수",
};

// 색만으로 구분하지 않도록 라벨을 항상 병기한다(명세 접근성 규칙).
// 파스텔 톤: 오방색(青赤黃白黑) 정체성은 유지하되 채도를 낮춰 부드럽게.
export const ELEMENT_STYLE: Record<string, string> = {
  "木": "bg-green-100 text-green-800",
  "火": "bg-rose-100 text-rose-800",
  "土": "bg-amber-100 text-amber-800",
  "金": "bg-gray-100 text-gray-600",
  "水": "bg-slate-500 text-white",
};

export function elementStyle(element: string | null | undefined): string {
  return (element && ELEMENT_STYLE[element]) || "bg-gray-200 text-black";
}

export function elementLabel(element: string | null | undefined): string {
  if (!element) return "-";
  return `${element}(${ELEMENT_KO[element] ?? ""})`;
}

// 납음오행 한글명(…목/화/토/금/수)의 끝 글자 → 오행 한자(색상용).
const NAEUM_KO_TO_HANJA: Record<string, string> = {
  목: "木", 화: "火", 토: "土", 금: "金", 수: "水",
};
export function naeumElement(naeum?: string | null): string | undefined {
  if (!naeum) return undefined;
  return NAEUM_KO_TO_HANJA[naeum.slice(-1)];
}

// 천간 음양(陰陽). 지지는 본기(정기) 지장간의 음양으로 표기한다(체용 기준: 巳=양화, 亥=양수).
export const STEM_YINYANG: Record<string, "양" | "음"> = {
  "甲": "양", "乙": "음", "丙": "양", "丁": "음", "戊": "양",
  "己": "음", "庚": "양", "辛": "음", "壬": "양", "癸": "음",
};

// 양 → "+", 음 → "−".
export function yinyangSign(stem: string): string {
  const y = STEM_YINYANG[stem];
  return y === "양" ? "+" : y === "음" ? "−" : "";
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
