import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type StoryItem, type SourceItem } from "../lib/api";
import StoryCard from "../components/StoryCard";

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
    const ts = item.published_at || item.first_seen_at;
    const label = dateLabel(ts);
    const arr = groups.get(label);
    if (arr) arr.push(item);
    else groups.set(label, [item]);
  }
  return Array.from(groups.entries());
}

export default function HeadlinesPage() {
  const qc = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [sourceFilter, setSourceFilter] = useState<number | "">("");
  const [search, setSearch] = useState("");
  const limit = 50;

  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (sourceFilter !== "") params.set("source_id", String(sourceFilter));
  if (search) params.set("q", search);

  const { data, isLoading, error } = useQuery({
    queryKey: ["stories", offset, sourceFilter, search],
    queryFn: () => api.getStories(params.toString()),
  });

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: api.getSources,
  });

  const fetchMutation = useMutation({
    mutationFn: () => api.triggerFetch(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  const grouped = useMemo(
    () => (data ? groupByDate(data.items) : []),
    [data],
  );

  const totalPages = data ? Math.ceil(data.total / limit) : 0;
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <input
          type="text"
          placeholder="Search headlines..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          className="flex-1 min-w-[200px] px-3 py-2 bg-hankel-surface border border-hankel-surface rounded-lg text-hankel-text text-sm placeholder:text-hankel-muted focus:outline-none focus:ring-1 focus:ring-hankel-accent"
        />
        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value === "" ? "" : Number(e.target.value));
            setOffset(0);
          }}
          className="px-3 py-2 bg-hankel-surface border border-hankel-surface rounded-lg text-hankel-text text-sm focus:outline-none focus:ring-1 focus:ring-hankel-accent"
        >
          <option value="">All sources</option>
          {sourcesQuery.data?.items.map((s: SourceItem) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button
          onClick={() => fetchMutation.mutate()}
          disabled={fetchMutation.isPending}
          className="px-4 py-2 bg-hankel-accent text-hankel-bg rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50 transition"
        >
          {fetchMutation.isPending ? "Fetching..." : "Refresh Now"}
        </button>
      </div>

      {fetchMutation.isSuccess && fetchMutation.data && (
        <div className="mb-4 px-3 py-2 bg-hankel-surface rounded-lg text-sm text-hankel-muted">
          Fetched {fetchMutation.data.stories_new} new / {fetchMutation.data.stories_seen} seen
          &middot; {fetchMutation.data.sources_ok} sources OK
          {fetchMutation.data.sources_failed > 0 && (
            <span className="text-red-400">
              {" "}&middot; {fetchMutation.data.sources_failed} failed
            </span>
          )}
          &middot; {fetchMutation.data.duration_ms}ms
        </div>
      )}

      {isLoading && <p className="text-hankel-muted py-8 text-center">Loading...</p>}
      {error && (
        <p className="text-red-400 py-8 text-center">
          Error: {(error as Error).message}
        </p>
      )}

      {data && data.items.length === 0 && (
        <p className="text-hankel-muted py-12 text-center">
          No stories yet. Click "Refresh Now" to fetch headlines.
        </p>
      )}

      {grouped.map(([label, stories]) => (
        <section key={label} className="mb-8">
          <h2 className="text-lg font-semibold text-hankel-text mb-3 border-b border-hankel-surface pb-2">
            {label}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {stories.map((story) => (
              <StoryCard key={story.id} story={story} />
            ))}
          </div>
        </section>
      ))}

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
