import { useEffect, useState } from "react";
import { api, type StorageUnit } from "../api";

function SeverityDot({ sev }: { sev: string | null }) {
  const color = sev === "HIGH" ? "bg-red-500" : sev === "MEDIUM" ? "bg-amber-500" : "bg-stone-300";
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />;
}

export default function Storage() {
  const [units, setUnits] = useState<StorageUnit[]>([]);

  async function load() {
    setUnits(await api.storageUnits());
  }

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("fg:refresh", handler);
    return () => window.removeEventListener("fg:refresh", handler);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-stone-900">Storage Units</h1>
      <div className="grid md:grid-cols-3 gap-4">
        {units.map((u) => {
          const deviation = u.current_temperature != null ? u.current_temperature - u.target_temp_c : null;
          return (
            <div key={u.id} className="bg-white border border-stone-200 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-medium text-stone-900">{u.name}</p>
                <SeverityDot sev={u.latest_severity} />
              </div>
              <p className="text-xs text-stone-500">{u.unit_type}</p>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-semibold">
                  {u.current_temperature != null ? `${u.current_temperature.toFixed(1)}°C` : "—"}
                </span>
                <span className="text-xs text-stone-400">target {u.target_temp_c}°C</span>
              </div>
              {deviation != null && Math.abs(deviation) > 0.3 && (
                <p className={`text-xs ${deviation > 0 ? "text-red-600" : "text-blue-600"}`}>
                  {deviation > 0 ? "+" : ""}
                  {deviation.toFixed(2)}°C from target
                </p>
              )}
              {u.latest_anomaly_type && (
                <div className="text-xs bg-red-50 text-red-700 rounded px-2 py-1.5 mt-2">
                  <span className="font-medium">{u.latest_anomaly_type}</span>
                  {u.estimated_days_to_threshold != null && (
                    <span> — est. {u.estimated_days_to_threshold}d to threshold</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
