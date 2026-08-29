import { useEffect, useState } from "react";
import {
  api,
  type CategoryRef,
  type FoodItemRef,
  type ManualEntryResult,
  type RefItem,
  type StorageUnitRef,
} from "../api";

type Tab = "batch" | "reading" | "delivery" | "consumption";

function ResultPanel({ result }: { result: ManualEntryResult | null }) {
  if (!result) return null;

  const sevColor = (sev?: string | null) =>
    sev === "HIGH" ? "text-red-700 bg-red-50 border-red-200" : sev === "MEDIUM" ? "text-amber-700 bg-amber-50 border-amber-200" : "text-emerald-700 bg-emerald-50 border-emerald-200";

  return (
    <div className="mt-4 space-y-3">
      {result.risk_prediction && (
        <div className={`border rounded-lg p-3 text-sm ${sevColor(result.risk_prediction.risk_class)}`}>
          <p className="font-medium">
            Food risk: {result.risk_prediction.risk_class} ({(result.risk_prediction.risk_probability * 100).toFixed(1)}%)
          </p>
          <p className="text-xs mt-1 opacity-80">
            Top factors: {Object.entries(result.risk_prediction.top_factors).map(([k, v]) => `${k} (${(v * 100).toFixed(0)}%)`).join(", ")}
          </p>
        </div>
      )}
      {result.storage_anomaly && (
        <div className={`border rounded-lg p-3 text-sm ${sevColor(result.storage_anomaly.severity)}`}>
          <p className="font-medium">
            Storage anomaly: {result.storage_anomaly.anomaly_type} ({result.storage_anomaly.severity})
          </p>
          <p className="text-xs mt-1 opacity-80">
            Current {result.storage_anomaly.current_value}°C vs expected {result.storage_anomaly.expected_value}°C
            {result.storage_anomaly.estimated_days_to_threshold != null &&
              ` — est. ${result.storage_anomaly.estimated_days_to_threshold}d to threshold`}
          </p>
        </div>
      )}
      {!result.storage_anomaly && result.created_id && result.risk_prediction === null && result.supplier_anomaly === null && result.consumption_anomaly === null && (
        <p className="text-xs text-stone-500">Recorded — no anomaly detected (within normal range, or not enough history yet).</p>
      )}
      {result.supplier_anomaly && (
        <div className={`border rounded-lg p-3 text-sm ${sevColor(result.supplier_anomaly.severity)}`}>
          <p className="font-medium">
            Supplier anomaly: {result.supplier_anomaly.severity} (score {result.supplier_anomaly.anomaly_score.toFixed(3)})
          </p>
          <div className="text-xs mt-1 opacity-80 space-y-0.5">
            {Object.entries(result.supplier_anomaly.deviating_features).map(([k, v]: [string, any]) => (
              <p key={k}>
                {k}: {v.value} (baseline {v.supplier_baseline_mean}, z={v.z_score})
              </p>
            ))}
          </div>
        </div>
      )}
      {result.consumption_anomaly && (
        <div className={`border rounded-lg p-3 text-sm ${sevColor(result.consumption_anomaly.severity)}`}>
          <p className="font-medium">Consumption anomaly: {result.consumption_anomaly.severity}</p>
          <p className="text-xs mt-1 opacity-80">
            z-score {result.consumption_anomaly.z_score}, change {(result.consumption_anomaly.pct_change * 100).toFixed(0)}% — recommendation: {result.consumption_anomaly.recommendation}
          </p>
        </div>
      )}
      {result.incident && (
        <div className="border border-stone-300 bg-stone-50 rounded-lg p-3 text-sm">
          <p className="font-medium text-stone-900">
            → Routed action: <span className="font-semibold">{result.incident.action}</span> to <span className="font-semibold">{result.incident.department}</span>
          </p>
          {result.incident.reason_codes?.length > 0 && (
            <p className="text-xs text-stone-500 mt-1">Reasons: {result.incident.reason_codes.join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ManualEntry() {
  const [tab, setTab] = useState<Tab>("batch");
  const [categories, setCategories] = useState<CategoryRef[]>([]);
  const [foodItems, setFoodItems] = useState<FoodItemRef[]>([]);
  const [suppliers, setSuppliers] = useState<RefItem[]>([]);
  const [units, setUnits] = useState<StorageUnitRef[]>([]);
  const [result, setResult] = useState<ManualEntryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.refCategories().then(setCategories);
    api.refFoodItems().then(setFoodItems);
    api.refSuppliers().then(setSuppliers);
    api.refStorageUnits().then(setUnits);
  }, []);

  async function refreshRefs() {
    setFoodItems(await api.refFoodItems());
  }

  async function submit(fn: () => Promise<ManualEntryResult>) {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const r = await fn();
      setResult(r);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
      await refreshRefs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-lg font-semibold text-stone-900">Manual Data Entry</h1>
      <p className="text-sm text-stone-500">
        Enter real data yourself — each submission is scored immediately by the actual model/anomaly engine, not a bulk simulation.
      </p>

      <div className="flex gap-1 border-b border-stone-200">
        {(["batch", "reading", "delivery", "consumption"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setResult(null);
              setError(null);
            }}
            className={`px-3 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-emerald-700 text-emerald-800 font-medium" : "text-stone-500"}`}
          >
            {t === "batch" ? "Food batch" : t === "reading" ? "Storage reading" : t === "delivery" ? "Supplier delivery" : "Consumption"}
          </button>
        ))}
      </div>

      <div className="bg-white border border-stone-200 rounded-lg p-5">
        {tab === "batch" && (
          <BatchForm categories={categories} suppliers={suppliers} units={units} submitting={submitting} onSubmit={(body) => submit(() => api.createBatch(body))} />
        )}
        {tab === "reading" && (
          <ReadingForm units={units} submitting={submitting} onSubmit={(body) => submit(() => api.createReading(body))} />
        )}
        {tab === "delivery" && (
          <DeliveryForm suppliers={suppliers} submitting={submitting} onSubmit={(body) => submit(() => api.createDelivery(body))} />
        )}
        {tab === "consumption" && (
          <ConsumptionForm foodItems={foodItems} submitting={submitting} onSubmit={(body) => submit(() => api.createConsumption(body))} />
        )}

        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
        <ResultPanel result={result} />
      </div>
    </div>
  );
}

const inputCls = "w-full border border-stone-300 rounded px-2.5 py-1.5 text-sm";
const labelCls = "block text-xs text-stone-500 mb-1";

function BatchForm({ categories, suppliers, units, submitting, onSubmit }: { categories: CategoryRef[]; suppliers: RefItem[]; units: StorageUnitRef[]; submitting: boolean; onSubmit: (body: object) => void }) {
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [batchCode, setBatchCode] = useState("");
  const [quantity, setQuantity] = useState("10");
  const [mfg, setMfg] = useState(new Date().toISOString().slice(0, 10));
  const [exp, setExp] = useState(new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          new_food_item_name: name, category_id: categoryId, supplier_id: supplierId,
          storage_unit_id: unitId, batch_code: batchCode, quantity: Number(quantity),
          manufacturing_date: mfg, expiry_date: exp,
        });
      }}
      className="grid grid-cols-2 gap-3"
    >
      <div>
        <label className={labelCls}>Food item name</label>
        <input required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Chicken Breast" />
      </div>
      <div>
        <label className={labelCls}>Category</label>
        <select required className={inputCls} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Select…</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name} (shelf life {c.expected_shelf_life_days}d, {c.required_min_temp_c}–{c.required_max_temp_c}°C)</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelCls}>Supplier</label>
        <select required className={inputCls} value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">Select…</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelCls}>Storage unit</label>
        <select required className={inputCls} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">Select…</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>{u.name} (target {u.target_temp_c}°C)</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelCls}>Batch code</label>
        <input required className={inputCls} value={batchCode} onChange={(e) => setBatchCode(e.target.value)} placeholder="e.g. XYZ-001" />
      </div>
      <div>
        <label className={labelCls}>Quantity (kg)</label>
        <input required type="number" step="0.1" className={inputCls} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
      </div>
      <div>
        <label className={labelCls}>Manufacturing date</label>
        <input required type="date" className={inputCls} value={mfg} onChange={(e) => setMfg(e.target.value)} />
      </div>
      <div>
        <label className={labelCls}>Expiry date</label>
        <input required type="date" className={inputCls} value={exp} onChange={(e) => setExp(e.target.value)} />
      </div>
      <div className="col-span-2">
        <button disabled={submitting} className="bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-sm px-4 py-2 rounded">
          {submitting ? "Scoring…" : "Submit & score"}
        </button>
      </div>
    </form>
  );
}

