export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type RegistrantSummary = {
  id: string;
  external_id: string;
  full_name: string;
  risk_level: string | null;
  last_seen: string;
};

export type SourceSummary = {
  name: string;
  state: string | null;
  enabled: boolean;
  supports_fetch: boolean;
  notes: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  getRegistrants: () => request<RegistrantSummary[]>("/registrants"),
  getRegistrant: (id: string) => request(`/registrants/${id}`),
  getSources: () => request<SourceSummary[]>("/sources"),
  ingestSource: (source: string) =>
    request(`/ingest/${source}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dry_run: true }),
    }),
};
