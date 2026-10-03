"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlarmClock, LoaderCircle, PhoneForwarded, Square, X } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatInZone, fromZonedInput, statusLabel, t, toZonedInput } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { bulkRunActive, formatApiError, ordersApi, type BulkCallRun, type BulkCallStatus } from "@/services/api";

const POLL_MS = 3000;

function runSummary(run: BulkCallRun): string {
  const parts = [`${run.started} started`];
  if (run.failed) parts.push(`${run.failed} failed`);
  if (run.skipped) parts.push(`${run.skipped} skipped`);
  return parts.join(" · ");
}

/**
 * "Call all" + "Auto call" for the records page: dials every record that still
 * needs a call (pending / no answer) a few at a time, and lets the account
 * schedule that run for a chosen time (in the account's time zone).
 */
export function BulkCallControls({ onOrdersChanged }: { onOrdersChanged: () => void }) {
  const toast = useAppToast();
  const { vertical, merchant } = useWorkspace();
  const timezone = merchant.timezone;
  const singular = t(vertical.record_label, "record").toLowerCase();
  const plural = t(vertical.record_label_plural, "records").toLowerCase();
  const callName = t(vertical.outbound_label, "call").toLowerCase();
  const pendingLabel = statusLabel(vertical, "pending").toLowerCase();
  const noAnswerLabel = statusLabel(vertical, "no_answer").toLowerCase();
  const count = (n: number) => `${n} ${n === 1 ? singular : plural}`;

  const [status, setStatus] = useState<BulkCallStatus | null>(null);
  const [busy, setBusy] = useState<"start" | "cancel" | "schedule" | "clear" | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [at, setAt] = useState("");
  const [repeatDaily, setRepeatDaily] = useState(false);
  const [dismissedRunId, setDismissedRunId] = useState<string | null>(null);

  // The parent's reload changes identity with its filters; call the latest one without re-running effects.
  const changedRef = useRef(onOrdersChanged);
  useEffect(() => {
    changedRef.current = onOrdersChanged;
  }, [onOrdersChanged]);
  const notifyChanged = useCallback(() => changedRef.current(), []);

  const refresh = useCallback(async () => {
    try {
      setStatus(await ordersApi.callAllStatus());
    } catch {
      // The records list shows its own error; this toolbar just stays quiet.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // While a run is dialing, keep the progress and the records table fresh.
  const active = bulkRunActive(status?.run);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void refresh();
      notifyChanged();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [active, refresh, notifyChanged]);

  // One last list refresh when a run ends so the final outcomes show up.
  const runState = status?.run?.state;
  useEffect(() => {
    if (runState === "done" || runState === "cancelled" || runState === "failed") notifyChanged();
  }, [runState, notifyChanged]);

  const openSchedule = () => {
    setAt(toZonedInput(status?.schedule.at, timezone));
    setRepeatDaily(Boolean(status?.schedule.repeat_daily));
    setScheduleOpen(true);
  };

  const startAll = async () => {
    const eligibleNow = status?.eligible ?? 0;
    if (!window.confirm(`Place a ${callName} for ${count(eligibleNow)} now? Up to ${status?.max_concurrent ?? 1} calls run at a time.`)) return;
    setBusy("start");
    try {
      const next = await ordersApi.callAll();
      setStatus(next);
      setDismissedRunId(null);
      toast.success(`Calling ${count(next.run?.total ?? eligibleNow)}…`);
      notifyChanged();
    } catch (err) {
      toast.error(formatApiError(err, "Could not start calling."));
      void refresh();
    } finally {
      setBusy(null);
    }
  };

  const stopAll = async () => {
    setBusy("cancel");
    try {
      setStatus(await ordersApi.cancelCallAll());
      toast.success("Stopped. Calls already ringing will finish on their own.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not stop the run."));
    } finally {
      setBusy(null);
    }
  };

  const saveSchedule = async () => {
    if (!at) {
      toast.error("Pick a date and time first.");
      return;
    }
    const iso = fromZonedInput(at, timezone);
    if (!iso || Number.isNaN(new Date(iso).getTime())) {
      toast.error("That date and time is not valid.");
      return;
    }
    setBusy("schedule");
    try {
      const next = await ordersApi.setAutoCall(iso, repeatDaily);
      setStatus(next);
      setScheduleOpen(false);
      toast.success(`Auto call set for ${formatInZone(next.schedule.at, timezone)}${next.schedule.repeat_daily ? ", every day" : ""}.`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not save the schedule."));
    } finally {
      setBusy(null);
    }
  };

  const clearSchedule = async () => {
    setBusy("clear");
    try {
      setStatus(await ordersApi.clearAutoCall());
      setScheduleOpen(false);
      toast.success("Auto call turned off.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not clear the schedule."));
    } finally {
      setBusy(null);
    }
  };

  const run = status?.run ?? null;
  const showRun = run && (active || run.id !== dismissedRunId);
  const eligible = status?.eligible ?? 0;
  const scheduledAt = status?.schedule.at ?? null;

  return (
    <section aria-label="Bulk calling" className="space-y-3 rounded-lg border bg-card p-3 sm:p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-sm">
          <p className="flex items-center gap-1.5 font-medium">
            Bulk {callName}s
            <InfoTip label="About bulk calls">
              Dials every {pendingLabel} or {noAnswerLabel} {singular} with fewer than {status?.max_attempts ?? 3} attempts, up to {status?.max_concurrent ?? 1} at a
              time. Auto call does the same at a set time.
            </InfoTip>
          </p>
          <p className="text-xs text-muted-foreground">
            {status ? `${count(eligible)} to call` : "Loading…"}
            {scheduledAt && (
              <>
                {" "}
                <span className="font-medium text-accent-foreground">
                  Auto call: {formatInZone(scheduledAt, timezone)}
                  {status?.schedule.repeat_daily ? " (daily)" : ""}
                </span>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {active ? (
            <Button variant="outline" onClick={() => void stopAll()} disabled={busy === "cancel"}>
              <Square className="h-4 w-4" aria-hidden="true" />
              {busy === "cancel" ? "Stopping…" : "Stop"}
            </Button>
          ) : (
            <Button
              onClick={() => void startAll()}
              disabled={!status || eligible === 0 || busy === "start"}
              title={eligible === 0 ? `No ${plural} need a call right now` : `Call every ${pendingLabel} or ${noAnswerLabel} ${singular}`}
            >
              <PhoneForwarded className="h-4 w-4" aria-hidden="true" />
              {busy === "start" ? "Starting…" : `Call all${status ? ` (${eligible})` : ""}`}
            </Button>
          )}
          <Button variant="outline" onClick={scheduleOpen ? () => setScheduleOpen(false) : openSchedule} aria-expanded={scheduleOpen}>
            <AlarmClock className="h-4 w-4" aria-hidden="true" />
            {scheduledAt ? "Edit auto call" : "Auto call"}
          </Button>
        </div>
      </div>

      {scheduleOpen && (
        <div className="flex flex-col gap-3 rounded-md border bg-surface p-3 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1.5 text-sm">
            <span className="text-[13.5px] font-semibold text-muted-foreground">Auto call at</span>
            <Input type="datetime-local" value={at} onChange={(event) => setAt(event.target.value)} />
            <span className="text-xs text-muted-foreground">{timezone}</span>
          </label>
          <label className="inline-flex items-center gap-2 text-sm sm:pb-6">
            <input type="checkbox" className="h-4 w-4 accent-primary" checked={repeatDaily} onChange={(event) => setRepeatDaily(event.target.checked)} />
            Repeat daily
          </label>
          <div className="flex gap-2 sm:pb-6">
            <Button onClick={() => void saveSchedule()} disabled={busy === "schedule"}>
              {busy === "schedule" ? "Saving…" : "Save"}
            </Button>
            {scheduledAt && (
              <Button variant="outline" onClick={() => void clearSchedule()} disabled={busy === "clear"}>
                {busy === "clear" ? "Clearing…" : "Turn off"}
              </Button>
            )}
          </div>
        </div>
      )}

      {showRun && run && (
        <div className="flex items-start gap-3 rounded-md border bg-surface px-3 py-2 text-sm" role="status" aria-live="polite">
          {active ? <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" aria-hidden="true" /> : null}
          <div className="min-w-0 flex-1">
            {active ? (
              <>
                <span className="font-medium">
                  Calling {plural}
                  {run.source === "scheduled" ? " (auto call)" : ""}…
                </span>{" "}
                <span className="text-muted-foreground">
                  {run.started + run.failed + run.skipped} of {run.total} dialed · {runSummary(run)}
                </span>
              </>
            ) : (
              <>
                <span className="font-medium">
                  {run.state === "done" ? "Call all finished" : run.state === "cancelled" ? "Call all stopped" : "Call all failed"}
                  {run.source === "scheduled" ? " (auto call)" : ""}
                </span>{" "}
                <span className="text-muted-foreground">
                  {runSummary(run)} of {run.total}
                  {run.finished_at ? ` · ${formatInZone(run.finished_at, timezone)}` : ""}
                </span>
                {run.error && <div className="mt-1 text-destructive">{run.error}</div>}
              </>
            )}
          </div>
          {!active && (
            <Button variant="ghost" size="sm" onClick={() => setDismissedRunId(run.id)} aria-label="Dismiss">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
