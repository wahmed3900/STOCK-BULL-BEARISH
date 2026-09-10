"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api/client";

export default function Home() {
  const [symbol, setSymbol] = useState("AAPL");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchData() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.hybridChart({
        symbol,
        asset_type: "stock",
        include_ai: false,
      });
      setData(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-10 font-sans">
      <h1 className="text-3xl font-bold mb-4">Stock Dashboard</h1>

      <div className="mb-4">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          className="border p-2 rounded"
        />
        <button
          onClick={fetchData}
          className="bg-blue-500 text-white p-2 rounded ml-2"
        >
          Analyze
        </button>
      </div>

      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {data && (
        <div className="border p-6 rounded max-w-md">
          <h2 className="text-xl font-bold">{data.symbol}</h2>
          <p>Price: ${data.current_price}</p>
          <p>Change: {data.change_pct}%</p>
          <p>Source: {data.source ?? "unknown"}</p>
          <p>
            RSI:{" "}
            {data.technical_indicators?.rsi != null
              ? data.technical_indicators.rsi
              : "N/A"}
          </p>
          <p>AI: {data.ai_analysis}</p>
        </div>
      )}
    </div>
  );
}
