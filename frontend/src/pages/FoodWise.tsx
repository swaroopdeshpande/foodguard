import { useEffect, useState } from "react";
import { api, type CategoryRef, type RefItem, type StorageUnitRef } from "../api";

type Tab = "dashboard" | "deliveries" | "operations" | "can-use" | "use-first";

const inputCls = "w-full border border-stone-300 rounded px-2.5 py-1.5 text-sm";
const labelCls = "block text-xs text-stone-500 mb-1";

export default function FoodWise() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [categories, setCategories] = useState<CategoryRef[]>([]);
  const [suppliers, setSuppliers] = useState<RefItem[]>([]);
  const [units, setUnits] = useState<StorageUnitRef[]>([]);

  async function refreshRefs() {
    setCategories(await api.refCategories());
    setSuppliers(await api.refSuppliers());
    setUnits(await api.refStorageUnits());
  }

  useEffect(() => {
    refreshRefs();
  }, []);

  return (
    <div className="max-w-4xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-stone-900">FoodWise</h1>
        <p className="text-sm text-stone-500">
          Real-transaction-driven inventory, food safety &amp; waste prevention — every number here comes from data you entered, never synthetic filler.
        </p>
      </div>

      <div className="flex gap-1 border-b border-stone-200 flex-wrap">
        {(["dashboard", "deliveries", "operations", "can-use", "use-first"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-emerald-700 text-emerald-800 font-medium" : "text-stone-500"}`}
          >
            {t.replace("-", " ")}
          </button>
        ))}
      </div>

      <div className="bg-white border border-stone-200 rounded-lg p-5">
        {tab === "dashboard" && <DashboardTab />}
        {tab === "deliveries" && <DeliveriesTab categories={categories} suppliers={suppliers} units={units} onCreated={refreshRefs} />}
        {tab === "operations" && <OperationsTab units={units} />}
        {tab === "can-use" && <CanUseTab />}
        {tab === "use-first" && <UseFirstTab />}
      </div>
    </div>
  );
}

function DashboardTab() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setData(await api.foodwiseDashboard());
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("fg:refresh", h);
    return () => window.removeEventListener("fg:refresh", h);
  }, []);

  if (error) return <p className="text-red-600 text-sm">{error}</p>;
  if (!data) return <p className="text-stone-400 text-sm">Loading…</p>;

  if (!data.has_real_data) {
    return (
      <div className="text-center py-12">
        <p className="text-stone-500 text-sm">{data.message}</p>
        <p className="text-stone-400 text-xs mt-2">No fake numbers here — add a delivery in the Deliveries tab to begin.</p>
      </div>
    );
  }

  const Card = ({ label, value, tone }: { label: string; value: string | number; tone?: string }) => (
    <div className="bg-stone-50 border border-stone-200 rounded-lg p-4">
      <p className="text-xs text-stone-500 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${tone ?? "text-stone-900"}`}>{value}</p>
    </div>
  );

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
      <Card label="Real batches in stock" value={data.real_batches_in_stock} />
      <Card label="Inventory value" value={`₹${data.inventory_value.toLocaleString()}`} />
      <Card label="Expiring soon" value={data.expiring_soon_batches} tone="text-amber-600" />
      <Card label="Expired" value={data.expired_batches} tone="text-red-600" />
      <Card label="Quarantined" value={data.quarantined_batches} tone="text-red-600" />
      <Card label="Today's consumption" value={data.today_consumption_qty} />
      <Card label="Today's waste (qty)" value={data.today_waste_qty} />
      <Card label="Today's waste cost" value={`₹${data.today_waste_cost.toLocaleString()}`} tone="text-red-600" />
    </div>
  );
}

