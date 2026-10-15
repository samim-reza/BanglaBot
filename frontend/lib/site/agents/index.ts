/** Every solution page, in display order (home cards, /solutions, footer). */

import type { AgentKey, AgentSolution } from "../types";
import { clinic } from "./clinic";
import { custom } from "./custom";
import { dental } from "./dental";
import { ecommerce } from "./ecommerce";
import { homeService } from "./home-service";
import { realEstate } from "./real-estate";
import { restaurant } from "./restaurant";
import { salon } from "./salon";
import { vet } from "./vet";

export const AGENTS: AgentSolution[] = [clinic, dental, vet, restaurant, salon, realEstate, homeService, ecommerce, custom];

export function agentBySlug(slug: string): AgentSolution | undefined {
  return AGENTS.find((agent) => agent.slug === slug);
}

export function agentByKey(key: AgentKey): AgentSolution | undefined {
  return AGENTS.find((agent) => agent.key === key);
}
