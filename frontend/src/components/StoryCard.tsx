import { useCallback, useRef, useState } from "react";
import type { StoryItem } from "../lib/api";
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

function sourceHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return Math.abs(h) % 360;
}

const HOVER_SHOW_DELAY = 500;
const HOVER_HIDE_DELAY = 300;

export default function StoryCard({ story }: { story: StoryItem }) {
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
        onMouseEnter={scheduleShow}
        onMouseLeave={scheduleHide}
        onClick={(e) => {
          if (showPopup) e.preventDefault();
        }}
        className="group flex flex-col bg-hankel-surface rounded-lg overflow-hidden hover:ring-1 hover:ring-hankel-accent transition"
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
            <span>{story.source_name}</span>
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
          onClose={closePopup}
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
        />
      )}
    </>
  );
}