function DeliveriesTab({ categories, suppliers, units, onCreated }: { categories: CategoryRef[]; suppliers: RefItem[]; units: StorageUnitRef[]; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [batchCode, setBatchCode] = useState("");
  const [quantity, setQuantity] = useState("40");
  const [unitCost, setUnitCost] = useState("400");
  const [mfg, setMfg] = useState(new Date().toISOString().slice(0, 10));
  const [exp, setExp] = useState(new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10));
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    try {
      const r = await api.foodwiseDelivery({
        new_food_item_name: name, category_id: categoryId, supplier_id: supplierId,
        storage_unit_id: unitId, batch_code: batchCode, quantity: Number(quantity),
        unit_cost: Number(unitCost), manufacturing_date: mfg, expiry_date: exp,
      });
      setResult(r);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
      onCreated();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3">
      <div><label className={labelCls}>Food item name</label><input required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Chicken Breast" /></div>
      <div>
        <label className={labelCls}>Category</label>
        <select required className={inputCls} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Select…</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div>
        <label className={labelCls}>Supplier</label>
        <select required className={inputCls} value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">Select…</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div>
        <label className={labelCls}>Storage unit</label>
        <select required className={inputCls} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">Select…</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </div>
      <div><label className={labelCls}>Batch code</label><input required className={inputCls} value={batchCode} onChange={(e) => setBatchCode(e.target.value)} placeholder="CHK-001" /></div>
      <div><label className={labelCls}>Quantity</label><input required type="number" step="0.1" className={inputCls} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></div>
      <div><label className={labelCls}>Unit cost</label><input type="number" step="0.1" className={inputCls} value={unitCost} onChange={(e) => setUnitCost(e.target.value)} /></div>
      <div><label className={labelCls}>Manufacturing date</label><input required type="date" className={inputCls} value={mfg} onChange={(e) => setMfg(e.target.value)} /></div>
      <div><label className={labelCls}>Expiry date</label><input required type="date" className={inputCls} value={exp} onChange={(e) => setExp(e.target.value)} /></div>
      <div className="col-span-2"><button className="bg-emerald-700 hover:bg-emerald-800 text-white text-sm px-4 py-2 rounded">Record delivery → create batch</button></div>
      {error && <p className="col-span-2 text-sm text-red-600">{error}</p>}
      {result && <p className="col-span-2 text-sm text-emerald-700">Batch {result.batch_code} created — current quantity: {result.current_quantity}</p>}
    </form>
  );
}

function OperationsTab({ units }: { units: StorageUnitRef[] }) {
  const [opTab, setOpTab] = useState<"consumption" | "waste" | "storage" | "occupancy">("consumption");
  return (
    <div className="space-y-4">
      <div className="flex gap-2 text-sm">
        {(["consumption", "waste", "storage", "occupancy"] as const).map((t) => (
          <button key={t} onClick={() => setOpTab(t)} className={`px-2 py-1 rounded capitalize ${opTab === t ? "bg-emerald-100 text-emerald-800" : "text-stone-500"}`}>{t}</button>
        ))}
      </div>
      {opTab === "consumption" && <ConsumptionOp />}
      {opTab === "waste" && <WasteOp />}
      {opTab === "storage" && <StorageOp units={units} />}
      {opTab === "occupancy" && <OccupancyOp />}
    </div>
  );
}

function ConsumptionOp() {
  const [batchId, setBatchId] = useState("");
  const [qty, setQty] = useState("1");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.foodwiseConsumption({ food_batch_id: batchId, quantity: Number(qty) });
      setResult(r);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div><label className={labelCls}>Batch ID (paste from delivery result)</label><input required className={inputCls} value={batchId} onChange={(e) => setBatchId(e.target.value)} /></div>
      <div><label className={labelCls}>Quantity consumed</label><input required type="number" step="0.1" className={inputCls} value={qty} onChange={(e) => setQty(e.target.value)} /></div>
      <button className="bg-emerald-700 hover:bg-emerald-800 text-white text-sm px-4 py-2 rounded">Record consumption</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && (
        <div className="text-sm space-y-1">
          <p className="text-emerald-700">Remaining quantity: {result.remaining_quantity}</p>
          {result.fefo_warning && <p className="text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">{result.fefo_warning}</p>}
        </div>
      )}
    </form>
  );
}

function WasteOp() {
  const [batchId, setBatchId] = useState("");
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState("spoilage");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.foodwiseWaste({ food_batch_id: batchId, quantity: Number(qty), reason });
      setResult(r);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div><label className={labelCls}>Batch ID</label><input required className={inputCls} value={batchId} onChange={(e) => setBatchId(e.target.value)} /></div>
      <div><label className={labelCls}>Quantity wasted</label><input required type="number" step="0.1" className={inputCls} value={qty} onChange={(e) => setQty(e.target.value)} /></div>
      <div>
        <label className={labelCls}>Reason</label>
        <select className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)}>
          {["expired", "spoilage", "overproduction", "damaged", "storage_issue", "preparation_waste", "buffet_leftover", "quality_rejection", "other"].map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <button className="bg-red-700 hover:bg-red-800 text-white text-sm px-4 py-2 rounded">Record waste</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && <p className="text-sm text-emerald-700">Recorded — estimated loss ₹{result.estimated_loss}, remaining {result.remaining_quantity}</p>}
    </form>
  );
}

function StorageOp({ units }: { units: StorageUnitRef[] }) {
  const [unitId, setUnitId] = useState("");
  const [temp, setTemp] = useState("4.0");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.foodwiseStorageReading({ storage_unit_id: unitId, temperature_c: Number(temp) });
      setResult(r);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className={labelCls}>Storage unit</label>
        <select required className={inputCls} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">Select…</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </div>
      <div><label className={labelCls}>Temperature °C</label><input required type="number" step="0.1" className={inputCls} value={temp} onChange={(e) => setTemp(e.target.value)} /></div>
      <button className="bg-emerald-700 hover:bg-emerald-800 text-white text-sm px-4 py-2 rounded">Record reading</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && (
        <p className={`text-sm ${result.anomaly_detected ? "text-red-600" : "text-emerald-700"}`}>
          {result.anomaly_detected ? "Excursion detected — check Incidents/Alerts." : "Within range."}
        </p>
      )}
    </form>
  );
}

