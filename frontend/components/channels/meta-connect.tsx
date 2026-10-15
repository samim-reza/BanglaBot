"use client";

/** Connect a Meta account by ID + token (Instagram DMs, WhatsApp Cloud API), or disconnect it. */

import { FormEvent, useState } from "react";
import { LoaderCircle, Unplug, type LucideIcon } from "lucide-react";

import { useAppToast } from "@/components/app-toast";
import { InfoTip, InlineError, SectionCard, SetupNote, StatusPill } from "@/components/portal/kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useWorkspace } from "@/lib/workspace";
import { formatApiError, isApiRequestError, type ChannelsView } from "@/services/api";

const NUMERIC_ID = /^\d{3,40}$/;

export type MetaConnectProps = {
  id: string;
  icon: LucideIcon;
  title: string;
  connected: boolean;
  /** What is connected, e.g. "@shop" or "+1 415 …". */
  summary: string;
  idLabel: string;
  tokenLabel: string;
  help: string;
  platformReady: boolean;
  connect: (id: string, token: string) => Promise<ChannelsView>;
  disconnect: () => Promise<ChannelsView>;
  onView: (next: ChannelsView) => void;
};

export function MetaConnectSection({ id, icon, title, connected, summary, idLabel, tokenLabel, help, platformReady, connect, disconnect, onView }: MetaConnectProps) {
  const { refresh } = useWorkspace();
  const toast = useAppToast();
  const [accountId, setAccountId] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!NUMERIC_ID.test(accountId.trim())) return setError(`The ${idLabel.toLowerCase()} is a number, like 1234567890.`);
    if (token.trim().length < 20) return setError(`Paste the full ${tokenLabel.toLowerCase()}.`);
    setBusy(true);
    setError(null);
    try {
      onView(await connect(accountId.trim(), token.trim()));
      setAccountId("");
      setToken("");
      await refresh();
      toast.success(`${title} connected.`);
    } catch (err) {
      setError(isApiRequestError(err) && err.status === 409 ? "That account is already connected to another business." : formatApiError(err, "Could not connect."));
    } finally {
      setBusy(false);
    }
  };

  const unplug = async () => {
    if (!window.confirm(`Disconnect ${title}?\n\nThe agent stops answering its messages.`)) return;
    setBusy(true);
    try {
      onView(await disconnect());
      await refresh();
      toast.success(`${title} disconnected.`);
    } catch (err) {
      toast.error(formatApiError(err, "Could not disconnect."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard id={id} icon={icon} title={title} badge={<StatusPill ok={connected}>{connected ? "Connected" : "Not connected"}</StatusPill>}>
      <div className="space-y-3 text-sm">
        {connected ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="min-w-0 font-semibold">{summary || title}</p>
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void unplug()}>
              {busy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Unplug className="h-3.5 w-3.5" aria-hidden />}
              Disconnect
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="space-y-3">
            <p className="flex items-center gap-1.5 font-medium">
              Connect
              <InfoTip label={`How to connect ${title}`}>{help}</InfoTip>
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor={`${id}-account`} className="text-[13.5px] font-semibold text-muted-foreground">
                  {idLabel}
                </label>
                <Input id={`${id}-account`} value={accountId} inputMode="numeric" autoComplete="off" spellCheck={false} maxLength={40} placeholder="1234567890" className="font-mono" onChange={(e) => setAccountId(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor={`${id}-token`} className="text-[13.5px] font-semibold text-muted-foreground">
                  {tokenLabel}
                </label>
                <Input id={`${id}-token`} type="password" value={token} autoComplete="off" spellCheck={false} maxLength={1000} className="font-mono" onChange={(e) => setToken(e.target.value)} />
              </div>
            </div>
            <InlineError message={error} />
            <Button type="submit" size="sm" disabled={busy || !accountId.trim() || !token.trim()}>
              {busy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Connect
            </Button>
          </form>
        )}
        {!platformReady && <SetupNote>{title} isn&apos;t set up on this server yet.</SetupNote>}
      </div>
    </SectionCard>
  );
}
