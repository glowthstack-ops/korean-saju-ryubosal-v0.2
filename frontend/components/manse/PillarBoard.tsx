import { ELEMENT_KO, elementLabel, elementStyle, ganjiKo, naeumElement, yinyangSign } from "@/lib/elements";
import { JA_HOUR_RULE_LABEL, type JaHourRule, type ManseResult, type Pillar } from "@/lib/types";
import { GhostOverlay } from "./HourUnknown";

// 시주 미상일 때 보여 주는 흐린 예시 — 실제 데이터가 아니다(블러+반투명 레이어 아래 자리만 잡는다).
const GHOST_HOUR_PILLAR: Pillar = {
  stem: "丙", branch: "午", ganji: "丙午",
  stem_element: "火", branch_element: "火", stem_yinyang: "양", branch_yinyang: "양",
  stem_ten_god: "편인", branch_main_ten_god: "정인", twelve_unseong: "제왕",
  hidden_stems: [
    { stem: "丙", type: "residual", element: "火", weight: 0.3 },
    { stem: "己", type: "middle", element: "土", weight: 0.2 },
    { stem: "丁", type: "main", element: "火", weight: 0.5 },
  ],
  naeum: "天河水", gongmang_hit: false, palace: "자녀궁",
} as unknown as Pillar;

function Cell(
  { char, ko, element, mark, sub, isVoid = false }:
  { char: string; ko: string; element: string; mark: string; sub: string; isVoid?: boolean },
) {
  return (
    <div className={`relative rounded border border-gray-200 p-2 text-center ${elementStyle(element)}`}>
      {/* 음양·공망은 absolute 코너 배치 → 메인 글자 중앙정렬에 영향 없음 */}
      {isVoid && (
        <span
          className="absolute left-1 top-1 text-[12px] font-bold leading-none opacity-90"
          title="공망"
          aria-label="공망"
        >⊘</span>
      )}
      <span className="absolute right-1 top-1 text-[10px] font-medium leading-none opacity-90">{mark}</span>
      <div className="text-2xl font-bold leading-none">{char}</div>
      <div className="text-[11px] opacity-80">{ko}</div>
      <div className="mt-1 text-[11px]">{sub}</div>
    </div>
  );
}

// 지지 음양 표기는 본기(정기) 지장간 기준. 없으면 첫 지장간으로 폴백.
function _mainHidden(p: Pillar): string {
  return (p.hidden_stems.find((h) => h.type === "main") ?? p.hidden_stems[0])?.stem ?? "";
}

function Column({ title, p, ghost = false }: { title: string; p: Pillar | null; ghost?: boolean }) {
  if (!p) {
    // 시간 모름 — 빈칸 대신 흐린 예시 위에 반투명 레이어를 덮어 '여기에 시주 정보가 들어온다'는
    // 것을 보여 준다(2026-10-06 데굴님 지시). 예시 글자는 실제 데이터가 아니다.
    return (
      <GhostOverlay
        className="flex-1"
        label="시주 미상 · 산출 불가"
        sub="출생시간을 입력하면 시주·십성·지장간·운성이 여기에 표시돼요"
      >
        <Column title={title} p={GHOST_HOUR_PILLAR} ghost />
      </GhostOverlay>
    );
  }
  return (
    <div className={`flex-1 rounded-lg border bg-white p-2 ${ghost ? "h-full" : ""}`}>
      <div className="mb-2 text-center text-xs font-semibold text-gray-500">{title}</div>
      <div className="space-y-1">
        <Cell
          char={p.stem} ko={ganjiKo(p.stem)} element={p.stem_element}
          mark={`${yinyangSign(p.stem)}${ELEMENT_KO[p.stem_element] ?? ""}`}
          sub={p.stem_ten_god}
        />
        <Cell
          char={p.branch} ko={ganjiKo(p.branch)} element={p.branch_element}
          mark={`${yinyangSign(_mainHidden(p))}${ELEMENT_KO[p.branch_element] ?? ""}`}
          sub={p.branch_main_ten_god} isVoid={p.gongmang_hit}
        />
      </div>
      <div className="mt-2 text-center text-[11px] text-gray-600">{p.twelve_unseong}</div>
      {/* 지장간: 여기·중기·정기 3슬롯 고정. 없는 단계(예: 중기)는 자리를 비워 정렬 유지. */}
      <div className="mt-1 flex justify-center gap-0.5">
        {(["residual", "middle", "main"] as const).map((stage) => {
          const h = p.hidden_stems.find((x) => x.type === stage);
          if (!h) {
            return (
              <span key={stage} className="invisible rounded px-1 text-[10px] leading-tight">　</span>
            );
          }
          return (
            <span
              key={stage}
              className={`rounded px-1 text-[10px] leading-tight ${elementStyle(h.element)}`}
            >
              {h.stem}
            </span>
          );
        })}
      </div>
      <div className="mt-1 text-center text-[10px] text-gray-400">{p.palace}</div>
      {/* 납음오행 — 박스 하단(구분선 아래) 색배지. */}
      {p.naeum && (
        <div className="mt-1.5 border-t pt-1.5 text-center">
          <span className={`rounded px-1.5 py-0.5 text-[10px] ${elementStyle(naeumElement(p.naeum))}`}>
            {p.naeum}
          </span>
        </div>
      )}
    </div>
  );
}

