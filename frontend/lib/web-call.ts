/**
 * Browser test call: talk to your agent through the microphone.
 *
 * The backend's media websocket speaks Twilio's Media Streams protocol, so the
 * browser plays Twilio: it sends `connected` / `start` (with the signed ticket)
 * and 20 ms frames of 8 kHz μ-law audio, plays the agent's μ-law frames,
 * echoes `mark`s once they have been heard and obeys `clear` (barge-in). A
 * test call therefore runs exactly the production call path. In this mode the
 * backend also sends `transcript` / `state` / `hangup` events for the console.
 */

import type { AgentState, TestCallTicket } from "@/services/api";

export type WebCallStatus = "connecting" | "live" | "ended" | "error";

export type WebCallEvents = {
  onStatus?: (status: WebCallStatus, detail?: string) => void;
  onTranscript?: (role: "agent" | "caller", text: string) => void;
  onState?: (state: AgentState) => void;
  /** Microphone level 0..1, ~12 times a second. */
  onLevel?: (level: number) => void;
};

const TARGET_RATE = 8000;
const FRAME_SAMPLES = 160; // 20 ms at 8 kHz

// --- G.711 μ-law -------------------------------------------------------------------
const MULAW_DECODE = new Float32Array(256);
for (let i = 0; i < 256; i++) {
  const u = ~i & 0xff;
  const sign = u & 0x80;
  const exponent = (u >> 4) & 0x07;
  const mantissa = u & 0x0f;
  let sample = ((mantissa << 3) + 0x84) << exponent;
  sample -= 0x84;
  MULAW_DECODE[i] = (sign ? -sample : sample) / 32768;
}

