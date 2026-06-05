import { InfoTooltip } from "@/components/layout/InfoTooltip";
import { elementLabel } from "@/lib/elements";
import type { ManseResult } from "@/lib/types";

// 백엔드 응답에 일부 필드가 없어도(구버전/부분 데이터) 깨지지 않도록 방어.
function ent(obj: Record<string, number> | undefined | null): [string, number][] {
  return Object.entries(obj ?? {});
}

function Card({ title, info, children }: { title: string; info?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 flex items-center text-sm font-semibold">
        {title}
        {info && <InfoTooltip text={info} />}
      </h2>
      {children}
    </section>
  );
}

export function BirthSummaryBar({ result }: { result: ManseResult }) {
  const s = result.input_summary as Record<string, unknown>;
  const cal = s.calendar_type === "lunar" ? "음력" : "양력";
  const time = s.birth_time_unknown ? "시간 모름" : String(s.birth_time ?? "");
  const dir = s.daewoon_direction === "forward" ? "순행대운" : s.daewoon_direction === "backward" ? "역행대운" : "";
  return (
    <div className="rounded-lg bg-gray-900 p-3 text-sm text-white">
      ({cal}) {String(s.birth_date)} {time} · {String(s.birth_place_name)} ·{" "}
      {s.gender === "male" ? "남성" : s.gender === "female" ? "여성" : ""} {dir}
    </div>
  );
}

export function TrueSolarTimeCard({ result }: { result: ManseResult }) {
  const tc = result.time_correction as Record<string, unknown> | null;
  if (!tc) return null;
  const changed = Boolean(tc.hour_pillar_changed_by_true_solar_time);
  return (
    <Card title="시간 보정 · 진태양시" info="법정시→표준시(서머타임 제거)→경도보정→균시차→진태양시 순으로 계산합니다.">
      <ul className="space-y-1 text-xs text-gray-600">
        <li>표준시 offset: {String(tc.timezone_offset_minutes)}분 · 서머타임: {tc.daylight_saving_applied ? "적용" : "미적용"}</li>
        <li>경도보정: {String(tc.longitude_correction_minutes)}분 · 균시차: {String(tc.equation_of_time_minutes)}분</li>
        <li>진태양시: {String(tc.true_solar_datetime)}</li>
        {changed && (
          <li className="rounded bg-amber-100 p-1 text-amber-800">
            ⚠ 진태양시 적용으로 시주 변경: {String(tc.standard_time_hour_pillar)}(일반시) → {String(tc.true_solar_time_hour_pillar)}(진태양시)
          </li>
        )}
      </ul>
    </Card>
  );
}

export function QuickSummaryBar({ result }: { result: ManseResult }) {
  const fe = result.force_analysis.five_elements;
  const st = result.force_analysis.strength;
  const gong = result.pillars.gongmang_branches.join("");
  const amjang = fe.hidden_only_elements ?? [];
  return (
    <Card title="요약" info="화면 오행은 천간·지지에 실제 드러난 글자 기준(표면)입니다. 지장간에만 있는 오행은 '암장'으로 따로 표기하며 퍼센트에서 제외합니다(예: 木 0%). 부족한 오행이 곧 용신은 아닙니다.">
      <div className="text-xs text-gray-700">
        <div>오행(표면): {ent(fe.visible_percent ?? fe.effective_percent).map(([e, v]) => `${elementLabel(e)} ${v}%`).join(" · ")}</div>
        {amjang.length > 0 && (
          <div className="mt-1 text-gray-500">
            암장: {amjang.map((h) => `${elementLabel(h.element)}(${h.sources.join(",")})`).join(" · ")}
          </div>
        )}
        <div className="mt-1">공망: {gong} · 신강약: <b>{st.band}</b> ({st.score}점){st.requires_validation && " · 검증 필요"}</div>
      </div>
    </Card>
  );
}

