import { useState } from "react";
import { api } from "../api";

export default function LabelScanner() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await api.scanLabel(file));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-lg font-semibold text-stone-900">Label Scanner (local OCR, no cloud)</h1>
      <div className="bg-white border border-stone-200 rounded-lg p-6">
        <input type="file" accept="image/*" onChange={handleFile} className="text-sm" />
        {loading && <p className="text-sm text-stone-500 mt-3">Running local Tesseract OCR…</p>}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
        {result && (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <p className="text-stone-500 text-xs mb-1">Raw OCR text</p>
              <p className="bg-stone-50 rounded p-2 font-mono text-xs">{result.raw_ocr_text}</p>
            </div>
            <div>
              <p className="text-stone-500 text-xs mb-1">Extracted fields</p>
              <pre className="bg-stone-50 rounded p-2 text-xs overflow-x-auto">
                {JSON.stringify(result.extracted_fields, null, 2)}
              </pre>
            </div>
            <p className="text-xs text-stone-500">
              OCR confidence: {(result.ocr_confidence * 100).toFixed(1)}%
            </p>
            {result.anomalies?.length > 0 ? (
              <div className="bg-red-50 border border-red-200 rounded p-3">
                <p className="text-red-700 font-medium text-xs mb-1">Anomalies found</p>
                {result.anomalies.map((a: any, i: number) => (
                  <p key={i} className="text-xs text-red-700">
                    {a.anomaly_type} ({a.severity})
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-xs text-emerald-700">No label anomalies detected.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
