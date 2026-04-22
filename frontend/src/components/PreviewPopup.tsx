import { createPortal } from "react-dom";
import { useState } from "react";

interface Props {
  url: string;
  title: string;
  sourceName: string;
  onClose: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export default function PreviewPopup({
  url,
  title,
  sourceName,
  onClose,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const [loaded, setLoaded] = useState(false);

  const proxyUrl = `/api/proxy?url=${encodeURIComponent(url)}`;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-[90vw] h-[85vh] max-w-[1400px] bg-hankel-bg rounded-xl shadow-2xl overflow-hidden flex flex-col">
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

        <div className="relative flex-1">
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center text-hankel-muted text-sm z-10">
              Loading preview...
            </div>
          )}
          <iframe
            src={proxyUrl}
            className="w-full h-full border-0"
            onLoad={() => setLoaded(true)}
            title="Article preview"
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
