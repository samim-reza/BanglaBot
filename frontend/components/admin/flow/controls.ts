import type { FlowConfig } from "@/services/api/agentFlow";

import type { FlowState } from "./flow-paths";

/** Everything a step / branch row needs to show and change its settings. */
export type FlowControls = {
  state: FlowState;
  /** The owner's settings as saved (for "Owner: …"). */
  saved: FlowConfig;
  canEdit: boolean;
  canLock: boolean;
  errors: Record<string, string>;
  setValue: (path: string, value: unknown) => void;
  toggleLock: (path: string) => void;
};

/** Locked settings edit the lock (superadmin); open ones edit the owner's value (superadmin, support). */
export const editable = (c: FlowControls, path: string) => (path in c.state.locks ? c.canLock : c.canEdit);
