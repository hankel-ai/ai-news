import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SettingsMap, type SourceItem, type SourceHealthItem, type ReconcileResult } from "../lib/api";

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

  const analyzeMutation = useMutation({
    mutationFn: () => api.triggerAnalyze(),
  });

  const healthMap = new Map<number, SourceHealthItem>();
  healthData?.items.forEach((h) => healthMap.set(h.source_id, h));

  const sources = sourcesData?.items || [];

  return (
    <section className="mb-8">
      <h2 className="text-lg font-semibold mb-3">Sources</h2>
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
                  <td className="py-2 pr-3 font-medium">{s.name}</td>
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
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="text-xs text-hankel-accent hover:underline disabled:opacity-50"
            >
              {analyzeMutation.isPending ? "Analyzing..." : "Re-analyze"}
            </button>
          </div>
          {analyzeMutation.isSuccess && analyzeMutation.data && (
            <div className="mb-2 text-xs text-green-400 bg-hankel-surface rounded px-3 py-1.5">
              Analyzed {analyzeMutation.data.analyzed} stories
              {analyzeMutation.data.message && ` — ${analyzeMutation.data.message}`}
            </div>
          )}
          {analyzeMutation.isError && (
            <div className="mb-2 text-xs text-red-400 bg-hankel-surface rounded px-3 py-1.5">
              Analysis failed: {(analyzeMutation.error as Error).message}
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
              <button
                onClick={() => setReconcileData(null)}
                className="text-hankel-muted hover:text-hankel-text text-lg"
              >
                &times;
              </button>
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
    mutationFn: () => api.triggerAnalyze(),
  });

  if (isLoading || !settings) return <p className="text-hankel-muted">Loading settings...</p>;

  const merged = { ...settings, ...draft } as SettingsMap;

  function handleChange(key: string, value: unknown) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleRequestPermission() {
    if (!("Notification" in window)) {
      alert("This browser does not support notifications.");
      return;
    }
    Notification.requestPermission().then((perm) => {
      if (perm === "granted") {
        alert("Notifications enabled!");
      } else {
        alert(`Notification permission: ${perm}`);
      }
    });
  }

  function handleTestConnection() {
    testConnectionMutation.mutate(undefined, {
      onSuccess: (data) => {
        alert(`Connection OK — analyzed ${data.analyzed} stories${data.message ? `: ${data.message}` : ""}`);
      },
      onError: (err) => {
        alert(`Connection failed: ${(err as Error).message}`);
      },
    });
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
        <Field label="Hover preview (desktop)">
          <Toggle
            checked={!!merged.hover_preview_enabled}
            onChange={(v) => handleChange("hover_preview_enabled", v)}
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
        <Field label="Breaking threshold">
          <input
            type="number"
            min={1}
            max={100}
            value={Number((merged as Record<string, unknown>).breaking_threshold ?? 3)}
            onChange={(e) => handleChange("breaking_threshold", Number(e.target.value))}
            className="input-field"
          />
        </Field>
        <Field label="">
          <button
            onClick={handleTestConnection}
            disabled={testConnectionMutation.isPending}
            className="px-4 py-2 bg-hankel-surface text-hankel-text rounded-lg text-sm font-medium border border-white/10 hover:border-hankel-accent hover:text-hankel-accent disabled:opacity-50 transition"
          >
            {testConnectionMutation.isPending ? "Testing..." : "Test Connection"}
          </button>
        </Field>
      </div>

      {/* Notifications */}
      <h3 className="text-sm font-medium text-hankel-muted mb-2 mt-6 uppercase tracking-wider">Notifications</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Browser notifications">
          <Toggle
            checked={!!(merged as Record<string, unknown>).notifications_enabled}
            onChange={(v) => handleChange("notifications_enabled", v)}
          />
        </Field>
        <Field label="">
          <button
            onClick={handleRequestPermission}
            className="px-4 py-2 bg-hankel-surface text-hankel-text rounded-lg text-sm font-medium border border-white/10 hover:border-hankel-accent hover:text-hankel-accent transition"
          >
            Request Permission
          </button>
        </Field>
      </div>

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
