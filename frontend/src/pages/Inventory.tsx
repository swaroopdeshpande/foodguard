import { Fragment, useEffect, useState } from "react";
import { api, type FoodBatch } from "../api";

function RiskBadge({ cls }: { cls: string | null }) {
  if (!cls) return <span className="text-stone-400 text-xs">—</span>;
  const color =
    cls === "HIGH" ? "bg-red-100 text-red-700" : cls === "MEDIUM" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700";
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${color}`}>{cls}</span>;
}

export default function Inventory() {
  const [batches, setBatches] = useState<FoodBatch[]>([]);
  const [riskFilter, setRiskFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  async function load() {
    setBatches(await api.batches(riskFilter ? { risk_class: riskFilter } : {}));
  }

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("fg:refresh", handler);
    return () => window.removeEventListener("fg:refresh", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskFilter]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-stone-900">Inventory</h1>
        <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)} className="border border-stone-300 rounded px-2 py-1.5 text-sm bg-white">
          <option value="">All risk levels</option>
          <option value="HIGH">HIGH only</option>
          <option value="MEDIUM">MEDIUM only</option>
          <option value="LOW">LOW only</option>
        </select>
      </div>

      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 text-stone-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Food item</th>
              <th className="px-4 py-2 font-medium">Batch code</th>
              <th className="px-4 py-2 font-medium">Supplier</th>
              <th className="px-4 py-2 font-medium">Storage</th>
              <th className="px-4 py-2 font-medium">Expiry</th>
              <th className="px-4 py-2 font-medium">Risk</th>
              <th className="px-4 py-2 font-medium">Probability</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <Fragment key={b.id}>
                <tr
                  className="border-t border-stone-100 hover:bg-stone-50 cursor-pointer"
                  onClick={() => setExpanded(expanded === b.id ? null : b.id)}
                >
                  <td className="px-4 py-2">{b.food_item_name}</td>
                  <td className="px-4 py-2 font-mono text-xs text-stone-500">{b.batch_code}</td>
                  <td className="px-4 py-2">{b.supplier_name}</td>
                  <td className="px-4 py-2">{b.storage_unit_name ?? "—"}</td>
                  <td className="px-4 py-2">{b.expiry_date}</td>
                  <td className="px-4 py-2">
                    <RiskBadge cls={b.latest_risk_class} />
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {b.latest_risk_probability != null ? `${(b.latest_risk_probability * 100).toFixed(1)}%` : "—"}
                  </td>
                </tr>
                {expanded === b.id && b.latest_top_factors && (
                  <tr className="bg-stone-50 border-t border-stone-100">
                    <td colSpan={7} className="px-4 py-3 text-xs text-stone-600">
                      <span className="font-medium">Top contributing factors: </span>
                      {Object.entries(b.latest_top_factors)
                        .map(([k, v]) => `${k} (${(v * 100).toFixed(1)}%)`)
                        .join("  ·  ")}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {batches.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-stone-400">
                  No batches — run the pipeline or trigger a scenario from the Dashboard.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
