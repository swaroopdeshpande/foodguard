import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api, type DashboardSummary } from "../api";

const SCENARIOS = ["normal", "fridge_drift", "supplier_anomaly", "unit_failure", "label_fraud", "consumption_drop"];

function Card({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="bg-white border border-stone-200 rounded-lg p-4">
      <p className="text-xs text-stone-500 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${tone ?? "text-stone-900"}`}>{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [scenario, setScenario] = useState("fridge_drift");
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setSummary(await api.dashboardSummary());
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("fg:refresh", handler);
    return () => window.removeEventListener("fg:refresh", handler);
  }, []);

  async function trigger() {
    setTriggering(true);
    try {
      await api.triggerScenario(scenario, 90);
    } finally {
      setTimeout(() => setTriggering(false), 1500);
    }
  }

  const actionData = summary
    ? Object.entries(summary.incidents_by_action).map(([action, count]) => ({ action, count }))
    : [];
  const deptData = summary
    ? Object.entries(summary.incidents_by_department).map(([department, count]) => ({ department, count }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-stone-900">Dashboard</h1>
        <div className="flex items-center gap-2">
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            className="border border-stone-300 rounded px-2 py-1.5 text-sm bg-white"
          >
            {SCENARIOS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            onClick={trigger}
            disabled={triggering}
            className="bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded"
          >
            {triggering ? "Simulating…" : "Trigger scenario (live)"}
          </button>
        </div>
      </div>

      {error && <p className="text-red-600 text-sm">{error} — is the API running on :8000?</p>}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card label="Batches in stock" value={summary.total_batches_in_stock} />
            <Card label="High-risk batches" value={summary.high_risk_batches} tone="text-red-600" />
            <Card label="Open incidents" value={summary.open_incidents} tone="text-amber-600" />
            <Card
              label="Estimated wastage loss"
              value={`₹${summary.estimated_wastage_loss.toLocaleString()}`}
            />
            <Card label="Active storage anomalies" value={summary.active_storage_anomalies} />
            <Card label="Active supplier anomalies (7d)" value={summary.active_supplier_anomalies} />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-white border border-stone-200 rounded-lg p-4">
              <p className="text-sm font-medium text-stone-700 mb-3">Open incidents by action</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={actionData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="action" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#047857" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-white border border-stone-200 rounded-lg p-4">
              <p className="text-sm font-medium text-stone-700 mb-3">Open incidents by department</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={deptData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="department" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#b45309" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
