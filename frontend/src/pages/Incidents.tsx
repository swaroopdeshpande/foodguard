import { useEffect, useState } from "react";
import { api, type Incident } from "../api";

const DEPARTMENTS = ["", "KITCHEN", "MAINTENANCE", "PROCUREMENT", "AUDIT", "INVESTIGATION"];

export default function Incidents() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [department, setDepartment] = useState("");

  async function load() {
    setIncidents(await api.incidents(department ? { department, status: "OPEN" } : { status: "OPEN" }));
  }

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("fg:refresh", handler);
    return () => window.removeEventListener("fg:refresh", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  async function resolve(id: string) {
    await api.resolveIncident(id);
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-stone-900">Alerts / Incidents</h1>
        <select value={department} onChange={(e) => setDepartment(e.target.value)} className="border border-stone-300 rounded px-2 py-1.5 text-sm bg-white">
          {DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {d || "All departments"}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        {incidents.map((inc) => (
          <div key={inc.id} className="bg-white border border-stone-200 rounded-lg p-4 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    inc.severity === "HIGH" ? "bg-red-100 text-red-700" : inc.severity === "MEDIUM" ? "bg-amber-100 text-amber-700" : "bg-stone-100 text-stone-600"
                  }`}
                >
                  {inc.severity}
                </span>
                <span className="text-sm font-medium text-stone-900">{inc.action}</span>
                <span className="text-xs text-stone-400">→ {inc.department}</span>
              </div>
              <p className="text-xs text-stone-500">
                {inc.source_type} · {new Date(inc.created_at).toLocaleString()}
              </p>
              {inc.reason_codes?.length > 0 && (
                <p className="text-xs text-stone-600 mt-1">Reasons: {inc.reason_codes.join(", ")}</p>
              )}
            </div>
            <button
              onClick={() => resolve(inc.id)}
              className="text-xs text-emerald-700 border border-emerald-200 rounded px-2 py-1 hover:bg-emerald-50 whitespace-nowrap"
            >
              Mark resolved
            </button>
          </div>
        ))}
        {incidents.length === 0 && <p className="text-stone-400 text-sm">No open incidents.</p>}
      </div>
    </div>
  );
}