export function StrengthPanel({ result }: { result: ManseResult }) {
  const st = result.force_analysis.strength;
  const b = st.basis;
  return (
    <Card title="신강/신약 9단계" info="통근(지장간 뿌리)과 득지(일지가 일간을 직접 지지)는 다릅니다. 뿌리가 튼튼해도(신왕) 신강은 아닙니다.">
      <p className="text-sm">
        <b>{st.band}</b> · {st.score}점 · 신뢰도 {st.confidence}
        {st.borderline && " · 경계값"}
      </p>
      <p className="mt-1 text-xs text-gray-600">
        득령 {b.deukryeong ? "O" : "X"} · 득지 {b.deukji ? "O" : "X"} · 득세 {b.deukse ? "O" : "X"} · 통근 {b.tonggeun ? "O" : "X"}
      </p>
      <p className="mt-1 text-[11px] text-gray-400">
        구성: {ent(st.components).map(([k, v]) => `${k} ${v}`).join(" · ")}
      </p>
    </Card>
  );
}

export function DistributionPanel({ result }: { result: ManseResult }) {
  const fe = result.force_analysis.five_elements;
  const tg = result.force_analysis.ten_gods;
  const amjang = fe.hidden_only_elements ?? [];
  return (
    <Card title="오행 · 십성 분포" info="표면=천간·지지에 실제 드러난 글자 기준(단순 카운트). 실세력=지장간에 자리별 가중치(月支 중심)+월령·통근·공망을 반영한 비중. 암장=지장간에만 있는 잠재 요소(표면 %엔 미포함). 표면과 실세력을 함께 봅니다.">
      <div className="space-y-2 text-xs text-gray-700">
        <div className="space-y-1">
          <div className="font-semibold text-gray-500">표면 (드러난 글자)</div>
          <div>오행: {ent(fe.visible_percent ?? fe.effective_percent).map(([e, v]) => `${elementLabel(e)} ${v}%`).join(" · ")}</div>
          <div>
            십성(일간 제외): {ent(tg.visible_percent).filter(([, v]) => v > 0)
              .map(([k, v]) => `${k} ${v}%`).join(" · ")}
            {(tg.visible_absent ?? []).length > 0 && (
              <span className="text-gray-400"> · 없음: {(tg.visible_absent ?? []).join("·")}</span>
            )}
          </div>
        </div>
        <div className="space-y-1">
          <div className="font-semibold text-gray-500">실세력 (지장간 자리별 가중)</div>
          <div>오행: {ent(fe.effective_percent).map(([e, v]) => `${elementLabel(e)} ${v}%`).join(" · ")}</div>
          <div>십성그룹: {ent(tg.groups).map(([k, v]) => `${k} ${Math.round(v)}`).join(" · ")}</div>
        </div>
        {amjang.length > 0 && (
          <div className="text-gray-500">
            암장(지장간만): {amjang.map((h) => `${elementLabel(h.element)}(${h.sources.join(",")})`).join(" · ")} — 작동성 낮음
          </div>
        )}
        {fe.hidden_support && Object.keys(fe.hidden_support).length > 0 && (
          <div className="text-gray-400">
            지장간 보조: {Object.entries(fe.hidden_support)
              .map(([e, src]) => `${elementLabel(e)}←${src.join(",")}`).join(" · ")}
          </div>
        )}
      </div>
    </Card>
  );
}

export function GeokgukPanel({ result }: { result: ManseResult }) {
  const g = result.geokguk as Record<string, unknown>;
  return (
    <Card title="격국" info="격국은 참고 레이어이며 단독으로 용신을 확정하지 않습니다.">
      <p className="text-sm"><b>{String(g.main_structure)}</b> · 성격 {String(g.formation_level)}</p>
      <ul className="mt-1 list-disc pl-4 text-xs text-gray-600">
        {(g.auxiliary_structures as string[] | undefined)?.map((a) => <li key={a}>{a}</li>)}
      </ul>
    </Card>
  );
}

