import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

interface Props {
  storyId: number;
  url: string;
  title: string;
  sourceName: string;
  onClose: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export default function PreviewPopup({
  storyId,
  url,
  title,
  sourceName,
  onClose,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/stories/${storyId}/content`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setContent(data.content || "");
      })
      .catch(() => {
        if (!cancelled) setContent("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storyId]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-[85vw] h-[80vh] max-w-[900px] bg-hankel-bg rounded-xl shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 bg-hankel-surface border-b border-hankel-bg shrink-0">
          <div className="flex items-center gap-2 min-w-0 mr-4">
            <span className="text-xs text-hankel-accent shrink-0">
              {sourceName}
            </span>
            <span className="text-sm text-hankel-muted truncate">{title}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.open(url, "_blank", "noopener,noreferrer");
                onClose();
              }}
              className="px-3 py-1 text-xs bg-hankel-accent text-hankel-bg rounded hover:brightness-110 transition"
            >
              Open in new tab
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
              className="w-7 h-7 flex items-center justify-center text-hankel-muted hover:text-hankel-text rounded transition text-lg leading-none"
            >
              &times;
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-8 py-6">
          {loading && (
            <p className="text-hankel-muted text-sm text-center py-12">
              Loading article...
            </p>
          )}
          {!loading && !content && (
            <div className="flex flex-col items-center justify-center gap-4 py-12 text-hankel-muted">
              <p>Could not extract article content</p>
              <button
                onClick={() => {
                  window.open(url, "_blank", "noopener,noreferrer");
                  onClose();
                }}
                className="px-4 py-2 bg-hankel-accent text-hankel-bg rounded-lg text-sm hover:brightness-110 transition"
              >
                Open in new tab
              </button>
            </div>
          )}
          {!loading && content && (
            <article
              className="reader-view text-hankel-text/90 text-sm leading-relaxed"
              dangerouslySetInnerHTML={{ __html: content }}
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
