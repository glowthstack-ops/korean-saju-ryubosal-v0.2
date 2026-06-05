import { elementLabel, elementStyle, ganjiKo } from "@/lib/elements";
import type { ManseResult, Pillar } from "@/lib/types";

function Cell({ char, ko, element, sub }: { char: string; ko: string; element: string; sub: string }) {
  return (
    <div className={`rounded p-2 text-center ${elementStyle(element)}`}>
      <div className="text-2xl font-bold leading-none">{char}</div>
      <div className="text-[11px] opacity-80">{ko}</div>
      <div className="mt-1 text-[11px]">{sub}</div>
    </div>
  );
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
      <div className="mb-2 text-center text-xs font-semibold text-gray-500">
        {title}
        {p.gongmang_hit && <span className="ml-1 rounded bg-gray-200 px-1 text-[10px]">공망</span>}
      </div>
      <div className="space-y-1">
        <Cell char={p.stem} ko={ganjiKo(p.stem)} element={p.stem_element} sub={p.stem_ten_god} />
        <Cell char={p.branch} ko={ganjiKo(p.branch)} element={p.branch_element} sub={p.branch_main_ten_god} />
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
      <p className="mt-1 text-[11px] text-gray-400">오행: {["木", "火", "土", "金", "水"].map(elementLabel).join(" ")}</p>
    </section>
  );
}