export function PillarBoard({
  result,
  applyEquationOfTime,
  onSelectVariant,
}: {
  result: ManseResult;
  /** 균시차 적용 여부 — 엔진 응답에는 적용 플래그가 없어 화면 상태를 받는다. 미전달 시 배지 생략. */
  applyEquationOfTime?: boolean;
  /** 경계 당일 명식 변형 선택(그 변형의 시진 목록, null=해제) — 저장·재계산은 호출 측 책임. */
  onSelectVariant?: (hourBranches: string[] | null) => void;
}) {
  const { year, month, day, hour, day_master } = result.pillars;
  const hu = hour === null ? result.hour_unknown ?? null : null;
  const variants = hu?.pillar_variants ?? [];
  const DIR_KO: Record<string, string> = { forward: "순행", backward: "역행" };
  // 자시 규칙은 엔진이 실제로 쓴 값(time_correction.ja_hour_rule)을 그대로 표시한다.
  // "none"은 엔진에서 standard_zi와 동일 동작이라 정자시로 표기.
  const tc = result.time_correction as Record<string, unknown> | null;
  const jaRule: JaHourRule =
    tc?.ja_hour_rule === "early_late_zi" ? "early_late_zi" : "standard_zi";
  // 원국에서 실제 공망에 해당하는 지지(중복 제거).
  const voidChars = [...new Set(
    [hour, day, month, year].filter((p) => p?.gongmang_hit).map((p) => p!.branch),
  )];
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">사주 원국 (일간 {day_master}·{ganjiKo(day_master)})</h2>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
        <span className="flex items-center gap-1">
          <span className="text-gray-400">오행</span>
          {["木", "火", "土", "金", "水"].map((e) => (
            <span key={e} className={`rounded px-1.5 py-0.5 ${elementStyle(e)}`}>
              {elementLabel(e)}
            </span>
          ))}
        </span>
        <span className="flex items-center gap-1 text-gray-500">
          <span className="font-bold text-gray-700">⊘</span>
          공망{voidChars.length ? `: ${voidChars.map((c) => `${c}(${ganjiKo(c)})`).join(", ")}` : " 없음"}
        </span>
        {/* 이 명식이 어떤 시간 옵션으로 계산됐는지 — 진태양시 카드의 선택과 항상 일치한다.
            좁은 폭에서는 범례 아래 한 줄을 통째로 차지(왼쪽 정렬), sm 이상에서만 오른쪽 끝에 붙인다. */}
        <span className="flex basis-full items-center gap-1 text-gray-500 sm:ml-auto sm:basis-auto">
          {applyEquationOfTime !== undefined && (
            <span className="rounded bg-gray-100 px-1.5 py-0.5">
              균시차 {applyEquationOfTime ? "적용" : "미적용"}
            </span>
          )}
          <span className="rounded bg-gray-100 px-1.5 py-0.5">{JA_HOUR_RULE_LABEL[jaRule]}</span>
        </span>
      </div>
      {variants.length > 1 && (
        // 경계 당일(입춘·절입·일 경계) — 출생시각에 따라 명식 자체가 갈린다. 변형별 핵심 사실을 나란히
        // 보여 주고 '이 변형으로 보기'로 표시 명식을 바꾼다(보기 선택일 뿐 확정이 아니다, 2026-10-06).
        <div className="mb-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          <p className="mb-1 font-medium">
            명식 분기 · 경계 당일이라 출생시각에 따라 명식이 {variants.length}갈래예요. 현재 표시 중인 명식은
            확정이 아니에요.
          </p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {variants.map((v, i) => (
              <div key={i} className={`rounded border bg-white p-2 ${v.is_base ? "border-rose-400" : "border-rose-100"}`}>
                <div className="flex items-center justify-between">
                  <b>[{String.fromCharCode(65 + i)}] {v.year_ganji}·{v.month_ganji}·{v.day_ganji}</b>
                  <span className="text-gray-500">{v.hour_branches.join("")}시</span>
                </div>
                <div className="mt-0.5 text-gray-700">
                  일간 {v.day_master} · 강약 {v.strength_bands.join("/") || "-"} · 격국 {v.geokguks.join("/") || "-"}
                  {" · "}대운 {v.daewoon_directions.map((d) => DIR_KO[d] ?? d).join("/") || "-"}
                </div>
                <div className="mt-1 flex items-center gap-2">
                  {v.is_base ? (
                    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-rose-700">현재 표시</span>
                  ) : (
                    onSelectVariant && (
                      <button
                        onClick={() => onSelectVariant(v.hour_branches)}
                        className="rounded bg-rose-600 px-2 py-0.5 text-white hover:bg-rose-700"
                      >
                        이 변형으로 보기
                      </button>
                    )
                  )}
                  {v.is_base && hu?.variant_choice && onSelectVariant && (
                    <button onClick={() => onSelectVariant(null)} className="text-gray-500 underline">
                      선택 해제(정오 기준)
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <Column title="시주" p={hour} />
        <Column title="일주" p={day} />
        <Column title="월주" p={month} />
        <Column title="연주" p={year} />
      </div>
    </section>
  );
}
