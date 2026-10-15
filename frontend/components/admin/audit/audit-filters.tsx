"use client";

import { FormEvent, useEffect, useState } from "react";
import { Search, X } from "lucide-react";

import { FilterBar } from "@/components/admin/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Merchant } from "@/services/api";

export type AuditFilterValues = { action: string; merchant_id: string; actor: string; actor_type: string };

/** Action (exact, or a prefix ending in *), account, actor id and actor type. Text applies on Enter. */
export function AuditFilters({
  values,
  merchants,
  onChange,
}: {
  values: AuditFilterValues;
  merchants: Merchant[];
  onChange: (patch: Partial<AuditFilterValues>) => void;
}) {
  const [action, setAction] = useState(values.action);
  const [actor, setActor] = useState(values.actor);
  useEffect(() => setAction(values.action), [values.action]);
  useEffect(() => setActor(values.actor), [values.actor]);

  const apply = (event: FormEvent) => {
    event.preventDefault();
    onChange({ action: action.trim(), actor: actor.trim() });
  };
  const filtered = Boolean(values.action || values.merchant_id || values.actor || values.actor_type);

  return (
    <form onSubmit={apply}>
      <FilterBar label="Filter the audit log">
        <Input
          className="sm:w-56"
          aria-label="Action"
          placeholder="Action, e.g. admin.*"
          title='Exact action, or a prefix ending in "*"'
          value={action}
          onChange={(e) => setAction(e.target.value)}
          onBlur={() => action.trim() !== values.action && onChange({ action: action.trim() })}
        />
        <Select className="sm:w-56" aria-label="Account" value={values.merchant_id} onChange={(e) => onChange({ merchant_id: e.target.value })}>
          <option value="">All accounts</option>
          {values.merchant_id && !merchants.some((m) => m.id === values.merchant_id) && <option value={values.merchant_id}>Selected account</option>}
          {merchants.map((m) => (
            <option key={m.id} value={m.id}>
              {m.business_name}
            </option>
          ))}
        </Select>
        <Select className="sm:w-36" aria-label="Actor type" value={values.actor_type} onChange={(e) => onChange({ actor_type: e.target.value })}>
          <option value="">Anyone</option>
          <option value="admin">Admins</option>
          <option value="merchant">Owners</option>
          <option value="system">System</option>
        </Select>
        <Input
          className="sm:w-48"
          aria-label="Actor id"
          placeholder="Actor id"
          title="An admin user id, env:<name>, or an account id"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          onBlur={() => actor.trim() !== values.actor && onChange({ actor: actor.trim() })}
        />
        <Button type="submit" variant="outline" size="sm" aria-label="Apply filters">
          <Search className="h-3.5 w-3.5" />
        </Button>
        {filtered && (
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ action: "", merchant_id: "", actor: "", actor_type: "" })}>
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        )}
      </FilterBar>
    </form>
  );
}
