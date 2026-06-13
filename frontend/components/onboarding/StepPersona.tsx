"use client";

// [페르소나설정] 상담가 문체 5축(docs/11 5장). 계정 전역 1개(궁합 충돌 방지) — 사주별 아님.
// 점수·날짜·간지에 영향 없음(문체 전용). politeness↔style, politeness↔호칭 제약을 UI로 강제.

import type { PersonaConfig } from "@/lib/types";

type Style = PersonaConfig["speech"]["style"];
type Preset = NonNullable<PersonaConfig["user_honorific"]["preset_id"]>;

const STYLE_BY_POLITENESS: Record<"jondae" | "banmal", { id: Style; label: string }[]> = {
  jondae: [
    { id: "haeyo", label: "~해요체" },
    { id: "hapsyo", label: "~합니다체" },
  ],
  banmal: [
    { id: "banmal_chae", label: "~반말체" },
    { id: "hagae", label: "~하게체" },
  ],
};

// 호칭 프리셋과 허용 politeness(docs/11 5-2 제약).
const HONORIFICS: { id: Preset; label: string; allow: ("jondae" | "banmal")[] }[] = [
  { id: "name_nim", label: "○○님", allow: ["jondae"] },
  { id: "nim_only", label: "님", allow: ["jondae"] },
  { id: "gogaeknim", label: "고객님", allow: ["jondae"] },
  { id: "seonsaengnim", label: "선생님", allow: ["jondae"] },
  { id: "name_only", label: "○○(이름)", allow: ["banmal"] },
  { id: "neo", label: "너", allow: ["banmal"] },
  { id: "jane", label: "자네", allow: ["banmal"] },
];

const GENDERS = [
  { id: "female", label: "여성" },
  { id: "male", label: "남성" },
  { id: "neutral", label: "중립" },
] as const;
const AGES = [
  { id: "20s", label: "20대" },
  { id: "30s", label: "30대" },
  { id: "40s", label: "40대" },
  { id: "50s", label: "50대" },
  { id: "60s_plus", label: "60대+" },
] as const;
const DIFFICULTIES = [
  { id: "easy", label: "쉽게", desc: "용어 최소·비유 위주" },
  { id: "standard", label: "표준", desc: "용어+풀이 병기" },
  { id: "expert", label: "전문가", desc: "원전 용어·근거 경로" },
] as const;

interface Props {
  value: PersonaConfig;
  onChange: (v: PersonaConfig) => void;
}

export function StepPersona({ value, onChange }: Props) {
  const politeness = value.speech.politeness;

  function setPoliteness(p: "jondae" | "banmal") {
    const style = STYLE_BY_POLITENESS[p][0].id;
    // 호칭이 새 politeness와 충돌하면 기본값으로 보정.
    const cur = value.user_honorific.preset_id;
    const ok = HONORIFICS.find((h) => h.id === cur)?.allow.includes(p);
    const preset: Preset = ok ? (cur as Preset) : p === "jondae" ? "name_nim" : "name_only";
    onChange({
      ...value,
      speech: { politeness: p, style },
      user_honorific: { type: "preset", preset_id: preset },
    });
  }

  return (
    <div className="space-y-5 text-sm">
      <Row label="상담가 성별">
        {GENDERS.map((g) => (
          <Chip
            key={g.id}
            active={value.counselor_gender === g.id}
            onClick={() => onChange({ ...value, counselor_gender: g.id })}
          >
            {g.label}
          </Chip>
        ))}
      </Row>

      <Row label="상담가 연령대">
        {AGES.map((a) => (
          <Chip
            key={a.id}
            active={value.counselor_age_band === a.id}
            onClick={() => onChange({ ...value, counselor_age_band: a.id })}
          >
            {a.label}
          </Chip>
        ))}
      </Row>

      <Row label="높임말">
        {(["jondae", "banmal"] as const).map((p) => (
          <Chip key={p} active={politeness === p} onClick={() => setPoliteness(p)}>
            {p === "jondae" ? "존댓말" : "반말"}
          </Chip>
        ))}
      </Row>

      <Row label="말투">
        {STYLE_BY_POLITENESS[politeness].map((s) => (
          <Chip
            key={s.id}
            active={value.speech.style === s.id}
            onClick={() => onChange({ ...value, speech: { politeness, style: s.id } })}
          >
            {s.label}
          </Chip>
        ))}
      </Row>

      <Row label="호칭">
        {HONORIFICS.filter((h) => h.allow.includes(politeness)).map((h) => (
          <Chip
            key={h.id}
            active={value.user_honorific.preset_id === h.id}
            onClick={() =>
              onChange({ ...value, user_honorific: { type: "preset", preset_id: h.id } })
            }
          >
            {h.label}
          </Chip>
        ))}
      </Row>

      <div>
        <span className="mb-1 block font-medium">설명 난이도</span>
        <div className="grid gap-2 sm:grid-cols-3">
          {DIFFICULTIES.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => onChange({ ...value, difficulty: d.id })}
              className={`rounded border p-2 text-left ${
                value.difficulty === d.id ? "border-gray-800 ring-1 ring-gray-800" : ""
              }`}
            >
              <span className="block font-medium">{d.label}</span>
              <span className="block text-xs text-gray-400">{d.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-gray-400">
        페르소나는 계정 전체 풀이에 동일하게 적용되는 말투 설정이에요. 점수·날짜·간지 같은 사실에는
        영향을 주지 않습니다.
      </p>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="mb-1 block font-medium">{label}</span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 ${
        active ? "border-gray-800 bg-gray-800 text-white" : "text-gray-600"
      }`}
    >
      {children}
    </button>
  );
}