function OccupancyOp() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [occ, setOcc] = useState("75");
  const [expected, setExpected] = useState("200");
  const [actual, setActual] = useState("190");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.foodwiseOccupancy({
        record_date: date, occupancy_pct: Number(occ), expected_guests: Number(expected), actual_guests: Number(actual),
      });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3">
      <div><label className={labelCls}>Date</label><input required type="date" className={inputCls} value={date} onChange={(e) => setDate(e.target.value)} /></div>
      <div><label className={labelCls}>Occupancy %</label><input type="number" step="0.1" className={inputCls} value={occ} onChange={(e) => setOcc(e.target.value)} /></div>
      <div><label className={labelCls}>Expected guests</label><input type="number" className={inputCls} value={expected} onChange={(e) => setExpected(e.target.value)} /></div>
      <div><label className={labelCls}>Actual guests</label><input type="number" className={inputCls} value={actual} onChange={(e) => setActual(e.target.value)} /></div>
      <div className="col-span-2"><button className="bg-emerald-700 hover:bg-emerald-800 text-white text-sm px-4 py-2 rounded">Record occupancy</button></div>
      {error && <p className="col-span-2 text-sm text-red-600">{error}</p>}
      {result && <p className="col-span-2 text-sm text-emerald-700">Recorded.</p>}
    </form>
  );
}

function CanUseTab() {
  const [batchId, setBatchId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [quarantineReason, setQuarantineReason] = useState("");

  async function check() {
    setError(null);
    try {
      setResult(await api.foodwiseCanUse(batchId));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function quarantine() {
    await api.foodwiseQuarantine(batchId, quarantineReason || "Manually quarantined");
    check();
  }
  async function release() {
    await api.foodwiseRelease(batchId);
    check();
  }

  const statusColor: Record<string, string> = {
    SAFE: "bg-emerald-100 text-emerald-800", EXPIRING_SOON: "bg-amber-100 text-amber-800",
    REVIEW_REQUIRED: "bg-orange-100 text-orange-800", DO_NOT_USE: "bg-red-100 text-red-800",
    EXPIRED: "bg-stone-800 text-white",
  };

  return (
    <div className="space-y-4 max-w-md">
      <div className="flex gap-2">
        <input className={inputCls} placeholder="Paste batch ID" value={batchId} onChange={(e) => setBatchId(e.target.value)} />
        <button onClick={check} className="bg-stone-800 text-white text-sm px-4 py-1.5 rounded whitespace-nowrap">Check</button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && !result.error && (
        <div className="border border-stone-200 rounded-lg p-4 space-y-2">
          <p className="font-medium text-stone-900">{result.food_item_name} — {result.batch_code}</p>
          <span className={`inline-block text-xs px-2 py-1 rounded-full font-semibold ${statusColor[result.status] ?? ""}`}>{result.status.replace(/_/g, " ")}</span>
          <p className="text-sm text-stone-600">{result.reason}</p>
          <p className="text-xs text-stone-400">Current quantity: {result.current_quantity} · Expiry: {result.expiry_date}</p>
          <div className="flex gap-2 pt-2">
            <input className={`${inputCls} flex-1`} placeholder="Quarantine reason" value={quarantineReason} onChange={(e) => setQuarantineReason(e.target.value)} />
            <button onClick={quarantine} className="text-xs bg-red-700 text-white px-3 py-1.5 rounded whitespace-nowrap">Quarantine</button>
            <button onClick={release} className="text-xs border border-stone-300 px-3 py-1.5 rounded whitespace-nowrap">Release</button>
          </div>
        </div>
      )}
    </div>
  );
}

function UseFirstTab() {
  const [queue, setQueue] = useState<any[]>([]);

  async function load() {
    setQueue(await api.foodwiseUseFirst());
  }
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("fg:refresh", h);
    return () => window.removeEventListener("fg:refresh", h);
  }, []);

  return (
    <div className="space-y-2">
      {queue.map((b, i) => (
        <div key={b.batch_id} className="flex items-center justify-between border border-stone-200 rounded-lg p-3">
          <div>
            <p className="text-sm font-medium">{i + 1}. {b.food_item_name} — {b.batch_code}</p>
            <p className="text-xs text-stone-500">{b.current_quantity} · expires {b.expiry_date} · {b.status.replace(/_/g, " ")}</p>
          </div>
        </div>
      ))}
      {queue.length === 0 && <p className="text-stone-400 text-sm">No real batches to prioritize — record a delivery first.</p>}
    </div>
  );
}
