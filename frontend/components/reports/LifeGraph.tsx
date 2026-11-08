"use client";

// 인생 그래프(총운 2부 첫 화면, 2026-11-07) — 백엔드 엔진이 확정한 대운 곡선·세운 선·주요
// 이벤트 마커를 인라인 SVG로 그린다. 차트 라이브러리 없이 동작하며, 값은 재계산하지 않는다.

export interface LifeGraphMarker {
  year: number;
  age: number;
  ganji: string;
  kind: string; // romance | marriage | job | career_change | relocation | wealth_gain | crisis_health | crisis_money
  kind_ko: string;
  event_key: string;
  score: number;
  tone: string;
  daewoon_index: number;
  risk_backed?: boolean;
  note?: string;
}

export interface LifeGraphDaewoon {
  index: number;
  ganji: string;
  stem_ten_god: string;
  branch_ten_god: string;
  start_age: number;
  end_age: number;
  start_year: number;
  end_year: number;
  score: number;
  label: string;
  status: string; // past | current | future | unknown
  partner_star_daewoon?: boolean; // 배우자성 대운(통설 라벨)
  mean_total?: number; // (세운+대운) 연 평균 — 누적 운세선 설명용
  trend_delta?: number | null; // 직전 대운 대비 차이
  trend?: string; // 상승 | 하강 | 보합 | 시작
  markers: LifeGraphMarker[];
}

export interface LifeGraphYear {
  year: number;
  age: number;
  ganji: string;
  score: number;
  label: string;
  cumulative?: number; // 누적 운세선 — 출생부터 (세운+대운)을 더해 온 값(주식 차트의 가격선)
}

export interface LifeGraphWindow {
  kind: string;
  kind_ko: string;
  start_year: number;
  end_year: number;
  start_age: number;
  end_age: number;
  peak_year: number;
  peak_score: number;
  years_count: number;
}

export interface LifeGraphData {
  birth_year: number;
  end_year: number;
  current_daewoon_index?: number | null;
  daewoons: LifeGraphDaewoon[];
  years: LifeGraphYear[];
  markers: LifeGraphMarker[];
  positive_windows?: LifeGraphWindow[]; // 오늘 이후 긍정 창(결혼·취업·이직·재물 유입·이사)
  today_year?: number | null; // 오늘 연도 — '오늘' 세로선
  cumulative_peak_year?: number | null;
  cumulative_low_year?: number | null;
  today_cumulative_percentile?: number | null;
}

const TREND_SYMBOL: Record<string, string> = { 상승: "↗", 하강: "↘", 보합: "→" };

const MARKER_STYLE: Record<string, { symbol: string; color: string }> = {
  romance: { symbol: "♡", color: "#f472b6" },
  marriage: { symbol: "♥", color: "#d946ef" },
  job: { symbol: "●", color: "#2563eb" },
  career_change: { symbol: "➤", color: "#0891b2" },
  relocation: { symbol: "⌂", color: "#16a34a" },
  wealth_gain: { symbol: "◆", color: "#ca8a04" },
  crisis_health: { symbol: "✚", color: "#dc2626" },
  crisis_money: { symbol: "₩", color: "#ea580c" },
};
const KIND_ORDER = [
  "romance",
  "marriage",
  "job",
  "career_change",
  "relocation",
  "wealth_gain",
  "crisis_health",
  "crisis_money",
];

/** 마커 메모의 화면 표기 — 엔진 메모는 LLM 입력용이라 그대로 보이면 군더더기다(2026-11-07).
 *  결혼 2축 메모('인연 창 ○ · 운의 결 …')는 '결' 열이 이미 담당하므로 숨기고, 미성년 메모만 짧게. */
function displayNote(note?: string): string {
  if (!note) return "";
  if (note.startsWith("인연 창")) return "";
  if (note.startsWith("미성년")) return " — 가족 단위로 읽기";
  return ` — ${note}`;
}

/** 데이터 형태가 맞는지 최소 검증 — 아니면 그리지 않는다(마크다운 본문만 표시). */
export function isLifeGraphData(v: unknown): v is LifeGraphData {
  if (!v || typeof v !== "object") return false;
  const d = v as Partial<LifeGraphData>;
  return (
    typeof d.birth_year === "number" &&
    typeof d.end_year === "number" &&
    Array.isArray(d.daewoons) &&
    Array.isArray(d.years) &&
    Array.isArray(d.markers)
  );
}

