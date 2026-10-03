"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { Lightbulb, MessageSquare, Mic, PhoneIncoming, PhoneOutgoing, RefreshCw, Send, type LucideIcon } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { statusLabel, t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, ordersApi, type Direction, type Order } from "@/services/api";

import { AgentStatePanel } from "./agent-state-panel";
import { ChatPanel } from "./chat-panel";
import { samplesFor, type ConsoleMode, type SessionSetup } from "./types";
import { useChatSession } from "./use-chat-session";
import { useVoiceCall, voiceActive } from "./use-voice-call";
import { VoicePanel } from "./voice-panel";

const MODES: { id: ConsoleMode; label: string; icon: LucideIcon }[] = [
  { id: "voice", label: "Voice call", icon: Mic },
  { id: "chat", label: "Chat", icon: MessageSquare },
];

function shorten(text: string, max = 60): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

/**
 * "Test your agent": a browser voice call or a typed chat with the account's
 * own agent, inbound (a customer contacts you) or outbound (you call about one
 * of your records), with the agent's live state alongside.
 */
export function TestConsole() {
  const { vertical, entitlements } = useWorkspace();
  // A chat-only plan has no phone agent: test by chat, as a customer writing in.
  const hasVoice = entitlements.channels.includes("voice");
  const canInbound = vertical.directions.includes("inbound");
  const canOutbound = vertical.directions.includes("outbound") && (hasVoice || !canInbound);
  const modes = hasVoice ? MODES : MODES.filter((item) => item.id === "chat");
  const singular = t(vertical.record_label, "record").toLowerCase();
  const plural = t(vertical.record_label_plural, "records").toLowerCase();

  const [mode, setMode] = useState<ConsoleMode>(hasVoice ? "voice" : "chat");
  const [direction, setDirection] = useState<Direction>(canInbound || !canOutbound ? "inbound" : "outbound");
  const [recordId, setRecordId] = useState("");
  const [callerNumber, setCallerNumber] = useState("");
  const [records, setRecords] = useState<Order[] | null>(null);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const tabRefs = useRef<Record<ConsoleMode, HTMLButtonElement | null>>({ voice: null, chat: null });

  const voice = useVoiceCall();
  const chat = useChatSession();
  const voiceBusy = voiceActive(voice.phase);
  const chatBusy = chat.active || chat.starting;
  const busy = mode === "voice" ? voiceBusy : chatBusy;

  const loadRecords = useCallback(async () => {
    setRecordsLoading(true);
    setRecordsError(null);
    try {
      const page = await ordersApi.list({ page_size: 50 });
      setRecords(page.items);
      setRecordId((current) => (current && page.items.some((item) => item.id === current) ? current : page.items[0]?.id ?? ""));
    } catch (err) {
      setRecordsError(formatApiError(err, `Could not load your ${plural}.`));
    } finally {
      setRecordsLoading(false);
    }
  }, [plural]);

  useEffect(() => {
    if (direction === "outbound" && records === null && !recordsLoading && !recordsError) void loadRecords();
  }, [direction, records, recordsLoading, recordsError, loadRecords]);

  const selected = records?.find((item) => item.id === recordId);
  const setup: SessionSetup = {
    direction,
    recordId: direction === "outbound" ? recordId : "",
    recordName: direction === "outbound" && selected ? selected.customer_name : "",
    callerNumber: direction === "inbound" ? callerNumber : "",
  };
  const needsRecord = direction === "outbound" && !recordId;
  const startHint = needsRecord ? `Choose a ${singular} to call about first.` : undefined;

  const view =
    mode === "voice" ? { state: voice.state, setup: voice.setup, running: voiceBusy } : { state: chat.state, setup: chat.setup, running: chat.active };
  const sampleDirection = (mode === "chat" && chat.active ? chat.setup?.direction : mode === "voice" && voiceBusy ? voice.setup?.direction : null) ?? direction;
  const samples = samplesFor(vertical.key, sampleDirection);
  const sampleDisabled = chat.waiting || chat.starting || chat.ending || (!chat.active && needsRecord);

  const switchMode = (next: ConsoleMode) => {
    if (next === mode || (next === "chat" && voiceBusy) || !modes.some((item) => item.id === next)) return;
    setMode(next);
  };

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const next: ConsoleMode = mode === "voice" ? "chat" : "voice";
    if ((next === "chat" && voiceBusy) || !modes.some((item) => item.id === next)) return;
    setMode(next);
    tabRefs.current[next]?.focus();
  };

  const directionOptions: { value: Direction; label: string; icon: LucideIcon }[] = [
    ...(canInbound ? [{ value: "inbound" as const, label: "Customer contacts you", icon: PhoneIncoming }] : []),
    ...(canOutbound ? [{ value: "outbound" as const, label: t(vertical.outbound_label, "You call a customer"), icon: PhoneOutgoing }] : []),
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <Card className="min-w-0">
        <CardContent className="space-y-5 p-4 sm:p-5">
          <div role="tablist" aria-label="How to test" className={cn("grid gap-1 rounded-lg bg-secondary p-1", modes.length > 1 ? "grid-cols-2" : "grid-cols-1")}>
            {modes.map((item) => {
              const active = mode === item.id;
              const locked = item.id === "chat" && voiceBusy;
              return (
                <button
                  key={item.id}
                  ref={(node) => {
                    tabRefs.current[item.id] = node;
                  }}
                  type="button"
                  role="tab"
                  id={`test-tab-${item.id}`}
                  aria-controls={`test-panel-${item.id}`}
                  aria-selected={active}
                  tabIndex={active ? 0 : -1}
                  disabled={locked}
                  title={locked ? "Hang up first" : undefined}
                  onClick={() => switchMode(item.id)}
                  onKeyDown={onTabKey}
                  className={cn(
                    "flex h-10 min-w-0 items-center justify-center gap-2 rounded-md px-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                    active ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </div>

          <fieldset disabled={busy} className="space-y-4">
            <legend className="sr-only">Test setup</legend>
            {directionOptions.length > 1 ? (
              <div role="radiogroup" aria-label="Who starts the conversation" className="grid gap-2 sm:grid-cols-2">
                {directionOptions.map((option) => {
                  const checked = direction === option.value;
                  return (
                    <label
                      key={option.value}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                        checked ? "border-primary bg-accent/60" : "border-border hover:bg-secondary",
                        busy && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <input
                        type="radio"
                        name="test-direction"
                        value={option.value}
                        checked={checked}
                        onChange={() => setDirection(option.value)}
                        className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                      />
                      <span className="flex min-w-0 items-center gap-1.5 font-semibold">
                        <option.icon className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                        {option.label}
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : (
              directionOptions[0] && (
                <p className="flex items-center gap-2 text-sm font-medium">
                  {(() => {
                    const Icon = directionOptions[0].icon;
                    return <Icon className="h-4 w-4 text-primary" aria-hidden />;
                  })()}
                  {directionOptions[0].label}
                </p>
              )
            )}

            {direction === "outbound" ? (
              <div className="flex flex-col gap-1.5 text-sm">
                <label htmlFor="test-record" className="text-[13.5px] font-semibold text-muted-foreground">
                  {t(vertical.record_label, "Record")} to call about
                </label>
                {recordsError ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    <span className="min-w-0 flex-1">{recordsError}</span>
                    <Button type="button" variant="outline" size="sm" onClick={() => void loadRecords()}>
                      Try again
                    </Button>
                  </div>
                ) : records && records.length === 0 ? (
                  <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
                    No {plural} yet.{" "}
                    <Link href="/orders/new" className="font-medium text-primary underline-offset-2 hover:underline">
                      Create one
                    </Link>
                  </p>
                ) : (
                  <div className="flex gap-2">
                    <Select
                      id="test-record"
                      value={recordId}
                      disabled={!records || recordsLoading}
                      aria-describedby="test-record-hint"
                      className="min-w-0"
                      onChange={(e) => setRecordId(e.target.value)}
                    >
                      {!records && <option value="">Loading…</option>}
                      {records?.map((item) => (
                        <option key={item.id} value={item.id}>
                          {shorten(`${item.customer_name}${item.summary ? ` — ${item.summary}` : ""} (${statusLabel(vertical, item.status)})`, 90)}
                        </option>
                      ))}
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="shrink-0"
                      aria-label={`Reload ${plural}`}
                      disabled={recordsLoading}
                      onClick={() => void loadRecords()}
                    >
                      <RefreshCw className={cn("h-4 w-4", recordsLoading && "animate-spin")} aria-hidden />
                    </Button>
                  </div>
                )}
                <p id="test-record-hint" className="text-xs text-muted-foreground">
                  You play the customer; nothing is dialed.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5 text-sm">
                <span className="flex items-center gap-1.5">
                  <label htmlFor="test-caller" className="text-[13.5px] font-semibold text-muted-foreground">
                    Caller number <span className="font-normal">(optional)</span>
                  </label>
                  <InfoTip label="About the caller number">
                    Use a customer&apos;s number to test cancelling or rescheduling their {singular} — the agent finds it by the caller&apos;s number. Empty = a new
                    caller.
                  </InfoTip>
                </span>
                <Input
                  id="test-caller"
                  type="tel"
                  inputMode="tel"
                  maxLength={32}
                  value={callerNumber}
                  placeholder="+1 415 555 0100"
                  onChange={(e) => setCallerNumber(e.target.value)}
                />
              </div>
            )}
            {busy && (
              <p className="text-xs text-muted-foreground">{mode === "voice" ? "Hang up" : "End the chat"} to change these.</p>
            )}
          </fieldset>

          <div role="tabpanel" id="test-panel-voice" aria-labelledby="test-tab-voice" hidden={mode !== "voice"}>
            <VoicePanel voice={voice} onStart={() => void voice.start(setup)} startDisabled={needsRecord} startHint={startHint} />
          </div>
          <div role="tabpanel" id="test-panel-chat" aria-labelledby="test-tab-chat" hidden={mode !== "chat"}>
            <ChatPanel chat={chat} onStart={() => void chat.start(setup)} startDisabled={needsRecord} startHint={startHint} />
          </div>
        </CardContent>
      </Card>

      <aside className="min-w-0 space-y-6" aria-label="Agent details">
        <AgentStatePanel state={view.state} setup={view.setup} vertical={vertical} running={view.running} />

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-primary" aria-hidden />
              Things to try
            </CardTitle>
            <CardDescription>{mode === "chat" ? "Click one to send it." : "Say one of these on the call."}</CardDescription>
          </CardHeader>
          <CardContent>
            {samples.length ? (
              <ul className="space-y-2">
                {samples.map((sample) => (
                  <li key={sample}>
                    {mode === "chat" ? (
                      <button
                        type="button"
                        disabled={sampleDisabled}
                        onClick={() => void chat.send(sample, setup)}
                        className="group flex w-full items-start gap-2 rounded-md border border-border bg-card px-3 py-2 text-left text-sm transition hover:border-tint-strong hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <span className="min-w-0 flex-1">&ldquo;{sample}&rdquo;</span>
                        <Send className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground group-hover:text-primary" aria-hidden />
                        <span className="sr-only">Send</span>
                      </button>
                    ) : (
                      <p className="rounded-md bg-surface px-3 py-2 text-sm">&ldquo;{sample}&rdquo;</p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Talk to it the way your customers would.</p>
            )}
            <p className="mt-4 text-xs text-muted-foreground">
              Answers come from your{" "}
              <Link href="/settings?tab=agent#knowledge" className="font-medium text-primary underline-offset-2 hover:underline">
                knowledge base
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
