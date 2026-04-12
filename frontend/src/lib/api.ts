const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface StoryItem {
  id: number;
  title: string;
  url: string;
  source_id: number;
  source_name: string;
  summary: string | null;
  score: number | null;
  published_at: string | null;
  first_seen_at: string;
  keywords_matched: string | null;
  image_url: string | null;
}

export interface StoriesResponse {
  total: number;
  limit: number;
  offset: number;
  items: StoryItem[];
}

export interface SourceItem {
  id: number;
  key: string;
  name: string;
  type: string;
  url: string | null;
  enabled: boolean;
  keywords: string[] | null;
  max_stories: number;
  min_score: number | null;
  subreddit: string | null;
  sort: string | null;
  extra_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SettingsMap {
  fetch_interval_minutes: number;
  retention_days: number;
  enrich_content: boolean;
  display_group_by_date: boolean;
  display_page_size: number;
  max_stories_per_fetch: number;
  timezone: string;
  [key: string]: unknown;
}

export interface FetchRunItem {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  stories_new: number;
  stories_seen: number;
  sources_ok: number;
  sources_failed: number;
  duration_ms: number | null;
  error: string | null;
}

export interface HealthStatus {
  status: string;
  db: string;
  scheduler: string;
  last_fetch: { id: number; finished_at: string; status: string } | null;
  interval_minutes: number;
}

export interface SourceHealthItem {
  source_id: number;
  total_fetches: number;
  successes: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_stories: number;
  status: string;
}

export const api = {
  getStories: (params?: string) =>
    request<StoriesResponse>(`/api/stories${params ? `?${params}` : ""}`),
  getSources: () => request<{ items: SourceItem[] }>("/api/sources"),
  createSource: (body: Partial<SourceItem>) =>
    request<SourceItem>("/api/sources", { method: "POST", body: JSON.stringify(body) }),
  updateSource: (id: number, body: Partial<SourceItem>) =>
    request<SourceItem>(`/api/sources/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSource: (id: number) =>
    request<void>(`/api/sources/${id}`, { method: "DELETE" }),
  getSettings: () => request<SettingsMap>("/api/settings"),
  updateSettings: (body: Partial<SettingsMap>) =>
    request<SettingsMap>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  triggerFetch: (sourceId?: number) =>
    request<FetchRunItem>(`/api/fetch${sourceId ? `?source_id=${sourceId}` : ""}`, {
      method: "POST",
    }),
  getFetchRuns: (limit = 20) =>
    request<{ items: FetchRunItem[] }>(`/api/fetch-runs?limit=${limit}`),
  getHealth: () => request<HealthStatus>("/api/health"),
  getSourceHealth: () =>
    request<{ items: SourceHealthItem[] }>("/api/source-health"),
};