export function LifeGraph({ data }: { data: LifeGraphData }) {
  const W = 920;
  const H = 300;
  const padL = 36;
  const padR = 16;
  const padT = 44;
  const padB = 54;
  const ageMin = 0;
  const ageMax = Math.max(1, data.end_year - data.birth_year);
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const x = (age: number) => padL + ((age - ageMin) / (ageMax - ageMin)) * plotW;

  const scores = [...data.years.map((y) => y.score), ...data.daewoons.map((d) => d.score)];
  const sMin = scores.length ? Math.min(...scores) : -1;
  const sMax = scores.length ? Math.max(...scores) : 1;
  const span = sMax - sMin || 1;
  const y = (s: number) => padT + (1 - (s - sMin) / span) * plotH;
  const yZero = sMin <= 0 && sMax >= 0 ? y(0) : null;

  const yearPath = data.years
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.age).toFixed(1)},${y(p.score).toFixed(1)}`)
    .join(" ");
  // 누적 운세선(2026-11-08, 주식 차트형) — 자체 세로 척도. 과거 계약 데이터(cumulative 없음)는 생략.
  const cumYears = data.years.filter((p) => typeof p.cumulative === "number");
  const cums = cumYears.map((p) => p.cumulative as number);
  const cMin = cums.length ? Math.min(...cums) : 0;
  const cMax = cums.length ? Math.max(...cums) : 1;
  const cSpan = cMax - cMin || 1;
  const yC = (c: number) => padT + 6 + (1 - (c - cMin) / cSpan) * (plotH - 12);
  const cumPath =
    cumYears.length >= 2
      ? cumYears
          .map(
            (p, i) =>
              `${i === 0 ? "M" : "L"}${x(p.age).toFixed(1)},${yC(p.cumulative as number).toFixed(1)}`,
          )
          .join(" ")
      : "";

  const current = data.current_daewoon_index ?? null;
  const kindsPresent = KIND_ORDER.filter((k) => data.markers.some((m) => m.kind === k));

  return (
    <figure className="my-3 print:break-inside-avoid">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="인생 그래프 — 대운 흐름과 주요 이벤트 시기"
          className="min-w-[640px] w-full"
        >
          {/* 대운 띠 — 점수에 따라 밝기, 현재 대운은 테두리 강조 */}
          {data.daewoons.map((d) => {
            const x0 = x(d.start_year - data.birth_year);
            const x1 = x(Math.min(d.end_year + 1 - data.birth_year, ageMax));
            const t = (d.score - sMin) / span; // 0..1
            const fill = `hsl(${Math.round(120 * t)}, 60%, ${Math.round(88 - 18 * t)}%)`;
            return (
              <g key={d.index}>
                <rect
                  x={x0}
                  y={padT}
                  width={Math.max(0, x1 - x0)}
                  height={plotH}
                  fill={fill}
                  stroke={current === d.index ? "#111827" : "#ffffff"}
                  strokeWidth={current === d.index ? 2 : 1}
                />
                <text
                  x={(x0 + x1) / 2}
                  y={padT - 22}
                  textAnchor="middle"
                  fontSize="11"
                  fill="#374151"
                >
                  {d.ganji}
                  {d.partner_star_daewoon ? " ♥" : ""}
                </text>
                <text
                  x={(x0 + x1) / 2}
                  y={padT - 9}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#6b7280"
                >
                  {d.start_age}–{d.end_age}세{current === d.index ? " · 현재" : ""}
                  {d.trend && TREND_SYMBOL[d.trend] ? ` ${TREND_SYMBOL[d.trend]}` : ""}
                </text>
              </g>
            );
          })}
          {/* 0선 */}
          {yZero !== null && (
            <line x1={padL} x2={W - padR} y1={yZero} y2={yZero} stroke="#9ca3af" strokeDasharray="4 3" />
          )}
          {/* 세운 선 */}
          {yearPath && <path d={yearPath} fill="none" stroke="#1f2937" strokeWidth={1.2} opacity={0.85} />}
          {/* 누적 운세선 — 쌓인 수준·기울기(주식 차트의 가격선) + 기준선(누적 0 = 보통선) */}
          {cumPath && cMin <= 0 && cMax >= 0 && (
            <g>
              <line x1={padL} x2={W - padR} y1={yC(0)} y2={yC(0)} stroke="#2563eb" strokeWidth={0.8} strokeDasharray="1 3" opacity={0.7} />
              <text x={W - padR - 2} y={yC(0) - 3} textAnchor="end" fontSize="9" fill="#2563eb">
                보통선
              </text>
            </g>
          )}
          {cumPath && (
            <path d={cumPath} fill="none" stroke="#2563eb" strokeWidth={1.8} strokeDasharray="6 3" opacity={0.9} />
          )}
          {/* 오늘 — 지난 시기와 앞으로의 시기를 가르는 세로선 */}
          {typeof data.today_year === "number" &&
            data.today_year - data.birth_year >= ageMin &&
            data.today_year - data.birth_year <= ageMax && (
              <g>
                <line
                  x1={x(data.today_year - data.birth_year)}
                  x2={x(data.today_year - data.birth_year)}
                  y1={padT}
                  y2={padT + plotH}
                  stroke="#111827"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                />
                <text
                  x={x(data.today_year - data.birth_year) + 3}
                  y={padT + 10}
                  fontSize="9"
                  fill="#111827"
                >
                  오늘
                </text>
              </g>
            )}
          {/* 마커 */}
          {data.markers.map((m, i) => {
            const st = MARKER_STYLE[m.kind] ?? { symbol: "•", color: "#111827" };
            const yr = data.years.find((p) => p.year === m.year);
            const my = yr ? y(yr.score) : padT + plotH / 2;
            const stack = data.markers.filter((o) => o.year === m.year && KIND_ORDER.indexOf(o.kind) < KIND_ORDER.indexOf(m.kind)).length;
            return (
              <g key={`${m.year}-${m.kind}-${i}`}>
                <line x1={x(m.age)} x2={x(m.age)} y1={my} y2={padT + plotH} stroke={st.color} strokeWidth={0.6} opacity={0.5} />
                <text
                  x={x(m.age)}
                  y={my - 8 - stack * 13}
                  textAnchor="middle"
                  fontSize="13"
                  fill={st.color}
                  fontWeight="bold"
                >
                  {st.symbol}
                </text>
              </g>
            );
          })}
          {/* 나이 눈금 */}
          {Array.from({ length: Math.floor(ageMax / 10) + 1 }, (_, k) => k * 10).map((age) => (
            <g key={age}>
              <line x1={x(age)} x2={x(age)} y1={padT + plotH} y2={padT + plotH + 4} stroke="#6b7280" />
              <text x={x(age)} y={padT + plotH + 16} textAnchor="middle" fontSize="10" fill="#4b5563">
                {age}세
              </text>
              <text x={x(age)} y={padT + plotH + 28} textAnchor="middle" fontSize="9" fill="#9ca3af">
                {data.birth_year + age}
              </text>
            </g>
          ))}
          {/* 세로축 라벨 */}
          <text x={padL - 4} y={padT + 10} textAnchor="end" fontSize="9" fill="#6b7280">좋음</text>
          <text x={padL - 4} y={padT + plotH} textAnchor="end" fontSize="9" fill="#6b7280">부담</text>
        </svg>
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600">
        <span>띠 = 대운(밝을수록 좋은 흐름) · 선 = 해마다의 운</span>
        {cumPath && (
          <span style={{ color: "#2563eb" }}>
            점선 = 누적 운세선(해마다의 운을 쌓아 온 선 — 올라가면 이전보다 좋아지는 중, 보통선 위면 쌓인
            운이 플러스, ↗↘→ = 대운 추세)
          </span>
        )}
        {kindsPresent.map((k) => (
          <span key={k} style={{ color: MARKER_STYLE[k].color }}>
            {MARKER_STYLE[k].symbol} {data.markers.find((m) => m.kind === k)?.kind_ko}
          </span>
        ))}
      </figcaption>
      {/* 마커 표 — 그림과 같은 값, 인쇄·접근성용 */}
      {data.markers.length > 0 && (
        <table className="mt-2 w-full text-xs">
          <thead>
            <tr className="bg-gray-50">
              <th className="border px-2 py-1 text-left">시기</th>
              <th className="border px-2 py-1 text-left">이벤트</th>
              <th className="border px-2 py-1 text-left">결</th>
              <th className="border px-2 py-1 text-left">대운</th>
            </tr>
          </thead>
          <tbody>
            {data.markers.map((m, i) => {
              const dw = data.daewoons.find((d) => d.index === m.daewoon_index);
              return (
                <tr key={`${m.year}-${m.kind}-${i}`}>
                  <td className="border px-2 py-1">{m.year}년 · 만 {m.age}세 · {m.ganji}</td>
                  <td className="border px-2 py-1">
                    <span style={{ color: MARKER_STYLE[m.kind]?.color }}>{MARKER_STYLE[m.kind]?.symbol}</span>{" "}
                    {m.kind_ko}
                    {m.risk_backed ? " (주의 신호 동반)" : ""}
                    {displayNote(m.note)}
                  </td>
                  <td className="border px-2 py-1">{m.tone}</td>
                  <td className="border px-2 py-1">{dw ? `${dw.ganji} ${dw.start_age}–${dw.end_age}세` : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {/* 앞으로의 긍정 창 — 마커 상한과 무관한 게이트 통과 연도 묶음(가장 가까운 창부터) */}
      {(data.positive_windows?.length ?? 0) > 0 && (
        <div className="mt-2 text-xs text-gray-700">
          <div className="font-medium">앞으로 기대할 시기</div>
          <ul className="mt-1 list-disc pl-4">
            {KIND_ORDER.filter((k) => data.positive_windows!.some((w) => w.kind === k)).map((k) => {
              const ws = data.positive_windows!.filter((w) => w.kind === k).slice(0, 3);
              return (
                <li key={k}>
                  <span style={{ color: MARKER_STYLE[k]?.color }}>{MARKER_STYLE[k]?.symbol}</span>{" "}
                  {ws[0].kind_ko}:{" "}
                  {ws
                    .map((w) =>
                      w.start_year === w.end_year
                        ? `${w.start_year}년(만 ${w.start_age}세)`
                        : `${w.start_year}–${w.end_year}년(만 ${w.start_age}–${w.end_age}세)`,
                    )
                    .join(" · ")}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </figure>
  );
}