function linearToMulaw(value: number): number {
  const BIAS = 0x84;
  const CLIP = 32635;
  let sample = Math.round(Math.max(-1, Math.min(1, value)) * 32767);
  const sign = sample < 0 ? 0x80 : 0;
  if (sign) sample = -sample;
  if (sample > CLIP) sample = CLIP;
  sample += BIAS;
  let exponent = 7;
  for (let mask = 0x4000; (sample & mask) === 0 && exponent > 0; exponent--, mask >>= 1) {
    /* find the segment */
  }
  const mantissa = (sample >> (exponent + 3)) & 0x0f;
  return ~(sign | (exponent << 4) | mantissa) & 0xff;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function fromBase64(text: string): Uint8Array {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("agent-capture", Capture);
`;

/** Where the media websocket lives. Local dev: the backend port directly (the Next
 * dev proxy does not carry websockets); otherwise the public URL from the ticket. */
export function mediaSocketUrl(ticket: TestCallTicket): string {
  const override = process.env.NEXT_PUBLIC_BACKEND_WS_URL;
  if (override) return `${override.replace(/\/$/, "")}/twilio/media`;
  const { hostname, protocol, host } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") return `ws://${hostname}:8000/twilio/media`;
  if (ticket.ws_url) return ticket.ws_url;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}/twilio/media`;
}

export class WebCall {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private playhead = 0;
  private playing: AudioBufferSourceNode[] = [];
  private pending: number[] = [];
  private phase = 0;
  private accSum = 0;
  private accCount = 0;
  private levelAccum = 0;
  private levelCount = 0;
  private timers: number[] = [];
  private stopped = false;
  muted = false;

  constructor(
    private readonly ticket: TestCallTicket,
    private readonly events: WebCallEvents = {},
  ) {}

  async start(): Promise<void> {
    this.events.onStatus?.("connecting");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      this.fail("Microphone permission was denied.");
      return;
    }
    if (this.stopped) {
      // Hung up while the permission prompt was open.
      this.stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    await this.ctx.resume();
    const moduleUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
    await this.ctx.audioWorklet.addModule(moduleUrl);
    URL.revokeObjectURL(moduleUrl);
    if (this.stopped) {
      this.stream.getTracks().forEach((track) => track.stop());
      void this.ctx.close().catch(() => undefined);
      return;
    }
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "agent-capture");
    this.node.port.onmessage = (event: MessageEvent<Float32Array>) => this.onMic(event.data);
    this.source.connect(this.node);
    // The worklet must be pulled by the graph; a muted gain keeps the mic out of the speakers.
    const sink = this.ctx.createGain();
    sink.gain.value = 0;
    this.node.connect(sink).connect(this.ctx.destination);

    this.ws = new WebSocket(mediaSocketUrl(this.ticket));
    this.ws.onopen = () => this.handshake();
    this.ws.onmessage = (event) => this.onMessage(event.data);
    this.ws.onerror = () => this.fail("Could not reach the call server.");
    this.ws.onclose = () => this.finish();
  }

  setMuted(muted: boolean) {
    this.muted = muted;
  }

  stop() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event: "stop", streamSid: this.ticket.stream_sid, stop: {} }));
      this.ws.close();
    }
    this.finish();
  }

  // ---- protocol ---------------------------------------------------------------------
  private handshake() {
    const ws = this.ws;
    if (!ws) return;
    ws.send(JSON.stringify({ event: "connected", protocol: "Call", version: "1.0.0" }));
    ws.send(
      JSON.stringify({
        event: "start",
        sequenceNumber: "1",
        streamSid: this.ticket.stream_sid,
        start: {
          streamSid: this.ticket.stream_sid,
          callSid: "",
          tracks: ["inbound"],
          mediaFormat: { encoding: "audio/x-mulaw", sampleRate: 8000, channels: 1 },
          customParameters: {
            order_id: this.ticket.order_id ?? "",
            call_log_id: this.ticket.call_log_id,
            media_token: this.ticket.media_token,
          },
        },
      }),
    );
    this.events.onStatus?.("live");
  }

  private onMessage(raw: unknown) {
    if (typeof raw !== "string") return;
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    switch (message.event) {
      case "media": {
        const payload = (message.media as { payload?: string } | undefined)?.payload;
        if (payload) this.play(fromBase64(payload));
        break;
      }
      case "mark": {
        const name = (message.mark as { name?: string } | undefined)?.name;
        if (name) this.echoMark(name);
        break;
      }
      case "clear":
        this.clearPlayback();
        break;
      case "transcript":
        this.events.onTranscript?.(message.role === "agent" ? "agent" : "caller", String(message.text ?? ""));
        break;
      case "state":
      case "hangup":
        this.events.onState?.(message as unknown as AgentState);
        break;
    }
  }

  // ---- audio out --------------------------------------------------------------------------
  private play(bytes: Uint8Array) {
    const ctx = this.ctx;
    if (!ctx) return;
    const buffer = ctx.createBuffer(1, bytes.length, TARGET_RATE);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bytes.length; i++) data[i] = MULAW_DECODE[bytes[i]];
    const node = ctx.createBufferSource();
    node.buffer = buffer;
    node.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.04, this.playhead);
    node.start(at);
    this.playhead = at + buffer.duration;
    this.playing.push(node);
    node.onended = () => {
      this.playing = this.playing.filter((item) => item !== node);
    };
  }

  private echoMark(name: string) {
    const ctx = this.ctx;
    const delay = ctx ? Math.max(0, this.playhead - ctx.currentTime) : 0;
    const timer = window.setTimeout(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ event: "mark", streamSid: this.ticket.stream_sid, mark: { name } }));
      }
    }, delay * 1000);
    this.timers.push(timer);
  }

  private clearPlayback() {
    for (const node of this.playing) {
      try {
        node.stop();
      } catch {
        /* already stopped */
      }
    }
    this.playing = [];
    this.playhead = this.ctx?.currentTime ?? 0;
  }

  // ---- audio in ---------------------------------------------------------------------------
  private onMic(chunk: Float32Array) {
    const ctx = this.ctx;
    if (!ctx || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    // Boxcar decimation to 8 kHz: averaging each output's input window is a cheap
    // low-pass, so speech above 4 kHz does not alias into the transcriber.
    const ratio = ctx.sampleRate / TARGET_RATE;
    for (let i = 0; i < chunk.length; i++) {
      this.accSum += chunk[i];
      this.accCount += 1;
      this.phase += 1;
      if (this.phase >= ratio) {
        this.phase -= ratio;
        const sample = this.muted ? 0 : this.accSum / this.accCount;
        this.accSum = 0;
        this.accCount = 0;
        this.pending.push(sample);
        this.levelAccum += sample * sample;
        this.levelCount += 1;
      }
    }
    while (this.pending.length >= FRAME_SAMPLES) {
      const frame = this.pending.splice(0, FRAME_SAMPLES);
      const bytes = new Uint8Array(FRAME_SAMPLES);
      for (let i = 0; i < FRAME_SAMPLES; i++) bytes[i] = linearToMulaw(frame[i]);
      this.ws.send(JSON.stringify({ event: "media", streamSid: this.ticket.stream_sid, media: { track: "inbound", payload: toBase64(bytes) } }));
    }
    if (this.levelCount >= 640) {
      this.events.onLevel?.(Math.min(1, Math.sqrt(this.levelAccum / this.levelCount) * 4));
      this.levelAccum = 0;
      this.levelCount = 0;
    }
  }

  // ---- teardown ---------------------------------------------------------------------------
  private fail(detail: string) {
    this.events.onStatus?.("error", detail);
    this.finish(false);
  }

  private finish(notify = true) {
    if (this.stopped) return;
    this.stopped = true;
    for (const timer of this.timers) window.clearTimeout(timer);
    this.clearPlayback();
    this.node?.port.close();
    this.source?.disconnect();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.ctx?.close().catch(() => undefined);
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close();
    if (notify) this.events.onStatus?.("ended");
  }
}
