import { Pill, type Tone } from "@/components/admin/badges";
import type { SignupStatus } from "@/services/api/admin/signups";

export const SIGNUP_STATUSES: { value: SignupStatus; label: string; tone: Tone }[] = [
  { value: "awaiting_approval", label: "To approve", tone: "blue" },
  { value: "pending_payment", label: "Unpaid", tone: "amber" },
  { value: "approved", label: "Approved", tone: "green" },
  { value: "rejected", label: "Rejected", tone: "red" },
];

export function SignupStatusPill({ status }: { status: string }) {
  const entry = SIGNUP_STATUSES.find((item) => item.value === status);
  return <Pill tone={entry?.tone ?? "neutral"}>{entry?.label ?? status}</Pill>;
}
