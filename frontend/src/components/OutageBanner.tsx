import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type LlmStatus } from "../lib/api";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface OutageBannerProps {
  status: LlmStatus;
}

export default function OutageBanner({ status }: OutageBannerProps) {
  const qc = useQueryClient();
  const [checkError, setCheckError] = useState<string | null>(null);

  const pingMut = useMutation({
    mutationFn: () => api.pingLLM(),
    onSuccess: (data) => {
      if (data.ok) {
        qc.invalidateQueries({ queryKey: ["llmStatus"] });
        setCheckError(null);
      } else {
        setCheckError(data.error ?? "still down");
      }
    },
    onError: (e: Error) => setCheckError(e.message),
  });

  if (!status.outage) return null;

  return (
    <div className="mb-4 px-4 py-3 rounded-lg border border-amber-500/40 bg-amber-950/40 text-amber-200 text-sm">
      <div className="flex items-start gap-3">
        <span aria-hidden className="mt-0.5">⚠️</span>
        <div className="flex-1 min-w-0">
          <div className="font-medium">
            AI analysis is down
            {status.since && (
              <span className="font-normal text-amber-200/70"> — down since {timeAgo(status.since)}</span>
            )}
            {status.skipped_runs > 0 && (
              <span className="font-normal text-amber-200/70">
                {", "}
                {status.skipped_runs} {status.skipped_runs === 1 ? "fetch run" : "fetch runs"} skipped analysis
              </span>
            )}
          </div>
          {status.reason && (
            <div className="text-xs text-amber-200/70 mt-0.5 break-words">{status.reason}</div>
          )}
          {checkError && (
            <div className="text-xs text-amber-200/70 mt-0.5">Check failed — {checkError}</div>
          )}
        </div>
        <button
          onClick={() => pingMut.mutate()}
          disabled={pingMut.isPending}
          className="shrink-0 px-3 py-1.5 rounded-lg border border-amber-500/40 text-amber-200 text-xs font-medium hover:bg-amber-500/10 disabled:opacity-50 transition-colors"
        >
          {pingMut.isPending ? "Checking…" : "Check now"}
        </button>
      </div>
    </div>
  );
}
