"use client";

/** Wizard step 4: the owner's account (sign-in = email unless a username is given). */

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { InfoTip } from "@/components/portal/kit";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Region } from "@/services/api";

export const MIN_PASSWORD = 10;

export type AccountForm = {
  business_name: string;
  owner_name: string;
  email: string;
  phone: string;
  password: string;
  region: string;
  username: string;
  /** Honeypot: hidden from people, stays empty. */
  website: string;
};

export function accountProblem(form: AccountForm): string | null {
  if (form.business_name.trim().length < 2) return "Enter your business name.";
  if (!form.owner_name.trim()) return "Enter your name.";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) return "Enter a valid email address.";
  if (form.password.length < MIN_PASSWORD) return `The password needs at least ${MIN_PASSWORD} characters.`;
  return null;
}

function Row({ id, label, info, children }: { id: string; label: string; info?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 text-sm">
      <span className="flex items-center gap-1.5">
        <label htmlFor={id} className="text-[13.5px] font-semibold text-muted-foreground">
          {label}
        </label>
        {info && <InfoTip label={`About ${label.toLowerCase()}`}>{info}</InfoTip>}
      </span>
      {children}
    </div>
  );
}

export function StepAccount({ form, regions, onChange }: { form: AccountForm; regions: Region[]; onChange: (patch: Partial<AccountForm>) => void }) {
  const [show, setShow] = useState(false);
  const set = (key: keyof AccountForm) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange({ [key]: event.target.value });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Row id="su-business" label="Business name">
        <Input id="su-business" value={form.business_name} onChange={set("business_name")} maxLength={160} autoComplete="organization" required />
      </Row>
      <Row id="su-owner" label="Your name">
        <Input id="su-owner" value={form.owner_name} onChange={set("owner_name")} maxLength={120} autoComplete="name" required />
      </Row>
      <Row id="su-email" label="Email" info="You sign in with it and we send your receipt there.">
        <Input id="su-email" type="email" value={form.email} onChange={set("email")} maxLength={160} autoComplete="email" required />
      </Row>
      <Row id="su-phone" label="Phone">
        <Input id="su-phone" type="tel" value={form.phone} onChange={set("phone")} maxLength={32} autoComplete="tel" />
      </Row>
      <Row id="su-password" label="Password" info={`At least ${MIN_PASSWORD} characters.`}>
        <div className="relative">
          <Input id="su-password" type={show ? "text" : "password"} value={form.password} onChange={set("password")} maxLength={200} autoComplete="new-password" className="pr-10" required />
          <button
            type="button"
            aria-label={show ? "Hide password" : "Show password"}
            className="absolute right-2 top-2 inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
            onClick={() => setShow((value) => !value)}
          >
            {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
          </button>
        </div>
      </Row>
      <Row id="su-region" label="Country" info="Sets the phone format, time zone and currency.">
        <Select id="su-region" value={form.region} onChange={set("region")}>
          {regions.map((region) => (
            <option key={region.code} value={region.code}>
              {region.label}
            </option>
          ))}
        </Select>
      </Row>
      {/* Honeypot: off-screen and skipped by keyboard; bots fill it, people never see it. */}
      <div aria-hidden className="absolute left-[-10000px] top-auto h-px w-px overflow-hidden">
        <label htmlFor="su-website">Website</label>
        <input id="su-website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
      </div>
    </div>
  );
}
