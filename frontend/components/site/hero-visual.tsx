import { CalendarCheck, PhoneOutgoing } from "lucide-react";

import { CallTranscript } from "@/components/site/call-transcript";
import { AGENTS } from "@/lib/site-content";

const clinic = AGENTS[0];

/** Hero illustration: a live booking call plus the record it writes. CSS only. */
export function HeroVisual() {
  return (
    <div className="relative mx-auto w-full max-w-md lg:max-w-none">
      <div
        aria-hidden
        className="absolute -inset-6 -z-10 rounded-[2rem] bg-[radial-gradient(70%_70%_at_60%_40%,hsl(var(--tint-strong)/0.45)_0%,transparent_70%)]"
      />
      <CallTranscript conversation={clinic.example} live maxLines={5} />

      <div className="absolute -bottom-8 -left-4 hidden w-60 rounded-xl border border-border bg-card p-4 shadow-xl sm:block lg:-left-10">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-primary-dark">
          <CalendarCheck className="h-4 w-4" aria-hidden />
          New appointment
        </p>
        <dl className="mt-3 space-y-1.5 text-xs">
          {[
            ["Patient", "Leo Garcia"],
            ["Doctor", "Dr. James Carter"],
            ["When", "Wed · 10:40 am"],
            ["Fee", "$140"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="absolute -right-3 -top-5 hidden items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-lg sm:flex">
        <PhoneOutgoing className="h-3.5 w-3.5 text-primary" aria-hidden />
        Reminder call · Tue 6:00 pm
      </div>
    </div>
  );
}
