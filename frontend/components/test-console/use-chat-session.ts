"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { agentApi, formatApiError, isApiRequestError, type AgentState } from "@/services/api";

import { nextLineId, type Line, type SessionSetup } from "./types";

const ENDED_NOTE = "Chat ended.";

function agentLines(messages: string[]): Line[] {
  return messages.filter((text) => text && text.trim()).map((text) => ({ id: nextLineId(), role: "agent" as const, text: text.trim() }));
}

/**
 * A typed test conversation with the agent (same flow as a call). An open chat
 * is ended — and so saved to the call history — when the console unmounts.
 */
export function useChatSession() {
  const current = useRef<{ id: string | null; ended: boolean }>({ id: null, ended: false });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [setup, setSetup] = useState<SessionSetup | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<AgentState | null>(null);
  const [ended, setEnded] = useState(false);
  const [starting, setStarting] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(
    () => () => {
      const { id, ended: done } = current.current;
      if (id && !done) void agentApi.endChat(id).catch(() => undefined);
    },
    [],
  );

  const markEnded = useCallback((note = ENDED_NOTE) => {
    current.current.ended = true;
    setEnded(true);
    setLines((existing) => [...existing, { id: nextLineId(), role: "system", text: note }]);
  }, []);

  const start = useCallback(async (next: SessionSetup): Promise<string | null> => {
    const previous = current.current;
    if (previous.id && !previous.ended) void agentApi.endChat(previous.id).catch(() => undefined);
    current.current = { id: null, ended: false };
    setSessionId(null);
    setSetup(next);
    setLines([]);
    setState(null);
    setEnded(false);
    setError(null);
    setWaiting(false);
    setStarting(true);
    try {
      const response = await agentApi.startChat({
        direction: next.direction,
        record_id: next.direction === "outbound" ? next.recordId || null : null,
        caller_number: next.direction === "inbound" ? next.callerNumber.trim() : "",
      });
      current.current = { id: response.session_id, ended: Boolean(response.state?.ended) };
      setSessionId(response.session_id);
      setLines(agentLines(response.messages));
      setState(response.state);
      if (response.state?.ended) {
        setEnded(true);
      }
      return response.session_id;
    } catch (err) {
      setError(formatApiError(err, "Could not start the chat."));
      return null;
    } finally {
      setStarting(false);
    }
  }, []);

  const send = useCallback(
    async (text: string, fallbackSetup?: SessionSetup) => {
      const message = text.trim().slice(0, 600);
      if (!message) return false;
      let id = current.current.ended ? null : current.current.id;
      if (!id) {
        if (!fallbackSetup) return false;
        id = await start(fallbackSetup);
        if (!id || current.current.ended) return false;
      }
      setLines((existing) => [...existing, { id: nextLineId(), role: "caller", text: message }]);
      setWaiting(true);
      setError(null);
      try {
        const reply = await agentApi.say(id, message);
        if (current.current.id !== id) return true;
        setLines((existing) => [...existing, ...agentLines(reply.messages)]);
        setState(reply.state);
        if (reply.ended) markEnded();
        return true;
      } catch (err) {
        if (current.current.id !== id) return false;
        if (isApiRequestError(err) && err.status === 404) {
          markEnded("This chat has ended — start a new one.");
        } else {
          setError(formatApiError(err, "Your message could not be sent."));
        }
        return false;
      } finally {
        setWaiting(false);
      }
    },
    [markEnded, start],
  );

  const end = useCallback(async () => {
    const id = current.current.id;
    if (!id || current.current.ended) return;
    setEnding(true);
    try {
      const reply = await agentApi.endChat(id);
      if (current.current.id === id) setState(reply.state);
    } catch {
      // Already gone on the server (expired) — it is over either way.
    } finally {
      if (current.current.id === id) markEnded();
      setEnding(false);
    }
  }, [markEnded]);

  const active = Boolean(sessionId) && !ended;
  return { sessionId, setup, lines, state, ended, active, starting, waiting, ending, error, start, send, end };
}

export type ChatSession = ReturnType<typeof useChatSession>;
