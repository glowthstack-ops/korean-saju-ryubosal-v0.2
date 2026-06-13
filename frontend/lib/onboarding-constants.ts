// 온보딩 입력용 닫힌 분류(docs/11 3장). 라벨은 사용자 표시용, id는 백엔드 저장값.

export const OCCUPATIONS: { id: string; label: string }[] = [
  { id: "O01", label: "사무/행정/기획" },
  { id: "O02", label: "공무원/군인/경찰/소방" },
  { id: "O03", label: "경영/임원/관리직" },
  { id: "O04", label: "영업/판매/유통" },
  { id: "O05", label: "금융/회계/세무/투자" },
  { id: "O06", label: "교육/강의/연구" },
  { id: "O07", label: "의료/보건/약무" },
  { id: "O08", label: "법률/특허/감사" },
  { id: "O09", label: "IT/개발/엔지니어링" },
  { id: "O10", label: "제조/생산/기술직" },
  { id: "O11", label: "예술/창작/디자인/콘텐츠" },
  { id: "O12", label: "방송/연예/스포츠" },
  { id: "O13", label: "서비스/요식/미용/접객" },
  { id: "O14", label: "운송/물류/항공/여행" },
  { id: "O15", label: "건설/부동산/농림수산" },
  { id: "O16", label: "종교/상담/복지/활인업" },
  { id: "O17", label: "학생/수험생" },
  { id: "O18", label: "주부/무직/구직/은퇴" },
];

export const EMPLOYMENT_FORMS = [
  "정규직",
  "계약직",
  "프리랜서",
  "자영업",
  "법인대표",
  "무급가족종사",
] as const;

export const MARITAL_STATUSES = [
  "미혼",
  "연애중",
  "기혼",
  "재혼",
  "별거",
  "이혼",
  "사별",
] as const;
