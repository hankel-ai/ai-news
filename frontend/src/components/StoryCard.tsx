import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { api, type StoryItem } from "../lib/api";
import PreviewPopup from "./PreviewPopup";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const canHover =
  typeof window !== "undefined" && window.matchMedia("(hover: hover)").matches;

function sourceHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return Math.abs(h) % 360;
}

const HOVER_SHOW_DELAY = 500;
const HOVER_HIDE_DELAY = 300;

interface StoryCardProps {
  story: StoryItem;
  onSourceClick?: (sourceId: number) => void;
}

export default function StoryCard({ story, onSourceClick }: StoryCardProps) {
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
    staleTime: 60_000,
  });
  const hoverEnabled = canHover && (settings?.hover_preview_enabled ?? true);

  const qc = useQueryClient();
  const viewMutation = useMutation({
    mutationFn: () => api.markViewed(story.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  const [imgFailed, setImgFailed] = useState(false);
  const [showPopup, setShowPopup] = useState(false);
  const showTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showImage = story.image_url && !imgFailed;

  const clearTimers = useCallback(() => {
    if (showTimer.current) { clearTimeout(showTimer.current); showTimer.current = null; }
    if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; }
  }, []);

  const scheduleShow = useCallback(() => {
    clearTimers();
    showTimer.current = setTimeout(() => setShowPopup(true), HOVER_SHOW_DELAY);
  }, [clearTimers]);

  const scheduleHide = useCallback(() => {
    if (showTimer.current) { clearTimeout(showTimer.current); showTimer.current = null; }
    hideTimer.current = setTimeout(() => setShowPopup(false), HOVER_HIDE_DELAY);
  }, []);

  const cancelHide = useCallback(() => {
    if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; }
  }, []);

  const closePopup = useCallback(() => {
    clearTimers();
    setShowPopup(false);
  }, [clearTimers]);

  return (
    <>
      <a
        href={story.url}
        target="_blank"
        rel="noopener noreferrer"
        onMouseEnter={hoverEnabled ? scheduleShow : undefined}
        onMouseLeave={hoverEnabled ? scheduleHide : undefined}
        onClick={(e) => {
          if (hoverEnabled && showPopup) {
            e.preventDefault();
          } else if (!story.viewed_at) {
            viewMutation.mutate();
          }
        }}
        className={`group flex flex-col bg-hankel-surface rounded-lg overflow-hidden hover:ring-1 hover:ring-hankel-accent transition ${story.viewed_at ? "opacity-60" : ""}`}
      >
        <div className="relative w-full aspect-[2/1] bg-hankel-bg overflow-hidden">
          {showImage ? (
            <img
              src={story.image_url!}
              alt=""
              loading="lazy"
              onError={() => setImgFailed(true)}
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center"
              style={{
                background: `linear-gradient(135deg, hsl(${sourceHue(story.source_name)}, 35%, 20%) 0%, hsl(${sourceHue(story.source_name) + 40}, 30%, 15%) 100%)`,
              }}
            >
              <span className="text-3xl font-bold text-white/30 select-none">
                {story.source_name}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 p-3 flex-1">
          <h3 className="text-sm font-medium leading-snug text-hankel-text group-hover:text-hankel-accent transition line-clamp-2">
            {story.title}
          </h3>
          <div className="flex items-center gap-1.5 text-xs text-hankel-muted mt-auto pt-1">
            {onSourceClick ? (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onSourceClick(story.source_id);
                }}
                className="hover:text-hankel-accent hover:underline transition"
              >
                {story.source_name}
              </button>
            ) : (
              <span>{story.source_name}</span>
            )}
            <span>&middot;</span>
            <span>{timeAgo(story.first_seen_at)}</span>
            {story.score != null && (
              <>
                <span>&middot;</span>
                <span>{story.score} pts</span>
              </>
            )}
          </div>
          {story.summary && (
            <p className="text-xs text-hankel-muted line-clamp-2 mt-1">
              {story.summary}
            </p>
          )}
        </div>
      </a>

      {showPopup && (
        <PreviewPopup
          url={story.url}
          title={story.title}
          sourceName={story.source_name}
          onClose={closePopup}
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
        />
      )}
    </>
  );
}
