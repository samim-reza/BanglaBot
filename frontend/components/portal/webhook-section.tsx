"use client";

/** Webhooks: signed JSON events into the business's own systems. */

import { FormEvent, useMemo, useState } from "react";
import {
  ArrowRight,
  CircleCheck,
  Eye,
  EyeOff,
  FileText,
  LoaderCircle,
  RefreshCw,
  Send,
  TriangleAlert,
  Webhook,
} from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDraft, useCopy, CopyButton, SectionCard, StatusPill, InlineError, InfoTip, CodeBlock } from "@/components/portal/kit";
import { cn } from "@/lib/utils";
import { t } from "@/lib/vertical";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, merchantApi, type Merchant } from "@/services/api";

// ---------------------------------------------------------------- webhooks

const NODE_SNIPPET = `// Node.js + Express
import crypto from "node:crypto";
import express from "express";

const app = express();
const SECRET = process.env.AGENT_WEBHOOK_SECRET;

// Use the RAW body: the signature is over the exact bytes we sent.
app.post("/agent-webhook", express.raw({ type: "application/json" }), (req, res) => {
  const expected = "sha256=" + crypto.createHmac("sha256", SECRET).update(req.body).digest("hex");
  const received = req.get("X-Agent-Signature") || "";
  const valid =
    received.length === expected.length &&
    crypto.timingSafeEqual(Buffer.from(received), Buffer.from(expected));
  if (!valid) return res.sendStatus(401);

  const event = JSON.parse(req.body.toString("utf8"));
  if (event.event === "call.completed") {
    // event.call.outcome, event.record?.status, …
  }
  res.sendStatus(200);
});`;

const PYTHON_SNIPPET = `# Python (Flask shown; any framework works)
import hashlib, hmac, json, os
from flask import Flask, abort, request

app = Flask(__name__)
SECRET = os.environ["AGENT_WEBHOOK_SECRET"].encode()

def is_valid(raw_body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")

@app.post("/agent-webhook")
def agent_webhook():
    raw = request.get_data()  # the raw bytes, before any JSON parsing
    if not is_valid(raw, request.headers.get("X-Agent-Signature", "")):
        abort(401)
    event = json.loads(raw)
    if event["event"] == "call.completed":
        pass  # event["call"]["outcome"], event["record"], …
    return "", 200`;

function exampleEvent(merchant: Merchant, vertical: string, recordKind: string): string {
  const payload = {
    event: "call.completed",
    sent_at: "2026-10-03T14:32:10.512845+00:00",
    account: { id: merchant.id, business_name: merchant.business_name, vertical },
    call: {
      id: "5f0c2a9e-…",
      direction: "inbound",
      flow: `${vertical}.inbound`,
      caller_number: "+14155550100",
      outcome: "booked",
      duration_secs: 94,
      language: merchant.language || "en",
      transcript: `Agent: Hello, thank you for calling ${merchant.business_name}.\nCustomer: …`,
    },
    record: {
      id: "9b1e7c44-…",
      kind: recordKind,
      status: "confirmed",
      customer_name: "Jane Doe",
      customer_phone: "+14155550100",
      address: null,
      summary: "…",
      amount: "0.00",
      currency: merchant.currency || "USD",
      scheduled_at: "2026-10-06T09:30:00+00:00",
      catalog_item_id: null,
      details: {},
      collected: {},
    },
  };
  return JSON.stringify(payload, null, 2);
}

type TestResult = { ok: boolean; status?: number; error?: string };

