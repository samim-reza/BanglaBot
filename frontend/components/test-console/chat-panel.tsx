"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { LoaderCircle, MessageSquarePlus, Send, Square } from "lucide-react";

import { ApiError } from "@/components/api-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { Conversation } from "./conversation";
import type { ChatSession } from "./use-chat-session";

/** Typed conversation with the agent: start, send, end, new chat. */
export function ChatPanel({ chat, onStart, startDisabled, startHint }: { chat: ChatSession; onStart: () => void; startDisabled?: boolean; startHint?: string }) {
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { sessionId, lines, active, ended, starting, waiting, ending, error } = chat;
  const canType = active && !waiting && !ending;

  // Back to the input once the agent has answered.
  useEffect(() => {
    if (active && !waiting && !starting) input.current?.focus({ preventScroll: true });
  }, [active, waiting, starting]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const message = text.trim();
    if (!message || !canType) return;
    setText("");
    const sent = await chat.send(message);
    if (!sent) setText((current) => current || message);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium" aria-live="polite">
          <span
            aria-hidden
            className={
              active ? "inline-block h-2 w-2 rounded-full bg-emerald-500" : starting ? "inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" : "inline-block h-2 w-2 rounded-full bg-muted-foreground/50"
            }
          />
          {starting ? "Starting chat…" : active ? "Chat open" : ended ? "Chat ended" : "No chat yet"}
        </p>
        <div className="flex gap-2">
          {active && (
            <Button type="button" variant="outline" size="sm" onClick={() => void chat.end()} disabled={ending || waiting}>
              {ending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Square className="h-3.5 w-3.5" aria-hidden />}
              End chat
            </Button>
          )}
          {sessionId && (
            <Button type="button" variant={ended ? "default" : "ghost"} size="sm" onClick={onStart} disabled={starting || startDisabled}>
              <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />
              New chat
            </Button>
          )}
        </div>
      </div>

      <Conversation
        label="Chat transcript"
        lines={lines}
        typing={waiting || starting}
        className="h-[26rem]"
        empty={
          <div className="space-y-3">
            <p>Chat as a customer would. Bookings are real.</p>
            <Button type="button" onClick={onStart} disabled={starting || startDisabled}>
              {starting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <MessageSquarePlus className="h-4 w-4" aria-hidden />}
              Start chat
            </Button>
            {startHint && <p className="text-xs">{startHint}</p>}
          </div>
        }
      />

      {error && <ApiError message={error} />}

      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="test-chat-input" className="sr-only">
          Your message
        </label>
        <Input
          id="test-chat-input"
          ref={input}
          value={text}
          maxLength={600}
          autoComplete="off"
          placeholder={ended ? "This chat has ended — start a new one" : active ? "Type a message…" : "Start a chat first"}
          disabled={!active || ending}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" disabled={!canType || !text.trim()} aria-label="Send message" className="shrink-0">
          {waiting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
          <span className="hidden sm:inline">Send</span>
        </Button>
      </form>
    </div>
  );
}
