const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  "https://stock-dashboard-backend-634072894074.us-west4.run.app";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {}
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

export const apiClient = {
  hybridChart: (payload: {
    symbol: string;
    asset_type?: string;
    timeframe?: string;
    include_ai?: boolean;
  }) =>
    request<any>("/api/chart/hybrid", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  stock: (symbol: string) => request<any>(`/api/stock/${symbol}`),

  health: () => request<any>("/api/health"),
};
