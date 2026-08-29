const API_BASE = "http://127.0.0.1:8000";

export function getToken(): string | null {
  return localStorage.getItem("fg_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("fg_token", token);
  else localStorage.removeItem("fg_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export interface DashboardSummary {
  total_batches_in_stock: number;
  high_risk_batches: number;
  open_incidents: number;
  incidents_by_department: Record<string, number>;
  incidents_by_action: Record<string, number>;
  estimated_wastage_loss: number;
  active_storage_anomalies: number;
  active_supplier_anomalies: number;
}

export interface FoodBatch {
  id: string;
  food_item_name: string;
  category_name: string;
  supplier_name: string;
  storage_unit_name: string | null;
  batch_code: string;
  quantity: number;
  manufacturing_date: string;
  expiry_date: string;
  status: string;
  latest_risk_probability: number | null;
  latest_risk_class: string | null;
  latest_top_factors: Record<string, number> | null;
}

export interface StorageUnit {
  id: string;
  name: string;
  unit_type: string;
  target_temp_c: number;
  current_temperature: number | null;
  latest_anomaly_type: string | null;
  latest_severity: string | null;
  estimated_days_to_threshold: number | null;
}

export interface Supplier {
  id: string;
  name: string;
  latest_anomaly_score: number | null;
  latest_severity: string | null;
  deviating_features: Record<string, any> | null;
}

export interface Incident {
  id: string;
  created_at: string;
  source_type: string;
  action: string;
  department: string;
  severity: string;
  status: string;
  reason_codes: string[];
  dimensions_snapshot: Record<string, any>;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; role: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  dashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),
  batches: (params: Record<string, string> = {}) =>
    request<FoodBatch[]>(`/api/inventory/batches?${new URLSearchParams(params)}`),
  storageUnits: () => request<StorageUnit[]>("/api/storage/units"),
  suppliers: () => request<Supplier[]>("/api/suppliers"),
  incidents: (params: Record<string, string> = {}) =>
    request<Incident[]>(`/api/incidents?${new URLSearchParams(params)}`),
  resolveIncident: (id: string) => request<Incident>(`/api/incidents/${id}/resolve`, { method: "POST" }),
  triggerScenario: (scenario: string, days: number) =>
    request<{ status: string }>("/api/simulation/trigger", {
      method: "POST",
      body: JSON.stringify({ scenario, days }),
    }),
  simulationStatus: () => request<any>("/api/simulation/status"),
  scanLabel: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<any>("/api/ocr/scan", { method: "POST", body: form });
  },
};

export function wsUrl() {
  return "ws://127.0.0.1:8000/ws/live";
}
