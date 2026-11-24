// 민속 흉방 24방위 나침반(docs/19 §5-6, 2026-11-24 데굴님 승인).
// 세운 상세에서 그해 흉방이 실제로 걸치는 칸을 24방위(한 칸 15°)로 보여 준다 — 종전 표기는 동·서·남·북
// 한 글자뿐이라 '북서쪽 중 亥 한 칸만 해당' 같은 범위가 보이지 않았다.
// 어느 칸이 칠해지는지는 전부 엔진 값(FolkTabooHit.mountains)이다. 이 컴포넌트는 그리기만 한다.
import type { FolkTabooHit } from "@/lib/types";

// 24방위 — 정북(子)에서 시계 방향. 백엔드 saju_shared_types/compass24.MOUNTAINS_24 와 같은 표.
const MOUNTAINS_24 = [
  "子", "癸", "丑", "艮", "寅", "甲", "卯", "乙", "辰", "巽", "巳", "丙",
  "午", "丁", "未", "坤", "申", "庚", "酉", "辛", "戌", "乾", "亥", "壬",
] as const;
const DIRECTIONS_8 = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"] as const;

const SIZE = 220;
const C = SIZE / 2;
const R_IN = 60;
const R_OUT = 88;
const R_GLYPH = 74;
const R_LABEL = 100;

const FILL = {
  samsal: "#fecdd3", // rose-200
  daejanggun: "#fde68a", // amber-200
  overlap: "#fb7185", // rose-400 — 이사 판정층 2종 중첩
  none: "#fafaf9", // stone-50
} as const;

function point(r: number, deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [C + r * Math.sin(rad), C - r * Math.cos(rad)];
}

// 24방위 i번째 칸(중심 15i°, 폭 15°)의 고리 조각.
function sectorPath(i: number, rIn: number, rOut: number): string {
  const a0 = i * 15 - 7.5;
  const a1 = i * 15 + 7.5;
  const [x0, y0] = point(rOut, a0);
  const [x1, y1] = point(rOut, a1);
  const [x2, y2] = point(rIn, a1);
  const [x3, y3] = point(rIn, a0);
  const f = (n: number) => n.toFixed(2);
  return `M${f(x0)} ${f(y0)} A${rOut} ${rOut} 0 0 1 ${f(x1)} ${f(y1)} L${f(x2)} ${f(y2)} A${rIn} ${rIn} 0 0 0 ${f(x3)} ${f(y3)} Z`;
}

// 각도 표기 — 정북 0°·시계 방향. 정북을 넘는 구간은 시작 각이 더 크다(322.5°~37.5°).
export function folkDegreeLabel(h: FolkTabooHit): string {
  if (h.degree_from == null || h.degree_to == null) return "";
  const f = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
  return `${f(h.degree_from)}°~${f(h.degree_to)}°`;
}

export function FolkCompass({ move, ground }: { move: FolkTabooHit[]; ground: FolkTabooHit[] }) {
  const moveKeysAt = (m: string) => move.filter((h) => (h.mountains ?? []).includes(m)).map((h) => h.key);
  const groundAt = (m: string) => ground.some((h) => (h.mountains ?? []).includes(m));
  const summary = [...move, ...ground]
    .filter((h) => h.range_ko)
    .map((h) => `${h.name_ko} ${h.range_ko}`)
    .join(", ");
  return (
    <figure className="m-0 flex shrink-0 flex-col items-center">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="h-44 w-44"
        role="img"
        aria-label={`24방위 나침반 — ${summary}`}
      >
        {MOUNTAINS_24.map((m, i) => {
          const keys = moveKeysAt(m);
          const fill =
            keys.length >= 2
              ? FILL.overlap
              : keys[0] === "samsal"
                ? FILL.samsal
                : keys[0] === "daejanggun"
                  ? FILL.daejanggun
                  : FILL.none;
          const [gx, gy] = point(R_GLYPH, i * 15);
          return (
            <g key={m}>
              <path d={sectorPath(i, R_IN, R_OUT)} fill={fill} stroke="#d6d3d1" strokeWidth={0.6} />
              <text
                x={gx}
                y={gy}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={9.5}
                fontWeight={keys.length > 0 || groundAt(m) ? 700 : 400}
                fill={keys.length > 0 || groundAt(m) ? "#1c1917" : "#a8a29e"}
              >
                {m}
              </text>
            </g>
          );
        })}
        {/* 참고층(태세·세파) — 채우지 않고 점선 테두리로 겹쳐 그린다(이사 판정층 색을 가리지 않게). */}
        {MOUNTAINS_24.map((m, i) =>
          groundAt(m) ? (
            <path
              key={`g-${m}`}
              d={sectorPath(i, R_IN + 1.5, R_OUT - 1.5)}
              fill="none"
              stroke="#44403c"
              strokeWidth={1.6}
              strokeDasharray="3 2"
            />
          ) : null,
        )}
        {/* 8방위 경계(45° 간격) — 한 칸이 24방위 세 칸임을 보이는 굵은 구분선. */}
        {DIRECTIONS_8.map((d, k) => {
          const [x0, y0] = point(R_IN - 4, k * 45 + 22.5);
          const [x1, y1] = point(R_OUT + 4, k * 45 + 22.5);
          const [lx, ly] = point(R_LABEL, k * 45);
          return (
            <g key={d}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="#78716c" strokeWidth={1} />
              <text
                x={lx}
                y={ly}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={k % 2 === 0 ? 10.5 : 9}
                fontWeight={k % 2 === 0 ? 700 : 500}
                fill="#57534e"
              >
                {d}
              </text>
            </g>
          );
        })}
        <circle cx={C} cy={C} r={2.5} fill="#57534e" />
        <text x={C} y={C + 13} textAnchor="middle" fontSize={8.5} fill="#78716c">
          기준점(현재 집)
        </text>
      </svg>
      <figcaption className="mt-0.5 flex flex-wrap justify-center gap-x-2 gap-y-0.5 text-[10px] text-gray-500">
        <span><i className="mr-0.5 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: FILL.samsal }} />삼살방</span>
        <span><i className="mr-0.5 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: FILL.daejanggun }} />대장군방</span>
        {move.length >= 2 && MOUNTAINS_24.some((m) => moveKeysAt(m).length >= 2) && (
          <span><i className="mr-0.5 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: FILL.overlap }} />두 종 겹침</span>
        )}
        {ground.length > 0 && (
          <span><i className="mr-0.5 inline-block h-2 w-2 rounded-sm border border-dashed border-stone-700 align-middle" />태세·세파(참고)</span>
        )}
      </figcaption>
    </figure>
  );
}