function ReadingForm({ units, submitting, onSubmit }: { units: StorageUnitRef[]; submitting: boolean; onSubmit: (body: object) => void }) {
  const [unitId, setUnitId] = useState("");
  const [temp, setTemp] = useState("4.0");
  const [humidity, setHumidity] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ storage_unit_id: unitId, temperature_c: Number(temp), humidity_pct: humidity ? Number(humidity) : null });
      }}
      className="grid grid-cols-2 gap-3"
    >
      <div>
        <label className={labelCls}>Storage unit</label>
        <select required className={inputCls} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">Select…</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>{u.name} (target {u.target_temp_c}°C)</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelCls}>Temperature (°C)</label>
        <input required type="number" step="0.1" className={inputCls} value={temp} onChange={(e) => setTemp(e.target.value)} />
      </div>
      <div>
        <label className={labelCls}>Humidity % (optional)</label>
        <input type="number" step="0.1" className={inputCls} value={humidity} onChange={(e) => setHumidity(e.target.value)} />
      </div>
      <div className="col-span-2">
        <button disabled={submitting} className="bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-sm px-4 py-2 rounded">
          {submitting ? "Analyzing…" : "Submit & analyze"}
        </button>
      </div>
    </form>
  );
}

function DeliveryForm({ suppliers, submitting, onSubmit }: { suppliers: RefItem[]; submitting: boolean; onSubmit: (body: object) => void }) {
  const [supplierId, setSupplierId] = useState("");
  const [batchSize, setBatchSize] = useState("80");
  const [delay, setDelay] = useState("1");
  const [defectRate, setDefectRate] = useState("0.02");
  const [rejected, setRejected] = useState("1");
  const [complaints, setComplaints] = useState("0");
  const [price, setPrice] = useState("100");
  const [shelfLife, setShelfLife] = useState("7");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          supplier_id: supplierId, batch_size_kg: Number(batchSize), delivery_delay_days: Number(delay),
          defect_rate: Number(defectRate), rejected_quantity_kg: Number(rejected), complaint_count: Number(complaints),
          price_per_kg: Number(price), remaining_shelf_life_days: Number(shelfLife),
        });
      }}
      className="grid grid-cols-2 gap-3"
    >
      <div className="col-span-2">
        <label className={labelCls}>Supplier</label>
        <select required className={inputCls} value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">Select…</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
      <div><label className={labelCls}>Batch size (kg)</label><input type="number" step="0.1" className={inputCls} value={batchSize} onChange={(e) => setBatchSize(e.target.value)} /></div>
      <div><label className={labelCls}>Delivery delay (days)</label><input type="number" step="0.1" className={inputCls} value={delay} onChange={(e) => setDelay(e.target.value)} /></div>
      <div><label className={labelCls}>Defect rate (0-1)</label><input type="number" step="0.01" className={inputCls} value={defectRate} onChange={(e) => setDefectRate(e.target.value)} /></div>
      <div><label className={labelCls}>Rejected qty (kg)</label><input type="number" step="0.1" className={inputCls} value={rejected} onChange={(e) => setRejected(e.target.value)} /></div>
      <div><label className={labelCls}>Complaint count</label><input type="number" className={inputCls} value={complaints} onChange={(e) => setComplaints(e.target.value)} /></div>
      <div><label className={labelCls}>Price per kg</label><input type="number" step="0.1" className={inputCls} value={price} onChange={(e) => setPrice(e.target.value)} /></div>
      <div><label className={labelCls}>Remaining shelf life (days)</label><input type="number" className={inputCls} value={shelfLife} onChange={(e) => setShelfLife(e.target.value)} /></div>
      <div className="col-span-2">
        <button disabled={submitting} className="bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-sm px-4 py-2 rounded">
          {submitting ? "Analyzing…" : "Submit & analyze"}
        </button>
      </div>
      <p className="col-span-2 text-xs text-stone-400">Needs ≥6 prior deliveries for that supplier to have a baseline — all demo suppliers already do.</p>
    </form>
  );
}

function ConsumptionForm({ foodItems, submitting, onSubmit }: { foodItems: FoodItemRef[]; submitting: boolean; onSubmit: (body: object) => void }) {
  const [itemId, setItemId] = useState("");
  const [qty, setQty] = useState("10");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ food_item_id: itemId, quantity_consumed: Number(qty) });
      }}
      className="grid grid-cols-2 gap-3"
    >
      <div className="col-span-2">
        <label className={labelCls}>Food item</label>
        <select required className={inputCls} value={itemId} onChange={(e) => setItemId(e.target.value)}>
          <option value="">Select…</option>
          {foodItems.map((f) => (
            <option key={f.id} value={f.id}>{f.name} ({f.category_name})</option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelCls}>Quantity consumed today</label>
        <input required type="number" step="0.1" className={inputCls} value={qty} onChange={(e) => setQty(e.target.value)} />
      </div>
      <div className="col-span-2">
        <button disabled={submitting} className="bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white text-sm px-4 py-2 rounded">
          {submitting ? "Analyzing…" : "Submit & analyze"}
        </button>
      </div>
      <p className="col-span-2 text-xs text-stone-400">Needs ≥6 days of consumption history for that item to detect an anomaly.</p>
    </form>
  );
}
