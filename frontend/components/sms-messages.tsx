"use client";

/** The texts sent to customers (confirmations, reminders, manual sends) — Add-ons and record pages. */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { LoaderCircle, MessageSquareText, RefreshCw, Send } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { formatInZone } from "@/lib/vertical";
import { formatApiError, integrationsApi, type SmsMessage } from "@/services/api";

const STATUS: Record<string, { label: string; tone: string }> = {
  queued: { label: "Sending", tone: "bg-secondary text-muted-foreground" },
  sent: { label: "Sent", tone: "bg-accent text-accent-foreground" },
  delivered: { label: "Delivered", tone: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300" },
  read: { label: "Read", tone: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300" },
  failed: { label: "Failed", tone: "bg-destructive/10 text-destructive" },
  undelivered: { label: "Not delivered", tone: "bg-destructive/10 text-destructive" },
  skipped: { label: "Not sent", tone: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" },
};

export const SMS_KIND_LABEL: Record<string, string> = {
  confirmation: "Confirmation",
  change: "Change",
  cancellation: "Cancellation",
  reminder: "Reminder",
  lead: "Follow-up",
  manual: "Sent by you",
  test: "Test",
};

export function SmsStatus({ status }: { status: string }) {
  const meta = STATUS[status] ?? { label: status, tone: "bg-secondary text-muted-foreground" };
  return <span className={cn("inline-flex shrink-0 rounded-full px-2 py-0.5 text-[12px] font-semibold", meta.tone)}>{meta.label}</span>;
}

export function SmsMessageList({
  messages,
  timezone,
  showNumber = true,
  empty = "No texts yet.",
}: {
  messages: SmsMessage[];
  timezone?: string;
  showNumber?: boolean;
  empty?: string;
}) {
  if (!messages.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {messages.map((message) => (
        <li key={message.id} className="grid gap-1.5 p-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <SmsStatus status={message.status} />
            <span className="font-medium">{SMS_KIND_LABEL[message.kind] ?? message.kind}</span>
            {showNumber && <span className="tabular-nums text-muted-foreground">{message.to_number}</span>}
            <span className="ml-auto text-xs tabular-nums text-muted-foreground">{formatInZone(message.created_at, timezone)}</span>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{message.body}</p>
          {message.error && <p className="text-xs text-destructive">{message.error}</p>}
          {message.segments > 1 && <p className="text-xs text-muted-foreground">{message.segments} SMS segments</p>}
        </li>
      ))}
    </ul>
  );
}

/** Rough SMS segment count: 160 characters (GSM-7) or 70 (Unicode) per text, less for long ones. */
function segmentCount(text: string): number {
  if (!text) return 0;
  // eslint-disable-next-line no-control-regex
  const unicode = /[^\x00-\x7f£¥èéùìòÇØøÅåΔΦΓΛΩΠΨΣΘΞÆæßÉ¡¿ÄÖÑÜ§äöñüà€]/.test(text);
  const single = unicode ? 70 : 160;
  const multi = unicode ? 67 : 153;
  return text.length <= single ? 1 : Math.ceil(text.length / multi);
}

/** The texts about one record, and a composer to send another. */
export function RecordSmsCard({
  orderId,
  phone,
  timezone,
  recordLabel,
  refreshKey,
}: {
  orderId: string;
  phone: string;
  timezone?: string;
  recordLabel: string;
  /** Reload when this changes (e.g. the record's status after a call). */
  refreshKey?: string;
}) {
  const toast = useAppToast();
  const [messages, setMessages] = useState<SmsMessage[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [composing, setComposing] = useState(false);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMessages((await integrationsApi.messages({ order_id: orderId, page_size: 20 })).items);
    } catch {
      setMessages((current) => current ?? []);
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    try {
      const message = await integrationsApi.sendRecordSms(orderId, body.trim());
      if (message.status === "failed" || message.status === "skipped") toast.error(message.error || "The text wasn't sent.");
      else {
        toast.success(`Text sent to ${message.to_number}.`);
        setBody("");
        setComposing(false);
      }
      await load();
    } catch (err) {
      toast.error(formatApiError(err, "Could not send the text."));
    } finally {
      setSending(false);
    }
  };

  const segments = segmentCount(body.trim());

  return (
    <Card className="h-fit">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div className="min-w-0 space-y-1.5">
          <CardTitle>Texts</CardTitle>
          <CardDescription>{phone ? <>SMS to <span className="tabular-nums">{phone}</span> about this {recordLabel}.</> : `This ${recordLabel} has no phone number to text.`}</CardDescription>
        </div>
        <div className="flex gap-1">
          <Button type="button" variant="ghost" size="sm" onClick={() => void load()} disabled={loading} aria-label="Refresh texts">
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} aria-hidden />
          </Button>
          {!composing && (
            <Button type="button" variant="outline" size="sm" disabled={!phone} onClick={() => setComposing(true)}>
              <MessageSquareText className="h-3.5 w-3.5" aria-hidden />
              Send SMS
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {composing && (
          <form onSubmit={send} className="grid gap-2 rounded-md border border-border bg-surface p-3">
            <label htmlFor={`sms-body-${orderId}`} className="text-[13.5px] font-semibold text-muted-foreground">
              Message
            </label>
            <Textarea
              id={`sms-body-${orderId}`}
              rows={3}
              maxLength={640}
              value={body}
              autoFocus
              placeholder={`Leave empty to send the standard text with this ${recordLabel}'s details.`}
              onChange={(e) => setBody(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs tabular-nums text-muted-foreground">
                {body.trim() ? `${body.trim().length} characters · ${segments} ${segments === 1 ? "text" : "texts"}` : "Standard confirmation"}
              </span>
              <span className="flex-1" />
              <Button type="button" variant="ghost" size="sm" onClick={() => setComposing(false)} disabled={sending}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={sending}>
                {sending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
                Send
              </Button>
            </div>
          </form>
        )}
        {messages === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <SmsMessageList messages={messages} timezone={timezone} showNumber={false} empty={`No texts about this ${recordLabel} yet.`} />
        )}
      </CardContent>
    </Card>
  );
}
