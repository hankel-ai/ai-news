import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SettingsMap, type SourceItem, type SourceHealthItem, type ReconcileResult } from "../lib/api";

function sourceWebsiteUrl(s: SourceItem): string | null {
  if (s.url) {
    try {
      return new URL(s.url).origin;
    } catch {
      return s.url;
    }
  }
  if (s.subreddit) return `https://reddit.com/r/${s.subreddit}`;
  if (s.key === "hackernews") return "https://news.ycombinator.com";
  if (s.key === "claude_blog") return "https://www.anthropic.com/news";
  return null;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: "bg-green-900 text-green-300",
    degraded: "bg-yellow-900 text-yellow-300",
    broken: "bg-red-900 text-red-300",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[status] || "bg-gray-700 text-gray-300"}`}>
      {status}
    </span>
  );
}

function SourcesSection() {
  const qc = useQueryClient();
  const { data: sourcesData } = useQuery({ queryKey: ["sources"], queryFn: api.getSources });
  const { data: healthData } = useQuery({ queryKey: ["sourceHealth"], queryFn: api.getSourceHealth });
  const { data: runsData } = useQuery({ queryKey: ["fetchRuns"], queryFn: () => api.getFetchRuns(10) });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<SourceItem> }) =>
      api.updateSource(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteSource(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  const testMutation = useMutation({
    mutationFn: (sourceId: number) => api.triggerFetch(sourceId),
  });

  const [reconcileData, setReconcileData] = useState<ReconcileResult | null>(null);
  const reconcileMutation = useMutation({
    mutationFn: (sourceId: number) => api.reconcileSource(sourceId),
    onSuccess: (data) => setReconcileData(data),
  });

  const [analyzeState, setAnalyzeState] = useState<{
    running: boolean;
    done: number;
    remaining: number | null;
    error: string | null;
    lastBatchMs: number | null;
  }>({ running: false, done: 0, remaining: null, error: null, lastBatchMs: null });

  async function runAnalyze() {
    setAnalyzeState({ running: true, done: 0, remaining: null, error: null, lastBatchMs: null });
    let done = 0;
    while (true) {
      let r;
      try {
        r = await api.triggerAnalyze(20);
      } catch (e) {
        setAnalyzeState({ running: false, done, remaining: null, error: (e as Error).message, lastBatchMs: null });
        return;
      }
      done += r.analyzed;
      if (!r.ok) {
        setAnalyzeState({ running: false, done, remaining: r.remaining, error: r.error ?? "unknown error", lastBatchMs: r.duration_ms });
        qc.invalidateQueries({ queryKey: ["stories"] });
        return;
      }
      setAnalyzeState({ running: r.remaining > 0, done, remaining: r.remaining, error: null, lastBatchMs: r.duration_ms });
      if (r.remaining === 0) break;
    }
    qc.invalidateQueries({ queryKey: ["stories"] });
  }

  const importMissingMutation = useMutation({
    mutationFn: (sourceId: number) => api.importMissingFromSource(sourceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
      setReconcileData(null);
    },
  });

  const [showAddForm, setShowAddForm] = useState(false);
  const createMutation = useMutation({
    mutationFn: (body: Partial<SourceItem>) => api.createSource(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      setShowAddForm(false);
    },
  });

  const healthMap = new Map<number, SourceHealthItem>();
  healthData?.items.forEach((h) => healthMap.set(h.source_id, h));

  const sources = sourcesData?.items || [];

  return (
    <section className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Sources</h2>
        <button
          onClick={() => setShowAddForm((v) => !v)}
          className="text-xs px-3 py-1 bg-hankel-accent text-hankel-bg rounded font-medium hover:brightness-110 transition"
        >
          {showAddForm ? "Cancel" : "+ Add Source"}
        </button>
      </div>

      {showAddForm && (
        <AddSourceForm
          onSubmit={(body) => createMutation.mutate(body)}
          onCancel={() => setShowAddForm(false)}
          isPending={createMutation.isPending}
          error={createMutation.error ? (createMutation.error as Error).message : null}
        />
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-hankel-muted text-left border-b border-hankel-surface">
              <th className="py-2 pr-3">On</th>
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">Type</th>
              <th className="py-2 pr-3">Max</th>
              <th className="py-2 pr-3">Health</th>
              <th className="py-2 pr-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s: SourceItem) => {
              const h = healthMap.get(s.id);
              return (
                <tr key={s.id} className="border-b border-hankel-surface/50">
                  <td className="py-2 pr-3">
                    <button
                      onClick={() => updateMutation.mutate({ id: s.id, body: { enabled: !s.enabled } })}
                      className={`w-8 h-5 rounded-full transition ${s.enabled ? "bg-hankel-accent" : "bg-gray-600"} relative`}
                    >
                      <span className={`block w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 transition-all ${s.enabled ? "left-4" : "left-0.5"}`} />
                    </button>
                  </td>
                  <td className="py-2 pr-3 font-medium">
                    {(() => {
                      const href = sourceWebsiteUrl(s);
                      return href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-hankel-accent hover:underline"
                        >
                          {s.name}
                        </a>
                      ) : (
                        s.name
                      );
                    })()}
                  </td>
                  <td className="py-2 pr-3 text-hankel-muted">{s.type}</td>
                  <td className="py-2 pr-3">
                    <MaxStoriesInput
                      value={s.max_stories}
                      onCommit={(v) => updateMutation.mutate({ id: s.id, body: { max_stories: v } })}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    {h ? <StatusBadge status={h.status} /> : <span className="text-hankel-muted text-xs">-</span>}
                  </td>
                  <td className="py-2 pr-3 flex gap-2">
                    <button
                      onClick={() => testMutation.mutate(s.id)}
                      disabled={testMutation.isPending}
                      className="text-xs text-hankel-accent hover:underline disabled:opacity-50"
                    >
                      Test
                    </button>
                    <button
                      onClick={() => reconcileMutation.mutate(s.id)}
                      disabled={reconcileMutation.isPending}
                      className="text-xs text-hankel-accent hover:underline disabled:opacity-50"
                    >
                      Reconcile
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete source "${s.name}"?`)) deleteMutation.mutate(s.id);
                      }}
                      className="text-xs text-red-400 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {testMutation.isSuccess && testMutation.data && (
        <div className="mt-2 text-xs text-hankel-muted bg-hankel-surface rounded px-3 py-2">
          Test: {testMutation.data.stories_new} new, {testMutation.data.stories_seen} seen, {testMutation.data.duration_ms}ms
        </div>
      )}

      {runsData && runsData.items.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-hankel-muted">Recent Fetch Runs</h3>
            <button
              onClick={runAnalyze}
              disabled={analyzeState.running}
              className="text-xs text-hankel-accent hover:underline disabled:opacity-50"
            >
              {analyzeState.running ? "Analyzing..." : "Re-analyze"}
            </button>
          </div>
          {(analyzeState.running || analyzeState.done > 0 || analyzeState.error) && (
            <div className={`mb-2 text-xs bg-hankel-surface rounded px-3 py-1.5 ${analyzeState.error ? "text-red-400" : "text-green-400"}`}>
              {analyzeState.running
                ? `Analyzed ${analyzeState.done}, ${analyzeState.remaining ?? "?"} remaining${analyzeState.lastBatchMs ? ` (last batch ${analyzeState.lastBatchMs}ms)` : ""}`
                : analyzeState.error
                  ? `Stopped after ${analyzeState.done} — ${analyzeState.error}`
                  : `Done — analyzed ${analyzeState.done} stories`}
            </div>
          )}
          <div className="space-y-1">
            {runsData.items.slice(0, 5).map((r) => (
              <div key={r.id} className="flex items-center gap-3 text-xs text-hankel-muted bg-hankel-surface/50 rounded px-3 py-1.5">
                <span className={r.status === "success" ? "text-green-400" : r.status === "partial" ? "text-yellow-400" : "text-red-400"}>
                  {r.status}
                </span>
                <span>+{r.stories_new} new / {r.stories_seen} seen</span>
                <span>{r.sources_ok} ok{r.sources_failed > 0 ? `, ${r.sources_failed} fail` : ""}</span>
                <span>{r.duration_ms}ms</span>
                <span className="ml-auto">{r.started_at?.slice(0, 16).replace("T", " ")}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {reconcileMutation.isPending && (
        <div className="mt-2 text-xs text-hankel-muted bg-hankel-surface rounded px-3 py-2">
          Reconciling...
        </div>
      )}

      {reconcileData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setReconcileData(null)} />
          <div className="relative w-[90vw] max-w-2xl max-h-[80vh] bg-hankel-bg rounded-xl shadow-2xl overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 bg-hankel-surface border-b border-hankel-bg">
              <h3 className="text-sm font-semibold">
                Reconcile: {reconcileData.source_name}
              </h3>
              <div className="flex items-center gap-3">
                {reconcileData.missing_count > 0 && (
                  <button
                    onClick={() => importMissingMutation.mutate(reconcileData.source_id)}
                    disabled={importMissingMutation.isPending}
                    className="text-xs px-3 py-1 bg-hankel-accent text-hankel-bg rounded hover:brightness-110 disabled:opacity-50 transition"
                  >
                    {importMissingMutation.isPending
                      ? "Importing..."
                      : `Import ${reconcileData.missing_count} Missing`}
                  </button>
                )}
                <button
                  onClick={() => setReconcileData(null)}
                  className="text-hankel-muted hover:text-hankel-text text-lg"
                >
                  &times;
                </button>
              </div>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              <div className="flex gap-4 mb-4 text-sm">
                <span className="text-hankel-muted">
                  Available: {reconcileData.available_count}
                </span>
                <span className="text-green-400">
                  Matched: {reconcileData.matched_count}
                </span>
                <span className="text-yellow-400">
                  Missing: {reconcileData.missing_count}
                </span>
              </div>
              {reconcileData.missing.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-yellow-400 mb-2">
                    Missing Articles
                  </h4>
                  <div className="space-y-1">
                    {reconcileData.missing.map((item, i) => (
                      <a
                        key={i}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block text-xs text-hankel-muted hover:text-hankel-accent truncate"
                      >
                        {item.title}
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {reconcileData.matched.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-green-400 mb-2">
                    Matched Articles
                  </h4>
                  <div className="space-y-1">
                    {reconcileData.matched.map((item, i) => (
                      <div key={i} className="text-xs text-hankel-muted truncate">
                        {item.title}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function SettingsForm() {
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [draft, setDraft] = useState<Partial<SettingsMap>>({});
  const [saved, setSaved] = useState(false);

  const saveMutation = useMutation({
    mutationFn: (body: Partial<SettingsMap>) => api.updateSettings(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setDraft({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const testConnectionMutation = useMutation({
    mutationFn: () => api.pingLLM(),
  });
  const hasDraftLLMChange = ["llm_provider", "llm_model", "llm_base_url", "llm_api_key"].some(
    (k) => k in draft,
  );

  if (isLoading || !settings) return <p className="text-hankel-muted">Loading settings...</p>;

  const merged = { ...settings, ...draft } as SettingsMap;

  function handleChange(key: string, value: unknown) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleTestConnection() {
    testConnectionMutation.mutate();
  }

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">Settings</h2>

      {/* General */}
      <h3 className="text-sm font-medium text-hankel-muted mb-2 mt-4 uppercase tracking-wider">General</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Fetch interval (minutes)">
          <input
            type="number"
            min={5}
            max={1440}
            value={merged.fetch_interval_minutes}
            onChange={(e) => handleChange("fetch_interval_minutes", Number(e.target.value))}
            className="input-field"
          />
        </Field>
        <Field label="Retention (days)">
          <input
            type="number"
            min={1}
            max={365}
            value={merged.retention_days}
            onChange={(e) => handleChange("retention_days", Number(e.target.value))}
            className="input-field"
          />
        </Field>
        <Field label="Enrich content">
          <Toggle
            checked={!!merged.enrich_content}
            onChange={(v) => handleChange("enrich_content", v)}
          />
        </Field>
      </div>

      {/* Display */}
      <h3 className="text-sm font-medium text-hankel-muted mb-2 mt-6 uppercase tracking-wider">Display</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Page size">
          <input
            type="number"
            min={10}
            max={200}
            value={merged.display_page_size}
            onChange={(e) => handleChange("display_page_size", Number(e.target.value))}
            className="input-field"
          />
        </Field>
        <Field label="Group by date">
          <Toggle
            checked={!!merged.display_group_by_date}
            onChange={(v) => handleChange("display_group_by_date", v)}
          />
        </Field>
        <Field label="Expand summaries by default">
          <Toggle
            checked={!!(merged as Record<string, unknown>).display_expand_summaries}
            onChange={(v) => handleChange("display_expand_summaries", v)}
          />
        </Field>
        <Field label="Default sort">
          <select
            value={String((merged as Record<string, unknown>).display_sort_by ?? "relevance")}
            onChange={(e) => handleChange("display_sort_by", e.target.value)}
            className="input-field"
          >
            <option value="relevance">Relevance</option>
            <option value="newest">Newest</option>
            <option value="source">Source</option>
          </select>
        </Field>
        <Field label="Min score to display">
          <input
            type="number"
            min={0}
            max={100}
            value={Number((merged as Record<string, unknown>).display_score_threshold ?? 0)}
            onChange={(e) => handleChange("display_score_threshold", Number(e.target.value))}
            className="input-field"
          />
        </Field>
      </div>

      {/* AI Configuration */}
      <h3 className="text-sm font-medium text-hankel-muted mb-2 mt-6 uppercase tracking-wider">AI Configuration</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="LLM Provider">
          <select
            value={String((merged as Record<string, unknown>).llm_provider ?? "ollama")}
            onChange={(e) => handleChange("llm_provider", e.target.value)}
            className="input-field"
          >
            <option value="ollama">Ollama</option>
            <option value="anthropic">Anthropic</option>
            <option value="litellm">LiteLLM</option>
          </select>
        </Field>
        <Field label="Model">
          <input
            type="text"
            value={String((merged as Record<string, unknown>).llm_model ?? "")}
            onChange={(e) => handleChange("llm_model", e.target.value)}
            placeholder="e.g. llama3, claude-sonnet-4-20250514"
            className="input-field"
          />
        </Field>
        <Field label="Base URL">
          <input
            type="text"
            value={String((merged as Record<string, unknown>).llm_base_url ?? "")}
            onChange={(e) => handleChange("llm_base_url", e.target.value)}
            placeholder="e.g. http://localhost:11434"
            className="input-field"
          />
        </Field>
        <Field label="API Key">
          <input
            type="password"
            value={String((merged as Record<string, unknown>).llm_api_key ?? "")}
            onChange={(e) => handleChange("llm_api_key", e.target.value)}
            placeholder="sk-..."
            className="input-field"
          />
        </Field>
        <Field label="Auto-analyze on fetch">
          <Toggle
            checked={!!(merged as Record<string, unknown>).analysis_enabled}
            onChange={(v) => handleChange("analysis_enabled", v)}
          />
        </Field>
        <Field label="">
          <div className="flex items-center gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testConnectionMutation.isPending}
              className="px-4 py-2 bg-hankel-surface text-hankel-text rounded-lg text-sm font-medium border border-white/10 hover:border-hankel-accent hover:text-hankel-accent disabled:opacity-50 transition"
            >
              {testConnectionMutation.isPending ? "Testing..." : "Test Connection"}
            </button>
            {hasDraftLLMChange && (
              <span className="text-xs text-yellow-400">Save first — test uses saved values</span>
            )}
          </div>
        </Field>
      </div>

      <LLMTestResult mutation={testConnectionMutation} />

      {/* Save */}
      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={() => saveMutation.mutate(draft)}
          disabled={Object.keys(draft).length === 0 || saveMutation.isPending}
          className="px-5 py-2 bg-hankel-accent text-hankel-bg rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50 transition"
        >
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
        {saved && <span className="text-sm text-green-400">Saved!</span>}
      </div>
    </section>
  );
}

const SOURCE_TYPE_OPTIONS: { value: string; label: string; needs: ("url" | "subreddit" | "sort" | "key_choice" | "link_pattern")[] }[] = [
  { value: "rss", label: "RSS feed", needs: ["url"] },
  { value: "html_links", label: "HTML page (track new links)", needs: ["url", "link_pattern"] },
  { value: "reddit_json", label: "Reddit (subreddit)", needs: ["subreddit", "sort"] },
  { value: "hackernews_api", label: "Hacker News (top)", needs: [] },
  { value: "claude_blog", label: "Anthropic news", needs: [] },
  { value: "html_scraper", label: "HTML scraper (techmeme/implicator)", needs: ["key_choice"] },
];

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
}

type DetectResult = Awaited<ReturnType<typeof api.detectFeed>>;

function AddSourceForm({
  onSubmit,
  onCancel,
  isPending,
  error,
}: {
  onSubmit: (body: Partial<SourceItem>) => void;
  onCancel: () => void;
  isPending: boolean;
  error: string | null;
}) {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [keyEdited, setKeyEdited] = useState(false);
  const [type, setType] = useState("rss");
  const [url, setUrl] = useState("");
  const [linkPattern, setLinkPattern] = useState("");
  const [subreddit, setSubreddit] = useState("");
  const [sort, setSort] = useState("hot");
  const [scraperKey, setScraperKey] = useState("techmeme");
  const [maxStories, setMaxStories] = useState(10);
  const [keywords, setKeywords] = useState("");
  const [minScore, setMinScore] = useState("");

  const typeMeta = SOURCE_TYPE_OPTIONS.find((t) => t.value === type)!;
  const needsUrl = typeMeta.needs.includes("url");
  const needsSubreddit = typeMeta.needs.includes("subreddit");
  const needsScraperKey = typeMeta.needs.includes("key_choice");
  const needsLinkPattern = typeMeta.needs.includes("link_pattern");

  const detectMutation = useMutation({
    mutationFn: (u: string) => api.detectFeed(u),
    onSuccess: (data) => {
      if (data.feeds.length > 0) {
        setType("rss");
        setUrl(data.feeds[0].url);
      } else if (data.fallback) {
        setType("html_links");
        setUrl(data.fallback.url);
      }
    },
  });
  const detect: DetectResult | undefined = detectMutation.data;

  function effectiveKey(): string {
    if (needsScraperKey) return scraperKey;
    if (keyEdited && key) return key;
    if (name) return slugify(name);
    return key;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: Partial<SourceItem> & {
      key: string;
      type: string;
      name: string;
    } = {
      key: effectiveKey(),
      name: name.trim(),
      type,
      enabled: true,
      max_stories: maxStories,
    };
    if (needsUrl) body.url = url.trim();
    if (needsSubreddit) {
      body.subreddit = subreddit.trim().replace(/^\/?r\//, "");
      body.sort = sort;
    }
    if (needsLinkPattern && linkPattern.trim()) {
      body.extra_config = { link_pattern: linkPattern.trim() };
    }
    const kwList = keywords.split(",").map((s) => s.trim()).filter(Boolean);
    if (kwList.length) body.keywords = kwList;
    if (minScore.trim()) {
      const n = Number(minScore);
      if (Number.isFinite(n)) body.min_score = n;
    }
    onSubmit(body);
  }

  const submitDisabled =
    isPending ||
    !name.trim() ||
    !effectiveKey() ||
    (needsUrl && !url.trim()) ||
    (needsSubreddit && !subreddit.trim());

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-4 p-4 bg-hankel-surface/60 border border-white/10 rounded-lg"
    >
      <h3 className="text-sm font-medium mb-3">Add Source</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <Field label="Name *">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. The Verge AI"
            className="input-field"
            autoFocus
          />
        </Field>
        <Field label="Type *">
          <select value={type} onChange={(e) => setType(e.target.value)} className="input-field">
            {SOURCE_TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        {needsScraperKey ? (
          <Field label="Scraper *">
            <select
              value={scraperKey}
              onChange={(e) => setScraperKey(e.target.value)}
              className="input-field"
            >
              <option value="techmeme">techmeme</option>
              <option value="implicator">implicator</option>
            </select>
          </Field>
        ) : (
          <Field label="Key (slug)">
            <input
              type="text"
              value={keyEdited ? key : slugify(name)}
              onChange={(e) => {
                setKey(e.target.value);
                setKeyEdited(true);
              }}
              placeholder="auto from name"
              className="input-field"
            />
          </Field>
        )}
        {needsUrl && (
          <Field label="URL *">
            <div className="flex gap-2">
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/feed.xml or any page"
                className="input-field flex-1"
              />
              <button
                type="button"
                onClick={() => url.trim() && detectMutation.mutate(url.trim())}
                disabled={!url.trim() || detectMutation.isPending}
                className="px-3 py-1 bg-hankel-surface border border-white/10 hover:border-hankel-accent rounded text-xs whitespace-nowrap disabled:opacity-50"
                title="Find an RSS/Atom feed or fall back to HTML link tracking"
              >
                {detectMutation.isPending ? "Detecting..." : "Detect"}
              </button>
            </div>
          </Field>
        )}
        {needsLinkPattern && (
          <Field label="Link pattern (regex, optional)">
            <input
              type="text"
              value={linkPattern}
              onChange={(e) => setLinkPattern(e.target.value)}
              placeholder="e.g. /whats-new/  (leave blank to track all sub-pages)"
              className="input-field"
            />
          </Field>
        )}
        {needsSubreddit && (
          <>
            <Field label="Subreddit *">
              <input
                type="text"
                value={subreddit}
                onChange={(e) => setSubreddit(e.target.value)}
                placeholder="MachineLearning"
                className="input-field"
              />
            </Field>
            <Field label="Sort">
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                className="input-field"
              >
                <option value="hot">hot</option>
                <option value="new">new</option>
                <option value="top">top</option>
                <option value="rising">rising</option>
              </select>
            </Field>
          </>
        )}
        <Field label="Max stories per fetch">
          <input
            type="number"
            min={1}
            max={100}
            value={maxStories}
            onChange={(e) => setMaxStories(Number(e.target.value) || 10)}
            className="input-field"
          />
        </Field>
        <Field label="Min score (optional)">
          <input
            type="number"
            min={0}
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="HN: e.g. 50"
            className="input-field"
          />
        </Field>
        <Field label="Keywords (comma-separated, optional)">
          <input
            type="text"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="ai, llm, agents"
            className="input-field"
          />
        </Field>
      </div>
      {detectMutation.isError && (
        <div className="mt-3 text-xs text-red-300 bg-red-950/50 border border-red-900 rounded px-3 py-2">
          Detect failed: {(detectMutation.error as Error).message}
        </div>
      )}
      {detect && !detectMutation.isError && (
        <div className="mt-3 text-xs bg-hankel-surface/80 border border-white/10 rounded px-3 py-2">
          {detect.error ? (
            <span className="text-red-300">Could not fetch: {detect.error}</span>
          ) : detect.feeds.length > 0 ? (
            <div>
              <div className="text-green-300 font-medium mb-1">
                Found {detect.feeds.length} feed{detect.feeds.length > 1 ? "s" : ""} — switched to RSS.
              </div>
              {detect.feeds.map((f, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    setType("rss");
                    setUrl(f.url);
                  }}
                  className="block text-left hover:text-hankel-accent break-all"
                >
                  {f.title}: <span className="font-mono">{f.url}</span>
                </button>
              ))}
            </div>
          ) : detect.fallback ? (
            <div>
              <div className="text-yellow-300 font-medium mb-1">{detect.fallback.hint}</div>
              {detect.fallback.anchor_sample.length > 0 ? (
                <div>
                  <div className="text-hankel-muted mb-1">
                    Preview ({detect.fallback.anchor_sample.length} sample link
                    {detect.fallback.anchor_sample.length > 1 ? "s" : ""}):
                  </div>
                  <ul className="space-y-0.5">
                    {detect.fallback.anchor_sample.map((s, i) => (
                      <li key={i} className="truncate text-hankel-muted">
                        · <span className="text-hankel-text">{s.title}</span>{" "}
                        <span className="font-mono text-[10px]">{s.url}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="text-hankel-muted">
                  No suitable links found on this page. You may need a different URL or a
                  link pattern.
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
      {error && (
        <div className="mt-3 text-xs text-red-300 bg-red-950/50 border border-red-900 rounded px-3 py-2">
          {error}
        </div>
      )}
      <div className="mt-4 flex items-center gap-3">
        <button
          type="submit"
          disabled={submitDisabled}
          className="px-4 py-1.5 bg-hankel-accent text-hankel-bg rounded text-sm font-medium hover:brightness-110 disabled:opacity-50 transition"
        >
          {isPending ? "Adding..." : "Add"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-1.5 text-hankel-muted hover:text-hankel-text text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

type LLMPingResult = Awaited<ReturnType<typeof api.pingLLM>>;

function LLMTestResult({
  mutation,
}: {
  mutation: { isPending: boolean; data?: LLMPingResult; error: unknown };
}) {
  if (mutation.isPending) {
    return (
      <div className="mt-3 text-xs text-hankel-muted bg-hankel-surface rounded px-3 py-2">
        Testing connection...
      </div>
    );
  }
  if (mutation.error) {
    return (
      <div className="mt-3 text-xs text-red-300 bg-red-950/50 border border-red-900 rounded px-3 py-2">
        Request failed: {(mutation.error as Error).message}
      </div>
    );
  }
  const data = mutation.data;
  if (!data) return null;
  return (
    <div
      className={`mt-3 text-xs rounded px-3 py-2 border ${
        data.ok
          ? "bg-green-950/40 border-green-900 text-green-200"
          : "bg-red-950/40 border-red-900 text-red-200"
      }`}
    >
      <div className="font-semibold mb-1">
        {data.ok ? "Connection OK" : "Connection failed"} · {data.duration_ms}ms
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 font-mono">
        <dt className="text-hankel-muted">provider</dt>
        <dd>{data.provider}</dd>
        <dt className="text-hankel-muted">model</dt>
        <dd>{data.model}</dd>
        <dt className="text-hankel-muted">base_url</dt>
        <dd className="break-all">{data.base_url || "<empty>"}</dd>
        <dt className="text-hankel-muted">endpoint</dt>
        <dd className="break-all">{data.endpoint || "<empty>"}</dd>
        {data.http_status !== undefined && (
          <>
            <dt className="text-hankel-muted">http_status</dt>
            <dd>{data.http_status}</dd>
          </>
        )}
        {data.error_type && (
          <>
            <dt className="text-hankel-muted">error_type</dt>
            <dd>{data.error_type}</dd>
          </>
        )}
        {data.error && (
          <>
            <dt className="text-hankel-muted">error</dt>
            <dd className="break-words whitespace-pre-wrap">{data.error}</dd>
          </>
        )}
        {data.reply && (
          <>
            <dt className="text-hankel-muted">reply</dt>
            <dd className="break-words whitespace-pre-wrap">{data.reply}</dd>
          </>
        )}
      </dl>
      {data.available_models && data.available_models.length > 0 && (
        <div className="mt-2 pt-2 border-t border-red-900/60">
          <div className="text-hankel-muted mb-1">Available models on this Ollama:</div>
          <div className="flex flex-wrap gap-1.5">
            {data.available_models.map((m) => (
              <code key={m} className="px-1.5 py-0.5 bg-hankel-surface rounded text-[11px]">
                {m}
              </code>
            ))}
          </div>
        </div>
      )}
      {data.available_models && data.available_models.length === 0 && (
        <div className="mt-2 pt-2 border-t border-red-900/60 text-hankel-muted">
          Ollama reachable but reports zero installed models. Run <code>ollama pull &lt;model&gt;</code>.
        </div>
      )}
    </div>
  );
}

function MaxStoriesInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);

  function commit() {
    const n = Number(draft);
    if (!Number.isFinite(n) || n < 1 || n === value) {
      setDraft(String(value));
      return;
    }
    onCommit(n);
  }

  return (
    <input
      type="number"
      min={1}
      max={100}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setDraft(String(value));
      }}
      className="w-16 px-2 py-0.5 bg-hankel-surface rounded text-sm text-hankel-muted focus:outline-none focus:ring-1 focus:ring-hankel-accent"
    />
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm text-hankel-muted mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`w-10 h-6 rounded-full transition ${checked ? "bg-hankel-accent" : "bg-gray-600"} relative`}
    >
      <span className={`block w-4 h-4 bg-white rounded-full absolute top-1 transition-all ${checked ? "left-5" : "left-1"}`} />
    </button>
  );
}

export default function SettingsPage() {
  return (
    <div>
      <SourcesSection />
      <SettingsForm />

      <style>{`
        .input-field {
          width: 100%;
          padding: 0.5rem 0.75rem;
          background: #1e293b;
          border: 1px solid #1e293b;
          border-radius: 0.5rem;
          color: #e2e8f0;
          font-size: 0.875rem;
          outline: none;
        }
        .input-field:focus {
          box-shadow: 0 0 0 1px #60a5fa;
        }
      `}</style>
    </div>
  );
}