export function StructurePanel({ result }: { result: ManseResult }) {
  const items = result.structure_analysis.interactions;
  const gm = result.structure_analysis.gongmang as Record<string, unknown> | null;
  return (
    <Card title="구조 작용 (합충형파해)" info="길흉 단정이 아니라 작동성·변동성·안정도에 주는 영향입니다.">
      <ul className="space-y-0.5 text-xs text-gray-700">
        {items.length === 0 && <li className="text-gray-400">특이 관계 없음</li>}
        {items.map((i, idx) => (
          <li key={idx}>
            {String(i.relation_type)} {(i.members as string[]).join("-")} ({(i.positions as string[]).join(",")})
          </li>
        ))}
      </ul>
      {gm && (
        <p className="mt-2 text-[11px] text-gray-500">
          공망(일공망): {(gm.day_basis_empty_branches as string[]).join("")} · 년공망(참조): {(gm.year_basis_empty_branches as string[]).join("")}
        </p>
      )}
    </Card>
  );
}

export function SinsalPanel({ result }: { result: ManseResult }) {
  const sinsal = result.traditional_extras?.sinsal?.full_list ?? [];
  return (
    <Card title="전체 신살" info="신살은 모두 표시하되 용신·신강약·격국 결정의 핵심 근거로 쓰지 않습니다(해석 보조).">
      <div className="flex flex-wrap gap-1">
        {sinsal.map((s, i) => (
          <span key={i} className="rounded border px-2 py-0.5 text-[11px]" title={s.basis}>
            {s.name}
            <span className="ml-1 text-gray-400">{s.position}·{s.intensity}</span>
          </span>
        ))}
      </div>
    </Card>
  );
}

export function LuckPanel({ result }: { result: ManseResult }) {
  const lc = result.luck_cycles;
  if (!lc) return null;
  return (
    <Card title="대운 · 세운 · 월운" info="운은 원국을 바꾸지 않는 별도 레이어이며 용신 관계로 표시합니다.">
      <p className="text-xs text-gray-600">
        {lc.direction === "forward" ? "순행" : "역행"} · 대운수 {lc.start_age}세
        {lc.current_age != null && ` · 현재 ${lc.current_age}세`}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-center text-[11px]">
          <thead className="text-gray-400">
            <tr><th>나이</th><th>간지</th><th>십성</th><th>운성</th><th>용신관계</th></tr>
          </thead>
          <tbody>
            {lc.daewoon_table.map((d) => (
              <tr key={d.index} className={d.index === lc.current_daewoon_index ? "bg-yellow-50 font-semibold" : ""}>
                <td>{d.start_age}</td>
                <td>{d.ganji}</td>
                <td>{d.stem_ten_god}/{d.branch_ten_god}</td>
                <td>{d.twelve_unseong}</td>
                <td>{d.yongsin_relation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {lc.yearly_luck.length > 0 && (
        <p className="mt-2 text-[11px] text-gray-500">
          세운: {lc.yearly_luck.map((y) => `${y.label} ${y.ganji}(${y.yongsin_alignment})`).join(" · ")}
        </p>
      )}
      {lc.monthly_luck.length > 0 && (
        <p className="mt-1 text-[11px] text-gray-500">
          월운: {lc.monthly_luck.map((m) => `${m.label} ${m.ganji}`).join(" · ")}
        </p>
      )}
      {lc.daily_luck.length > 0 && (
        <p className="mt-1 text-[11px] text-gray-500">
          일운: {lc.daily_luck.slice(0, 5).map((d) => `${d.label.slice(5)} ${d.ganji}`).join(" · ")}
          {lc.daily_luck.length > 5 && ` … (총 ${lc.daily_luck.length}일)`}
        </p>
      )}
      {lc.yearly_luck.length === 0 && (
        <p className="mt-2 text-[11px] text-gray-400">
          세운/월운/일운은 기준일(오늘)이 있을 때 표시됩니다.
        </p>
      )}
    </Card>
  );
}
