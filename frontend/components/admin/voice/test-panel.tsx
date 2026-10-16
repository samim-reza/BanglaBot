"use client";

import { FormEvent, useState } from "react";
import { Bot, Volume2 } from "lucide-react";

import { DialogError } from "@/components/admin/overlay";
import { fmtBytes, fmtMs } from "@/components/admin/numbers";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatApiError } from "@/services/api";
import { systemApi, type LlmTestResult, type TtsTestResult } from "@/services/api/admin/system";

const SAMPLE = "Hello, thank you for calling. How can I help you today?";

/** One-off synth / completion through the live chains (superadmin). */
export function TestPanel() {
  const [text, setText] = useState(SAMPLE);
  const [tts, setTts] = useState<TtsTestResult | null>(null);
  const [llm, setLlm] = useState<LlmTestResult | null>(null);
  const [busy, setBusy] = useState<"tts" | "llm" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async <T,>(kind: "tts" | "llm", call: () => Promise<T>, done: (value: T) => void) => {
    setBusy(kind);
    setError(null);
    try {
      done(await call());
    } catch (err) {
      setError(formatApiError(err, "Test failed."));
    } finally {
      setBusy(null);
    }
  };

  const testTts = (event: FormEvent) => {
    event.preventDefault();
    void run("tts", () => systemApi.testTts(text.trim()), setTts);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="space-y-2" onSubmit={testTts}>
          <div className="flex gap-2">
            <Input aria-label="Text to speak" value={text} maxLength={300} onChange={(event) => setText(event.target.value)} required />
          </div>
          <Button type="submit" variant="outline" disabled={busy !== null || !text.trim()} title="Synthesizes through the live TTS chain (counts toward provider usage)">
            <Volume2 className="h-4 w-4" />
            {busy === "tts" ? "Synthesizing…" : "Test TTS"}
          </Button>
          {tts && (
            <p className="text-sm" role="status">
              <span className="font-semibold">{fmtMs(tts.ms)}</span>
              <span className="text-muted-foreground">
                {" "}
                · {tts.seconds}s audio · {fmtBytes(tts.bytes)}
              </span>
            </p>
          )}
        </form>
        <div className="space-y-2 border-t border-border pt-4">
          <Button variant="outline" disabled={busy !== null} onClick={() => void run("llm", systemApi.testLlm, setLlm)} title="One short completion through the live LLM chain">
            <Bot className="h-4 w-4" />
            {busy === "llm" ? "Asking…" : "Test LLM"}
          </Button>
          {llm && (
            <div className="space-y-1 text-sm" role="status">
              <p>
                <span className="font-semibold">{fmtMs(llm.ms)}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {llm.provider} · <span className="font-mono text-xs">{llm.model}</span>
                </span>
              </p>
              <p className="rounded-md bg-surface p-2 italic">“{llm.text}”</p>
            </div>
          )}
        </div>
        <DialogError message={error} />
      </CardContent>
    </Card>
  );
}
