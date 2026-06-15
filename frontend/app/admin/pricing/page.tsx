"use client";

// 단가·환율 관리 — 현재 사용 모델별 단가($/1M tokens)와 환율(USD→KRW)을 관리자가 직접 등록.

import { useEffect, useState } from "react";
import { getPricing, putPricing, putRate, type PricingRow } from "@/lib/admin";

export default function AdminPricingPage() {
  const [rows, setRows] = useState<PricingRow[]>([]);
  const [rate, setRate] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () =>
    getPricing().then((d) => {
      setRows(d.pricing);
      setRate(d.usd_krw);
    });

  useEffect(() => {
    load();
  }, []);

  function edit(model: string, field: keyof PricingRow, value: number) {
    setRows((rs) => rs.map((r) => (r.model === model ? { ...r, [field]: value } : r)));
  }

  async function save(r: PricingRow) {
    setMsg(null);
    await putPricing(r.model, {
      input_per_1m: r.input_per_1m,
      output_per_1m: r.output_per_1m,
      cached_per_1m: r.cached_per_1m,
    });
    setMsg(`${r.model} 단가 저장됨`);
    load();
  }

  async function saveRate() {
    setMsg(null);
    await putRate(rate);
    setMsg(`환율 저장됨 (1 USD = ₩${rate.toLocaleString()})`);
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-2 rounded-lg border bg-white p-4 shadow-sm">
        <label className="text-sm">
          <span className="text-gray-500">환율 (1 USD = ₩)</span>
          <input
            type="number"
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            className="ml-2 w-28 rounded border px-2 py-1"
          />
        </label>
        <button
          onClick={saveRate}
          className="rounded bg-indigo-500 px-3 py-1.5 text-sm text-white hover:bg-indigo-600"
        >
          환율 저장
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-3 py-2 text-left">모델</th>
              <th className="px-3 py-2 text-right">입력 $/1M</th>
              <th className="px-3 py-2 text-right">출력 $/1M</th>
              <th className="px-3 py-2 text-right">캐시입력 $/1M</th>
              <th className="px-3 py-2 text-left">수정</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model} className="border-t">
                <td className="px-3 py-2 font-medium">{r.model}</td>
                {(["input_per_1m", "output_per_1m", "cached_per_1m"] as const).map((f) => (
                  <td key={f} className="px-3 py-2 text-right">
                    <input
                      type="number"
                      step="0.0001"
                      value={r[f]}
                      onChange={(e) => edit(r.model, f, Number(e.target.value))}
                      className="w-24 rounded border px-2 py-1 text-right"
                    />
                  </td>
                ))}
                <td className="px-3 py-2 text-xs text-gray-400">
                  {r.updated_at?.slice(0, 10)} {r.updated_by ?? ""}
                </td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => save(r)}
                    className="rounded border px-2 py-1 text-xs hover:bg-gray-50"
                  >
                    저장
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {msg && <p className="text-sm text-green-600">{msg}</p>}
      <p className="text-xs text-gray-400">
        단가 변경은 이후 호출부터 비용 계산에 반영돼요(과거 기록은 그 시점 단가로 보존).
      </p>
    </div>
  );
}
