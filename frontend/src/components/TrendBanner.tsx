import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type AlertItem } from "../lib/api";

interface TrendBannerProps {
  alerts: AlertItem[];
  onTopicClick?: (topic: string) => void;
}

const severityStyles: Record<string, string> = {
  breaking:
    "bg-red-500/15 border-red-500/40 text-red-300",
  trending:
    "bg-yellow-500/15 border-yellow-500/40 text-yellow-300",
  normal:
    "bg-indigo-500/15 border-indigo-500/40 text-indigo-300",
};

export default function TrendBanner({ alerts, onTopicClick }: TrendBannerProps) {
  const qc = useQueryClient();
  const ackMut = useMutation({
    mutationFn: (id: number) => api.ackAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  if (alerts.length === 0) return null;

  return (
    <div className="flex flex-col gap-2 mb-4">
      {alerts.map((a) => (
        <div
          key={a.id}
          className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border text-sm ${severityStyles[a.severity] ?? severityStyles.normal}`}
        >
          <span className="font-bold uppercase text-[10px] tracking-wider shrink-0">
            {a.severity}
          </span>
          <button
            onClick={() => onTopicClick?.(a.topic)}
            className="font-medium hover:underline truncate"
          >
            {a.topic}
          </button>
          <span className="text-xs opacity-70 shrink-0">
            {a.story_count} {a.story_count === 1 ? "story" : "stories"}
          </span>
          <button
            onClick={() => ackMut.mutate(a.id)}
            disabled={ackMut.isPending}
            className="ml-auto shrink-0 opacity-60 hover:opacity-100 transition text-lg leading-none"
            aria-label="Dismiss"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  );
}
