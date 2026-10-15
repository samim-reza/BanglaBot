/** Options for the talk-to-sales form. Business type values match AgentKey (?type= prefill). */

import { TRIAL } from "./pricing";

export const BUSINESS_TYPES = [
  { value: "clinic", label: "Clinic / doctors" },
  { value: "dental", label: "Dental practice" },
  { value: "vet", label: "Veterinary clinic" },
  { value: "restaurant", label: "Restaurant" },
  { value: "salon", label: "Salon / spa" },
  { value: "real_estate", label: "Real estate agency" },
  { value: "home_service", label: "Home services" },
  { value: "ecommerce", label: "E-commerce" },
  { value: "custom", label: "Custom setup" },
  { value: "other", label: "Something else" },
] as const;

export const MONTHLY_CALLS = [
  { value: "<100", label: "Fewer than 100" },
  { value: "100–500", label: "100–500" },
  { value: "500–2,000", label: "500–2,000" },
  { value: "2,000+", label: "2,000+" },
] as const;

export const INTERESTS = [
  { value: "trial", label: `${TRIAL.days}-day free trial` },
  { value: "chat", label: "Chat agent plan" },
  { value: "starter", label: "Starter plan" },
  { value: "growth", label: "Growth plan" },
  { value: "pro", label: "Pro plan" },
  { value: "enterprise", label: "Enterprise" },
  { value: "demo", label: "A live demo" },
] as const;
