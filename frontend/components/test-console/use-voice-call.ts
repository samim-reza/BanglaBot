"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { WebCall, mediaSocketUrl } from "@/lib/web-call";
import { agentApi, formatApiError, type AgentState, type TestCallTicket } from "@/services/api";

import { nextLineId, type Line, type SessionSetup } from "./types";

export type VoicePhase = "idle" | "requesting" | "connecting" | "live" | "ended" | "error";

export type VoiceError = {
  kind: "insecure" | "mic" | "api" | "server" | "dropped" | "audio";
  message: string;
};

export function voiceActive(phase: VoicePhase): boolean {
  return phase === "requesting" || phase === "connecting" || phase === "live";
}

/**
 * A browser test call: asks the API for a ticket, then runs `WebCall` (the
 * Twilio-compatible media socket) and collects transcript, agent state and the
 * microphone level. The call is hung up when the component using it unmounts.
 *
 * `WebCall.start()` does not notice a `stop()` that lands while it is still
 * awaiting the microphone / audio worklet, so a hang-up (or unmount) during
 * that window is deferred until `start()` has returned.
 */
export function useVoiceCall() {
  const callRef = useRef<WebCall | null>(null);
  const mounted = useRef(true);
  /** Between "Start call" and WebCall.start() returning. */
  const pending = useRef(false);
  /** Hang-up requested while pending. */
  const abort = useRef(false);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<VoiceError | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<AgentState | null>(null);
  const [setup, setSetup] = useState<SessionSetup | null>(null);
  const [level, setLevel] = useState(0);
  const [muted, setMuted] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [endedAt, setEndedAt] = useState<number | null>(null);
  const [socketUrl, setSocketUrl] = useState("");

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pending.current) {
        abort.current = true;
        return;
      }
      const call = callRef.current;
      callRef.current = null;
      call?.stop();
    };
  }, []);

  const start = useCallback(async (next: SessionSetup) => {
    if (callRef.current || pending.current) return;
    pending.current = true;
    abort.current = false;
    const cancelled = () => abort.current || !mounted.current;

    setError(null);
    setLines([]);
    setState(null);
    setLevel(0);
    setMuted(false);
    setStartedAt(null);
    setEndedAt(null);
    setSocketUrl("");
    setSetup(next);

    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        setPhase("error");
        setError({
          kind: "insecure",
          message: "This browser doesn't allow microphone access on this address. Open the portal over https:// (or on localhost) in a current browser.",
        });
        return;
      }

      setPhase("requesting");
      // Ask for the microphone first, so a refusal doesn't leave a half-opened test call behind.
      try {
        const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
        probe.getTracks().forEach((track) => track.stop());
      } catch {
        if (!mounted.current) return;
        setPhase("error");
        setError({
          kind: "mic",
          message: "Microphone access was blocked. Allow the microphone for this site (the icon in the address bar), then start the call again.",
        });
        return;
      }
      if (cancelled()) {
        if (mounted.current) setPhase("idle");
        return;
      }

      let ticket: TestCallTicket;
      try {
        ticket = await agentApi.testCall({
          direction: next.direction,
          record_id: next.direction === "outbound" ? next.recordId || null : null,
          caller_number: next.direction === "inbound" ? next.callerNumber.trim() : "",
        });
      } catch (err) {
        if (!mounted.current) return;
        setPhase("error");
        setError({ kind: "api", message: formatApiError(err, "Could not start the test call.") });
        return;
      }
      if (cancelled()) {
        if (mounted.current) setPhase("idle");
        return;
      }

      const url = mediaSocketUrl(ticket);
      setSocketUrl(url);
      let wentLive = false;

      const call = new WebCall(ticket, {
        onStatus: (status, detail) => {
          if (!mounted.current || callRef.current !== call) return;
          if (status === "connecting") {
            setPhase("connecting");
          } else if (status === "live") {
            wentLive = true;
            setPhase("live");
            setStartedAt(Date.now());
          } else if (status === "ended") {
            callRef.current = null;
            setPhase("ended");
            setEndedAt(Date.now());
            setLevel(0);
          } else if (status === "error") {
            callRef.current = null;
            setPhase("error");
            setEndedAt(Date.now());
            setLevel(0);
            const text = detail || "The call failed.";
            if (/microphone/i.test(text)) {
              setError({ kind: "mic", message: "Microphone access was blocked. Allow the microphone for this site, then start the call again." });
            } else if (wentLive) {
              setError({ kind: "dropped", message: `The connection to the call server (${url}) dropped.` });
            } else {
              setError({ kind: "server", message: `Could not reach the call server at ${url}.` });
            }
          }
        },
        onTranscript: (role, text) => {
          if (!mounted.current || callRef.current !== call || !text.trim()) return;
          setLines((current) => [...current, { id: nextLineId(), role, text: text.trim() }]);
        },
        onState: (agentState) => {
          if (mounted.current && callRef.current === call) setState(agentState);
        },
        onLevel: (value) => {
          if (mounted.current && callRef.current === call) setLevel(value);
        },
      });
      callRef.current = call;
      try {
        await call.start();
      } catch (err) {
        if (callRef.current === call) callRef.current = null;
        call.stop();
        if (!mounted.current) return;
        setPhase("error");
        setLevel(0);
        setError({ kind: "audio", message: `Could not start audio in this browser${err instanceof Error && err.message ? `: ${err.message}` : "."}` });
        return;
      }
      // A hang-up / unmount while start() was running: stop now that it can take effect.
      if (cancelled()) {
        if (!mounted.current && callRef.current === call) callRef.current = null;
        call.stop();
      }
    } finally {
      pending.current = false;
    }
  }, []);

  const hangUp = useCallback(() => {
    if (pending.current) {
      abort.current = true;
      return;
    }
    callRef.current?.stop();
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((current) => {
      const next = !current;
      callRef.current?.setMuted(next);
      return next;
    });
  }, []);

  return { phase, error, lines, state, setup, level, muted, startedAt, endedAt, socketUrl, start, hangUp, toggleMute };
}

export type VoiceCall = ReturnType<typeof useVoiceCall>;