export function WebhookSection() {
  const { merchant, vertical, refresh } = useWorkspace();
  const toast = useAppToast();
  const { copied, copy } = useCopy();
  const source = useMemo(() => ({ url: merchant.webhook_url ?? "" }), [merchant]);
  const { draft, dirty, setDraft, reset, commit } = useDraft(source);
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);
  const [reveal, setReveal] = useState(false);
  const [lang, setLang] = useState<"node" | "python">("node");

  const urlOk = !draft.url.trim() || /^https?:\/\/\S+$/.test(draft.url.trim());
  const secret = merchant.webhook_secret;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!urlOk) {
      setError("The URL must start with http:// or https://");
      return;
    }
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const updated = await merchantApi.updateMe({ webhook_url: draft.url.trim() });
      commit({ url: updated.webhook_url ?? "" });
      await refresh();
      toast.success(updated.webhook_url ? "Webhook URL saved." : "Webhooks turned off.");
    } catch (err) {
      setError(formatApiError(err, "Could not save the webhook URL."));
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate the signing secret?\n\nEvents are signed with the new secret right away — update your receiver, or it will reject them.")) return;
    setRotating(true);
    try {
      await merchantApi.rotateWebhookSecret();
      await refresh();
      setReveal(true);
      toast.success("New signing secret created.");
    } catch (err) {
      toast.error(formatApiError(err, "Could not rotate the secret."));
    } finally {
      setRotating(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await merchantApi.testWebhook());
    } catch (err) {
      setResult({ ok: false, error: formatApiError(err, "Could not send the test event.") });
    } finally {
      setTesting(false);
    }
  };

  const canTest = Boolean(merchant.webhook_url) && !dirty;

  return (
    <SectionCard
      id="webhooks"
      icon={Webhook}
      title="Webhooks"
      badge={<StatusPill ok={Boolean(merchant.webhook_url)}>{merchant.webhook_url ? "Active" : "Not set"}</StatusPill>}
      description="Signed JSON for every finished call and chat."
      info="Send results to your CRM, a spreadsheet, Zapier or your own code: we POST a signed JSON event to your URL."
    >
      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="flex flex-col gap-1.5 text-sm">
          <div className="flex items-center gap-1.5">
            <label htmlFor="webhook-url" className="text-[13.5px] font-semibold text-muted-foreground">
              Endpoint URL
            </label>
            <InfoTip label="About delivery">We wait up to 6 seconds for a 2xx answer and don&apos;t retry.</InfoTip>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="webhook-url"
              type="url"
              inputMode="url"
              value={draft.url}
              maxLength={500}
              spellCheck={false}
              placeholder="https://example.com/agent-webhook"
              aria-invalid={!urlOk}
              aria-describedby="webhook-url-hint"
              className={cn("font-mono", !urlOk && "border-destructive")}
              onChange={(e) => setDraft(() => ({ url: e.target.value }))}
            />
            <div className="flex shrink-0 gap-2">
              <Button type="submit" size="sm" className="h-10 flex-1 sm:flex-none" disabled={!dirty || saving}>
                {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
                Save
              </Button>
              {dirty && (
                <Button type="button" variant="ghost" size="sm" className="h-10" disabled={saving} onClick={() => { reset(); setError(null); }}>
                  Discard
                </Button>
              )}
            </div>
          </div>
          <p id="webhook-url-hint" className="text-xs text-muted-foreground">
            Empty = off.
          </p>
        </div>
        <InlineError message={error} />
      </form>

      <div className="mt-5 grid gap-4 border-t border-border pt-5 md:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <h4 className="text-sm font-semibold">Signing secret</h4>
          {secret ? (
            <>
              <div className="flex min-w-0 items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-surface px-3 py-2 font-mono text-[12.5px]" aria-label="Signing secret">
                  {reveal ? secret : "•".repeat(Math.min(32, secret.length))}
                </code>
                <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0" aria-label={reveal ? "Hide secret" : "Reveal secret"} aria-pressed={reveal} onClick={() => setReveal((value) => !value)}>
                  {reveal ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <CopyButton id="secret" text={secret} copied={copied} onCopy={copy} label="Copy secret" />
                <Button type="button" variant="outline" size="sm" disabled={rotating} onClick={rotate}>
                  <RefreshCw className={cn("h-3.5 w-3.5", rotating && "animate-spin")} aria-hidden />
                  Rotate secret
                </Button>
              </div>
            </>
          ) : (
            <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">A secret is created when you save a URL.</p>
          )}
        </div>
        <div className="min-w-0 space-y-2">
          <h4 className="text-sm font-semibold">Test delivery</h4>
          <Button type="button" variant="outline" size="sm" disabled={!canTest || testing} onClick={sendTest}>
            {testing ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
            Send test event
          </Button>
          {!merchant.webhook_url && <p className="text-xs text-muted-foreground">Save a URL first.</p>}
          {merchant.webhook_url && dirty && <p className="text-xs text-muted-foreground">Save your URL change first.</p>}
          <div aria-live="polite">
            {result &&
              (result.ok ? (
                <p className="flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-[#065f46] dark:text-emerald-300">
                  <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  Delivered (HTTP {result.status ?? "2xx"}).
                </p>
              ) : (
                <p className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <span className="min-w-0 break-words">
                    {result.status ? `Not delivered (HTTP ${result.status}).` : `Not delivered — ${result.error || "endpoint unreachable"}.`}
                  </span>
                </p>
              ))}
          </div>
        </div>
      </div>

      <details className="group mt-5 rounded-md border border-border">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" aria-hidden />
            Docs &amp; examples
          </span>
          <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" aria-hidden />
        </summary>
        <div className="space-y-4 border-t border-border px-4 py-4 text-sm">
          <div className="space-y-2">
            <h5 className="font-semibold">Events</h5>
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <code className="rounded bg-secondary px-1 font-mono text-foreground">call.completed</code> — a call or chat ended.{" "}
                <code className="font-mono">record</code> is the {t(vertical.record_label, "record").toLowerCase()} it handled, or <code className="font-mono">null</code>.
              </li>
              <li>
                <code className="rounded bg-secondary px-1 font-mono text-foreground">test</code> — from &quot;Send test event&quot;.
              </li>
            </ul>
            <CodeBlock label="Example call.completed event" code={exampleEvent(merchant, vertical.key, vertical.record_kind)} />
          </div>
          <div className="space-y-2">
            <h5 className="font-semibold">Verify the signature</h5>
            <p className="text-muted-foreground">
              <code className="rounded bg-secondary px-1 font-mono text-foreground">X-Agent-Signature: sha256=&lt;hex&gt;</code> is the HMAC-SHA256 of the raw body,
              keyed with your secret. Compare in constant time; reject on mismatch.
            </p>
            <div role="tablist" aria-label="Code language" className="inline-flex rounded-md border border-input bg-card p-0.5">
              {(
                [
                  ["node", "Node.js"],
                  ["python", "Python"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={lang === value}
                  onClick={() => setLang(value)}
                  className={cn(
                    "h-8 rounded px-3 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    lang === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="relative">
              <CodeBlock label={lang === "node" ? "Node.js example" : "Python example"} code={lang === "node" ? NODE_SNIPPET : PYTHON_SNIPPET} />
              <div className="absolute right-2 top-2">
                <CopyButton id={`code-${lang}`} text={lang === "node" ? NODE_SNIPPET : PYTHON_SNIPPET} copied={copied} onCopy={copy} />
              </div>
            </div>
          </div>
        </div>
      </details>
    </SectionCard>
  );
}
