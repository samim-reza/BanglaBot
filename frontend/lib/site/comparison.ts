/** "What it costs elsewhere" table on the pricing page. */

import { BRAND } from "@/lib/brand";

export const COMPARISON = [
  {
    option: "Full-time receptionist",
    cost: "~$3,100 / month",
    unit: "wages for one shift",
    detail: "One shift, five days a week. Benefits, breaks, sick days and evenings are extra.",
    ours: false,
  },
  {
    option: "Live answering service",
    cost: "~$3.45–$5 / minute",
    unit: "e.g. $250 for 50 minutes",
    detail: "Takes messages well; usually can't book into your schedule or call customers back.",
    ours: false,
  },
  {
    option: "Developer voice platforms",
    cost: "$0.07–$0.31 / minute",
    unit: "plus engineering",
    detail: "You build and maintain the flows, booking logic, telephony and safety rules yourself.",
    ours: false,
  },
  {
    option: `${BRAND.name} Growth`,
    cost: "≈ $0.25 / minute",
    unit: "$149 for 600 minutes",
    detail: "A ready-made agent that answers 24/7, books into your records and calls back.",
    ours: true,
  },
] as const;

export const COMPARISON_SOURCES =
  "Receptionist: U.S. Bureau of Labor Statistics, Occupational Employment and Wage Statistics, receptionists and information clerks, median annual wage $37,230 (May 2024) ÷ 12 months; wages only. Answering service: published per-minute plan prices, e.g. Ruby's 50-minute plan at $250. Developer platforms: published per-minute list prices of developer voice-AI platforms, before telephony and engineering time. Vendor prices change; check current rates.";
