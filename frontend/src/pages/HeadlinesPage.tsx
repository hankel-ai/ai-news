import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type StoryItem, type SettingsMap } from "../lib/api";
import StoryRow from "../components/StoryRow";
import FilterBar from "../components/FilterBar";

function dateLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (today.getTime() - target.getTime()) / 86400000;

  if (diff < 1 && diff >= 0) return "Today";
  if (diff >= 1 && diff < 2) return "Yesterday";
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}

function groupByDate(items: StoryItem[]): [string, StoryItem[]][] {
  const groups = new Map<string, StoryItem[]>();
  for (const item of items) {
    const label = dateLabel(item.first_seen_at);
    const arr = groups.get(label);
    if (arr) arr.push(item);
    else groups.set(label, [item]);
  }
  return Array.from(groups.entries());
}

export default function HeadlinesPage() {
  const qc = useQueryClient();

  // State
  const [sortBy, setSortBy] = useState("relevance");
  const [sourceFilter, setSourceFilter] = useState<number | "">("");
  const [topicFilter, setTopicFilter] = useState("");
  const [scoreThreshold, setScoreThreshold] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const [expandAll, setExpandAll] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // Build query params
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (sortBy !== "relevance") params.set("sort_by", sortBy);
  if (sourceFilter !== "") params.set("source_id", String(sourceFilter));
  if (topicFilter) params.set("topics", topicFilter);
  if (scoreThreshold > 0) params.set("min_score", String(scoreThreshold));
  if (unreadOnly) params.set("unread_only", "true");
  if (search) params.set("q", search);

  // Queries
  const storiesQ = useQuery({
    queryKey: ["stories", offset, sortBy, sourceFilter, topicFilter, scoreThreshold, unreadOnly, search],
    queryFn: () => api.getStories(params.toString()),
  });

  const sourcesQ = useQuery({
    queryKey: ["sources"],
    queryFn: api.getSources,
  });

  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

  // Mutations
  const fetchMut = useMutation({
    mutationFn: () => api.triggerFetch(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  // Load persisted display preferences
  useEffect(() => {
    if (!settingsQ.data) return;
    const s = settingsQ.data as SettingsMap;
    if (s.display_expand_summaries) setExpandAll(true);
    if (s.display_sort_by) setSortBy(String(s.display_sort_by));
    if (s.display_score_threshold) setScoreThreshold(Number(s.display_score_threshold));
  }, [settingsQ.data]);

  // Group by date (settings-driven)
  const groupByDateEnabled = (settingsQ.data as SettingsMap | undefined)?.display_group_by_date ?? true;
  const grouped = useMemo(
    () => (storiesQ.data && groupByDateEnabled ? groupByDate(storiesQ.data.items) : []),
    [storiesQ.data, groupByDateEnabled],
  );

  const stories = storiesQ.data?.items ?? [];
  const totalPages = storiesQ.data ? Math.ceil(storiesQ.data.total / limit) : 0;
  const currentPage = Math.floor(offset / limit) + 1;

  function isExpanded(id: number) {
    return expandAll || expandedIds.has(id);
  }

  function toggleExpanded(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function resetFilters() {
    setSourceFilter("");
    setTopicFilter("");
    setScoreThreshold(0);
    setUnreadOnly(false);
    setSearch("");
    setOffset(0);
  }

  return (
    <div>
      {/* Header bar */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => fetchMut.mutate()}
          disabled={fetchMut.isPending}
          className="px-4 py-2 bg-hankel-accent text-hankel-bg rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50 transition"
        >
          {fetchMut.isPending ? "Fetching..." : "Refresh Now"}
        </button>
        <button
          onClick={() => setExpandAll((v) => !v)}
          className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
            expandAll
              ? "bg-hankel-accent text-hankel-bg border-hankel-accent"
              : "bg-hankel-surface text-hankel-muted border-white/10 hover:text-hankel-text"
          }`}
        >
          {expandAll ? "Collapse All" : "Expand All"}
        </button>
        <div className="flex-1" />
        {storiesQ.data && (
          <span className="text-xs text-hankel-muted">
            {storiesQ.data.total} {storiesQ.data.total === 1 ? "story" : "stories"}
          </span>
        )}
      </div>

      {/* Fetch result */}
      {fetchMut.isSuccess && fetchMut.data && (
        <div className="mb-4 px-3 py-2 bg-hankel-surface rounded-lg text-sm text-hankel-muted">
          Fetched {fetchMut.data.stories_new} new / {fetchMut.data.stories_seen} seen
          &middot; {fetchMut.data.sources_ok} sources OK
          {fetchMut.data.sources_failed > 0 && (
            <span className="text-red-400">
              {" "}&middot; {fetchMut.data.sources_failed} failed
            </span>
          )}
          &middot; {fetchMut.data.duration_ms}ms
        </div>
      )}

      {/* Filter bar */}
      <FilterBar
        sortBy={sortBy}
        onSortChange={(v) => { setSortBy(v); setOffset(0); }}
        sourceFilter={sourceFilter}
        onSourceChange={(v) => { setSourceFilter(v); setOffset(0); }}
        sources={sourcesQ.data?.items ?? []}
        topicFilter={topicFilter}
        onTopicChange={(v) => { setTopicFilter(v); setOffset(0); }}
        scoreThreshold={scoreThreshold}
        onScoreChange={(v) => { setScoreThreshold(v); setOffset(0); }}
        unreadOnly={unreadOnly}
        onUnreadChange={(v) => { setUnreadOnly(v); setOffset(0); }}
        search={search}
        onSearchChange={(v) => { setSearch(v); setOffset(0); }}
      />

      {/* Loading / Error states */}
      {storiesQ.isLoading && <p className="text-hankel-muted py-8 text-center">Loading...</p>}
      {storiesQ.error && (
        <p className="text-red-400 py-8 text-center">
          Error: {(storiesQ.error as Error).message}
        </p>
      )}

      {/* Empty state */}
      {storiesQ.data && stories.length === 0 && (
        <p className="text-hankel-muted py-12 text-center">
          No stories match your filters.{" "}
          <button onClick={resetFilters} className="text-hankel-accent hover:underline">
            Clear filters
          </button>
        </p>
      )}

      {/* Stories list — grouped by date */}
      {groupByDateEnabled &&
        grouped.map(([label, items]) => (
          <section key={label} className="mb-6">
            <h2 className="text-sm font-semibold text-hankel-muted mb-1 px-4 uppercase tracking-wider">
              {label}
            </h2>
            <div className="bg-hankel-surface/30 rounded-lg overflow-hidden">
              {items.map((story) => (
                <StoryRow
                  key={story.id}
                  story={story}
                  expanded={isExpanded(story.id)}
                  onToggle={() => toggleExpanded(story.id)}
                />
              ))}
            </div>
          </section>
        ))}

      {/* Stories list — flat (no date grouping) */}
      {!groupByDateEnabled && stories.length > 0 && (
        <div className="bg-hankel-surface/30 rounded-lg overflow-hidden">
          {stories.map((story) => (
            <StoryRow
              key={story.id}
              story={story}
              expanded={isExpanded(story.id)}
              onToggle={() => toggleExpanded(story.id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-6 text-sm">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            className="px-3 py-1 bg-hankel-surface rounded disabled:opacity-30 hover:bg-hankel-accent hover:text-hankel-bg transition"
          >
            Prev
          </button>
          <span className="text-hankel-muted">
            Page {currentPage} of {totalPages}
          </span>
          <button
            disabled={currentPage >= totalPages}
            onClick={() => setOffset(offset + limit)}
            className="px-3 py-1 bg-hankel-surface rounded disabled:opacity-30 hover:bg-hankel-accent hover:text-hankel-bg transition"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
