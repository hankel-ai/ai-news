import { useState } from "react";
import type { StoryItem } from "../lib/api";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='200' fill='%231e293b'%3E%3Crect width='400' height='200'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-family='sans-serif' font-size='14' fill='%2394a3b8'%3ENo image%3C/text%3E%3C/svg%3E";

export default function StoryCard({ story }: { story: StoryItem }) {
  const [imgSrc, setImgSrc] = useState(story.image_url || PLACEHOLDER);

  return (
    <a
      href={story.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col bg-hankel-surface rounded-lg overflow-hidden hover:ring-1 hover:ring-hankel-accent transition"
    >
      <div className="relative w-full aspect-[2/1] bg-hankel-bg overflow-hidden">
        <img
          src={imgSrc}
          alt=""
          loading="lazy"
          onError={() => setImgSrc(PLACEHOLDER)}
          className="w-full h-full object-cover"
        />
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
  );
}
