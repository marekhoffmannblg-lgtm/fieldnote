const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api").replace(/\/$/, "");

export interface ApiPage<T> {
  schema_version: "1";
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Lokalna usługa nie zwróciła poprawnej odpowiedzi.");
  }
  return payload as T;
}

export function apiPageRequest<T>(path: string, limit = 100, offset = 0): Promise<ApiPage<T>> {
  const separator = path.includes("?") ? "&" : "?";
  return apiRequest<ApiPage<T>>(`${path}${separator}limit=${limit}&offset=${offset}`);
}
