import { Clock3, Languages, Mic, PhoneCall } from "lucide-react";

import { OutcomeBadge } from "@/components/status-badge";
import { RecordingPlayer } from "@/components/recording-player";
import { formatDateTime, formatDuration, humanize, languageLabel } from "@/lib/format";
import type { CallLog } from "@/services/api";

/** Each attempt to reach the customer, newest first, with transcript and recording. */
export function CallLogList({ logs, withRecordings = true }: { logs: CallLog[]; withRecordings?: boolean }) {
  if (!logs.length) {
    return <p className="text-sm text-muted-foreground">No calls have been placed for this order yet.</p>;
  }
  const ordered = [...logs].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return (
    <ol className="space-y-4">
      {ordered.map((log, index) => (
        <li key={log.id} className="rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">Attempt {ordered.length - index}</span>
              <OutcomeBadge outcome={log.outcome} />
              {log.call_status && log.call_status !== log.outcome && (
                <span className="text-xs text-muted-foreground">Twilio: {humanize(log.call_status)}</span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">{formatDateTime(log.created_at)}</span>
          </div>
          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
            <div className="inline-flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5" />
              <dt className="sr-only">Duration</dt>
              <dd>{formatDuration(log.duration_secs)}</dd>
            </div>
            <div className="inline-flex items-center gap-1.5">
              <Languages className="h-3.5 w-3.5" />
              <dt className="sr-only">Language</dt>
              <dd>{languageLabel(log.language)}</dd>
            </div>
            {log.final_node && (
              <div className="inline-flex items-center gap-1.5">
                <PhoneCall className="h-3.5 w-3.5" />
                <dt className="sr-only">Ended at</dt>
                <dd>Ended at {humanize(log.final_node)}</dd>
              </div>
            )}
            {log.twilio_call_sid && (
              <div className="inline-flex items-center gap-1.5 font-mono">
                <dt className="sr-only">Call SID</dt>
                <dd>{log.twilio_call_sid}</dd>
              </div>
            )}
          </dl>
          {log.transcript ? (
            <pre className="transcript mt-3 max-h-64 overflow-y-auto font-sans">
              {log.transcript}
            </pre>
          ) : (
            <p className="mt-3 text-xs text-muted-foreground">No transcript recorded.</p>
          )}
          {withRecordings && log.recording_sid && (
            <div className="mt-3 flex items-center gap-2">
              <Mic className="h-3.5 w-3.5 text-muted-foreground" />
              <RecordingPlayer logId={log.id} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
