import { useEffect, useState } from "react";
import { api, type Supplier } from "../api";

export default function Suppliers() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  async function load() {
    setSuppliers(await api.suppliers());
  }

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("fg:refresh", handler);
    return () => window.removeEventListener("fg:refresh", handler);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-stone-900">Suppliers</h1>
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 text-stone-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Supplier</th>
              <th className="px-4 py-2 font-medium">Anomaly severity</th>
              <th className="px-4 py-2 font-medium">Anomaly score</th>
              <th className="px-4 py-2 font-medium">Deviating features</th>
            </tr>
          </thead>
          <tbody>
            {suppliers.map((s) => (
              <tr key={s.id} className="border-t border-stone-100">
                <td className="px-4 py-2 font-medium">{s.name}</td>
                <td className="px-4 py-2">
                  {s.latest_severity ? (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        s.latest_severity === "HIGH"
                          ? "bg-red-100 text-red-700"
                          : s.latest_severity === "MEDIUM"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-stone-100 text-stone-600"
                      }`}
                    >
                      {s.latest_severity}
                    </span>
                  ) : (
                    <span className="text-stone-400 text-xs">normal</span>
                  )}
                </td>
                <td className="px-4 py-2 tabular-nums">{s.latest_anomaly_score?.toFixed(3) ?? "—"}</td>
                <td className="px-4 py-2 text-xs text-stone-600">
                  {s.deviating_features && Object.keys(s.deviating_features).length > 0
                    ? Object.entries(s.deviating_features)
                        .map(([k, v]: [string, any]) => `${k}: ${v.value} (z=${v.z_score})`)
                        .join(", ")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
