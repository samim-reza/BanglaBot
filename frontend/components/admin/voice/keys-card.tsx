import { StatusChip } from "@/components/admin/status-chip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const LABELS: Record<string, string> = {
  groq: "Groq",
  gemini: "Gemini",
  deepgram: "Deepgram",
  openai: "OpenAI",
  azure: "Azure Speech",
  shared_audio_cache: "Shared audio cache",
};

/** Which provider keys this deploy has (values are never sent to the console). */
export function KeysCard({ keys }: { keys: Record<string, boolean> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Keys</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-wrap gap-2">
          {Object.entries(keys).map(([key, present]) => (
            <li key={key}>
              <StatusChip state={present ? "ok" : "off"} title={present ? "Configured" : "Not configured"}>
                {LABELS[key] ?? key}
              </StatusChip>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
