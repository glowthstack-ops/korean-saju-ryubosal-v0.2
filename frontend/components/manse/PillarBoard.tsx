import { ELEMENT_KO, elementLabel, elementStyle, ganjiKo, yinyangSign } from "@/lib/elements";
import type { ManseResult, Pillar } from "@/lib/types";

function Cell(
  { char, ko, element, mark, sub, isVoid = false }:
  { char: string; ko: string; element: string; mark: string; sub: string; isVoid?: boolean },
) {
  return (
    <div className={`relative rounded p-2 text-center ${elementStyle(element)}`}>
      {/* 음양·공망은 absolute 코너 배치 → 메인 글자 중앙정렬에 영향 없음 */}
      {isVoid && (
        <span className="absolute left-1 top-1 rounded bg-rose-600 px-1 py-0.5 text-[10px] font-semibold leading-none text-white shadow">공망</span>
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

function Column({ title, p }: { title: string; p: Pillar | null }) {
  if (!p) {
    return (
      <div className="flex-1 rounded-lg border bg-white p-2 text-center">
        <div className="mb-2 text-xs font-semibold text-gray-500">{title}</div>
        <div className="rounded bg-gray-100 p-6 text-2xl text-gray-400">?</div>
        <div className="mt-2 text-[11px] text-gray-400">시간 모름</div>
      </div>
    );
  }
  return (
    <div className="flex-1 rounded-lg border bg-white p-2">
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
      <div className="mt-1 text-center text-[10px] text-gray-500">
        {p.hidden_stems.map((h) => `${h.stem}`).join(" ")}
      </div>
      <div className="mt-1 text-center text-[10px] text-gray-400">{p.palace}</div>
    </div>
  );
}

export function PillarBoard({ result }: { result: ManseResult }) {
  const { year, month, day, hour, day_master } = result.pillars;
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">사주 원국 (일간 {day_master}·{ganjiKo(day_master)})</h2>
      <div className="flex gap-2">
        <Column title="시주" p={hour} />
        <Column title="일주" p={day} />
        <Column title="월주" p={month} />
        <Column title="년주" p={year} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px]">
        <span className="text-gray-400">오행</span>
        {["木", "火", "土", "金", "水"].map((e) => (
          <span key={e} className={`rounded px-1.5 py-0.5 ${elementStyle(e)}`}>
            {elementLabel(e)}
          </span>
        ))}
      </div>
    </section>
  );
}
