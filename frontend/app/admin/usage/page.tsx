"use client";

// 사용량·비용 — group_by(일자/surface/상품/모델/사용자)별 토큰·비용 표(USD·KRW).
// '상품' 기준은 섹션별 호출(RPT_FOCUS:W-01 등)을 상품 단위로 묶고, 펼치면 섹션 상세를 본다.

import { useEffect, useMemo, useState } from "react";
import { getUsageSummary, type GroupBy, type UsageRow } from "@/lib/admin";

const GROUPS: { v: GroupBy; label: string }[] = [
  { v: "day", label: "일자" },
  { v: "surface", label: "구분(채팅/리포트)" },
  { v: "product", label: "상품" },
  { v: "model", label: "모델" },
  { v: "owner", label: "사용자" },
];

interface Group {
  product: string;
  agg: UsageRow;
  children: UsageRow[]; // 섹션 단위(없으면 빈 배열 = 단일 상품)
}

function emptyRow(key: string): UsageRow {
  return {
    key, calls: 0, input_tokens: 0, output_tokens: 0,
    cached_tokens: 0, cost_usd: 0, cost_krw: 0,
  };
}

function addInto(a: UsageRow, b: UsageRow) {
  a.calls += b.calls;
  a.input_tokens += b.input_tokens;
  a.output_tokens += b.output_tokens;
  a.cached_tokens += b.cached_tokens;
  a.cost_usd += b.cost_usd;
  a.cost_krw += b.cost_krw;
}

export default function AdminUsagePage() {
  const [groupBy, setGroupBy] = useState<GroupBy>("product");
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setOpen(new Set());
    getUsageSummary(groupBy)
      .then((d) => setRows(d.rows))
      .finally(() => setLoading(false));
  }, [groupBy]);

  // '상품' 기준: 'RPT_FOCUS:W-01' → 상품 'RPT_FOCUS' + 섹션 'W-01'로 묶는다.
  const groups = useMemo<Group[] | null>(() => {
    if (groupBy !== "product") return null;
    const map = new Map<string, Group>();
    for (const r of rows) {
      const key = r.key ?? "(없음)";
      const idx = key.indexOf(":");
      const product = idx >= 0 ? key.slice(0, idx) : key;
      const section = idx >= 0 ? key.slice(idx + 1) : "";
      if (!map.has(product)) map.set(product, { product, agg: emptyRow(product), children: [] });
      const g = map.get(product)!;
      addInto(g.agg, r);
      if (section) g.children.push({ ...r, key: section });
    }
    return [...map.values()].sort((a, b) => b.agg.cost_usd - a.agg.cost_usd);
  }, [rows, groupBy]);

  const tot = rows.reduce((a, r) => (addInto(a, r), a), emptyRow("합계"));

  function toggle(p: string) {
    setOpen((s) => {
      const n = new Set(s);
      n.has(p) ? n.delete(p) : n.add(p);
      return n;
    });
  }

  const colLabel = GROUPS.find((g) => g.v === groupBy)?.label;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500">집계 기준</span>
        <select
          value={groupBy}
          onChange={(e) => setGroupBy(e.target.value as GroupBy)}
          className="rounded border px-2 py-1 text-sm"
        >
          {GROUPS.map((g) => (
            <option key={g.v} value={g.v}>{g.label}</option>
          ))}
        </select>
        {groupBy === "product" && (
          <span className="text-xs text-gray-400">행을 클릭하면 섹션별 상세가 펼쳐져요</span>
        )}
      </div>
      {loading ? (
        <p className="text-sm text-gray-500">불러오는 중…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">{colLabel}</th>
                <th className="px-3 py-2 text-right">호출</th>
                <th className="px-3 py-2 text-right">입력 토큰</th>
                <th className="px-3 py-2 text-right">출력 토큰</th>
                <th className="px-3 py-2 text-right">비용(₩)</th>
                <th className="px-3 py-2 text-right">비용($)</th>
              </tr>
            </thead>
            <tbody>
              {groups
                ? groups.flatMap((g) => {
                    const expandable = g.children.length > 0;
                    const isOpen = open.has(g.product);
                    const parent = (
                      <tr
                        key={g.product}
                        className={`border-t ${expandable ? "cursor-pointer hover:bg-gray-50" : ""}`}
                        onClick={expandable ? () => toggle(g.product) : undefined}
                      >
                        <td className="px-3 py-2 font-medium">
                          {expandable && (
                            <span className="mr-1 inline-block w-3 text-gray-400">
                              {isOpen ? "▼" : "▶"}
                            </span>
                          )}
                          {g.product}
                          {expandable && (
                            <span className="ml-1 text-xs text-gray-400">
                              ({g.children.length}섹션)
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">{g.agg.calls}</td>
                        <td className="px-3 py-2 text-right">{g.agg.input_tokens.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right">{g.agg.output_tokens.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right">₩{g.agg.cost_krw.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right text-gray-500">${g.agg.cost_usd.toFixed(4)}</td>
                      </tr>
                    );
                    const children = isOpen
                      ? g.children.map((c) => (
                          <tr key={`${g.product}:${c.key}`} className="border-t bg-gray-50/40">
                            <td className="px-3 py-1.5 pl-8 text-gray-600">{c.key}</td>
                            <td className="px-3 py-1.5 text-right">{c.calls}</td>
                            <td className="px-3 py-1.5 text-right">{c.input_tokens.toLocaleString()}</td>
                            <td className="px-3 py-1.5 text-right">{c.output_tokens.toLocaleString()}</td>
                            <td className="px-3 py-1.5 text-right">₩{c.cost_krw.toLocaleString()}</td>
                            <td className="px-3 py-1.5 text-right text-gray-400">${c.cost_usd.toFixed(4)}</td>
                          </tr>
                        ))
                      : [];
                    return [parent, ...children];
                  })
                : rows.map((r, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-3 py-2">{r.key ?? "(없음)"}</td>
                      <td className="px-3 py-2 text-right">{r.calls}</td>
                      <td className="px-3 py-2 text-right">{r.input_tokens.toLocaleString()}</td>
                      <td className="px-3 py-2 text-right">{r.output_tokens.toLocaleString()}</td>
                      <td className="px-3 py-2 text-right">₩{r.cost_krw.toLocaleString()}</td>
                      <td className="px-3 py-2 text-right text-gray-500">${r.cost_usd.toFixed(4)}</td>
                    </tr>
                  ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-gray-400">데이터 없음</td>
                </tr>
              )}
            </tbody>
            {rows.length > 0 && (
              <tfoot className="border-t bg-gray-50 font-medium">
                <tr>
                  <td className="px-3 py-2">합계</td>
                  <td className="px-3 py-2 text-right">{tot.calls}</td>
                  <td className="px-3 py-2 text-right">{tot.input_tokens.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right">{tot.output_tokens.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right">₩{tot.cost_krw.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right text-gray-500">${tot.cost_usd.toFixed(4)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  );
}
