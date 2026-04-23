import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SettingsMap, type SourceItem, type SourceHealthItem } from "../lib/api";

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
          <h3 className="text-sm font-medium text-hankel-muted mb-2">Recent Fetch Runs</h3>
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

  if (isLoading || !settings) return <p className="text-hankel-muted">Loading settings...</p>;

  const merged = { ...settings, ...draft };

  function handleChange(key: keyof SettingsMap, value: unknown) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">Settings</h2>
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
        <Field label="Enrich content">
          <Toggle
            checked={merged.enrich_content}
            onChange={(v) => handleChange("enrich_content", v)}
          />
        </Field>
        <Field label="Group by date">
          <Toggle
            checked={merged.display_group_by_date}
            onChange={(v) => handleChange("display_group_by_date", v)}
          />
        </Field>
      </div>
      <div className="mt-4 flex items-center gap-3">
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
