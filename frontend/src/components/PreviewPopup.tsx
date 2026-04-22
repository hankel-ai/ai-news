import { createPortal } from "react-dom";
import { useState } from "react";

interface Props {
  url: string;
  title: string;
  onClose: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export default function PreviewPopup({
  url,
  title,
  onClose,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  const [iframeError, setIframeError] = useState(false);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-[85vw] h-[80vh] max-w-[1200px] bg-hankel-bg rounded-xl shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 bg-hankel-surface border-b border-hankel-bg shrink-0">
          <span className="text-sm text-hankel-muted truncate mr-4">{title}</span>
          <div className="flex items-center gap-2">
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
          {!loaded && !iframeError && (
            <div className="absolute inset-0 flex items-center justify-center text-hankel-muted text-sm">
              Loading preview...
            </div>
          )}
          {iframeError ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-hankel-muted">
              <p>Preview unavailable for this site</p>
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
          ) : (
            <iframe
              src={url}
              className="w-full h-full border-0"
              onLoad={() => setLoaded(true)}
              onError={() => setIframeError(true)}
              sandbox="allow-same-origin allow-scripts allow-popups"
              title="Article preview"
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
