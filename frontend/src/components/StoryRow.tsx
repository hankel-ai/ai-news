import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type StoryItem } from "../lib/api";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function scoreBadgeColor(score: number | null): string {
  if (score === null) return "bg-hankel-muted/30 text-hankel-muted";
  if (score >= 75) return "bg-green-500 text-black";
  if (score >= 50) return "bg-yellow-500 text-black";
  return "bg-hankel-muted text-black";
}

function sourceHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

interface StoryRowProps {
  story: StoryItem;
  expanded: boolean;
  onToggle: () => void;
}

export default function StoryRow({ story, expanded, onToggle }: StoryRowProps) {
  const qc = useQueryClient();
  const viewMut = useMutation({
    mutationFn: () => api.markViewed(story.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  const handleClick = () => {
    if (!story.viewed_at) viewMut.mutate();
    window.open(story.url, "_blank", "noopener");
  };

  const hasAnalysis = story.ai_summary || story.relevance_score !== null;

  return (
    <div className={`border-b border-white/5 ${story.viewed_at ? "opacity-50" : ""}`}>
      <div className="flex items-center gap-2.5 px-4 py-3">
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-bold ${scoreBadgeColor(story.relevance_score)}`}
        >
          {story.relevance_score ?? "—"}
        </span>
        <button
          onClick={handleClick}
          className="flex-1 text-left text-sm font-medium text-hankel-text hover:text-hankel-accent truncate"
        >
          {story.title}
        </button>
        <span className="shrink-0 text-xs text-hankel-muted hidden sm:inline">
          {sourceHostname(story.url)}
        </span>
        <span className="shrink-0 text-xs text-hankel-muted">
          {timeAgo(story.first_seen_at)}
        </span>
        {hasAnalysis && (
          <button
            onClick={onToggle}
            className="shrink-0 text-xs text-hankel-muted hover:text-hankel-accent"
          >
            {expanded ? "▾" : "▸"}
          </button>
        )}
      </div>
      {expanded && hasAnalysis && (
        <div className="pl-[36px] pr-4 pb-3">
          {story.topics.length > 0 && (
            <div className="flex gap-1.5 mb-2 flex-wrap">
              {story.topics.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] text-indigo-400"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          {story.ai_summary && (
            <div className="rounded-md border-l-2 border-indigo-500 bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-hankel-muted">
              {story.ai_summary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
