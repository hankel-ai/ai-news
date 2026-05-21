import { type SourceItem } from "../lib/api";

interface FilterBarProps {
  sortBy: string;
  onSortChange: (v: string) => void;
  sourceFilter: number | "";
  onSourceChange: (v: number | "") => void;
  sources: SourceItem[];
  topicFilter: string;
  onTopicChange: (v: string) => void;
  scoreThreshold: number;
  onScoreChange: (v: number) => void;
  unreadOnly: boolean;
  onUnreadChange: (v: boolean) => void;
  search: string;
  onSearchChange: (v: string) => void;
}

const SCORE_PRESETS = [
  { label: "All", value: 0 },
  { label: "50+", value: 50 },
  { label: "75+", value: 75 },
];

const TOPIC_OPTIONS = [
  "llm-release",
  "funding",
  "research",
  "open-source",
  "regulation",
  "tutorial",
  "infrastructure",
  "product",
  "acquisition",
  "policy",
];

const selectClass =
  "px-2.5 py-1.5 bg-hankel-surface border border-white/10 rounded-lg text-hankel-text text-xs focus:outline-none focus:ring-1 focus:ring-hankel-accent";

export default function FilterBar({
  sortBy,
  onSortChange,
  sourceFilter,
  onSourceChange,
  sources,
  topicFilter,
  onTopicChange,
  scoreThreshold,
  onScoreChange,
  unreadOnly,
  onUnreadChange,
  search,
  onSearchChange,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      {/* Sort */}
      <select
        value={sortBy}
        onChange={(e) => onSortChange(e.target.value)}
        className={selectClass}
      >
        <option value="relevance">Relevance</option>
        <option value="newest">Newest</option>
        <option value="source">Source</option>
      </select>

      {/* Source */}
      <select
        value={sourceFilter}
        onChange={(e) =>
          onSourceChange(e.target.value === "" ? "" : Number(e.target.value))
        }
        className={selectClass}
      >
        <option value="">All sources</option>
        {sources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>

      {/* Topic */}
      <select
        value={topicFilter}
        onChange={(e) => onTopicChange(e.target.value)}
        className={selectClass}
      >
        <option value="">All topics</option>
        {TOPIC_OPTIONS.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      {/* Score threshold */}
      <div className="flex rounded-lg overflow-hidden border border-white/10">
        {SCORE_PRESETS.map((p) => (
          <button
            key={p.value}
            onClick={() => onScoreChange(p.value)}
            className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
              scoreThreshold === p.value
                ? "bg-hankel-accent text-hankel-bg"
                : "bg-hankel-surface text-hankel-muted hover:text-hankel-text"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Unread toggle */}
      <button
        onClick={() => onUnreadChange(!unreadOnly)}
        className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
          unreadOnly
            ? "bg-hankel-accent text-hankel-bg border-hankel-accent"
            : "bg-hankel-surface text-hankel-muted border-white/10 hover:text-hankel-text"
        }`}
      >
        Unread
      </button>

      {/* Search */}
      <input
        type="text"
        placeholder="Search..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        className="flex-1 min-w-[140px] px-2.5 py-1.5 bg-hankel-surface border border-white/10 rounded-lg text-hankel-text text-xs placeholder:text-hankel-muted focus:outline-none focus:ring-1 focus:ring-hankel-accent"
      />
    </div>
  );
}
