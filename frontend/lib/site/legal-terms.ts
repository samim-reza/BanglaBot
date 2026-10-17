/** Terms of Service content, rendered by app/(site)/terms/page.tsx. Shared facts live in ./legal.ts. */

import { BRAND } from "@/lib/brand";

import { CONTACT_US, LEGAL, smsTermsBlocks, type LegalDoc } from "./legal";
import { TRIAL } from "./pricing";

const name = BRAND.name;

export const TERMS: LegalDoc = {
  title: "Terms of Service",
  description: `The terms that apply when a business uses ${name}'s AI voice and chat agents.`,
  updated: LEGAL.updated,
  summary: `These terms are an agreement between your business and ${LEGAL.entity}. Please read them, especially the sections on acceptable use, emergencies and AI mistakes.`,
  sections: [
    {
      id: "agreement",
      title: "The agreement",
      blocks: [
        `These Terms of Service ("Terms") are between ${LEGAL.entity} ("${name}", "we", "us") and the business that creates an account ("you"). By creating an account or using the service, you agree to these Terms and to our [Privacy Policy](/privacy). If you accept for a company, you confirm that you can bind it.`,
        `${name} is for business use. You must be at least 18 years old to create an account.`,
      ],
    },
    {
      id: "the-service",
      title: "The service",
      blocks: [
        `${name} provides AI agents that answer and place phone calls, reply to website chats and messaging channels, take bookings and orders, and send text messages for your business, together with phone numbers, a web portal and integrations. What's included depends on your plan and add-ons. We improve the service over time and may change or retire features; we won't materially reduce the core service during a paid period you've already paid for.`,
      ],
    },
    {
      id: "your-account",
      title: "Your account",
      blocks: [
        "Give us accurate information and keep it up to date. Keep your sign-in details secret. You are responsible for everything done under your account, including by your team members. Tell us right away if you suspect unauthorized access.",
      ],
    },
    {
      id: "your-callers",
      title: "Your callers and your content",
      blocks: [
        "You are responsible for your relationship with the people who call or message you, and for the information you give the agent (prices, hours, services, policies). In particular, you are responsible for:",
        {
          list: [
            "giving callers any notice the law requires, including that calls are recorded and answered by an AI assistant, and getting any required consent;",
            "having the right to contact the numbers you ask the agent to call or text;",
            "having a privacy notice that tells your customers you use service providers like us;",
            "checking bookings, orders and messages the agent records, and keeping your information current.",
          ],
        },
      ],
    },
    {
      id: "acceptable-use",
      title: "Acceptable use",
      blocks: [
        "You must not use the service, or let anyone else use it, to:",
        {
          list: [
            "make unlawful robocalls or telemarketing calls, send spam, or call or text anyone without the consent the law requires;",
            "break the Telephone Consumer Protection Act (TCPA), the Telemarketing Sales Rule, do-not-call rules, state telemarketing and recording laws, carrier and CTIA messaging rules, or similar laws elsewhere;",
            "impersonate any person or business, spoof caller ID or mislead callers about who they are dealing with;",
            "collect full payment card numbers, Social Security numbers or passwords through the agent;",
            "process protected health information without a signed business associate agreement with us;",
            "send unlawful, harassing, hateful, sexually explicit or infringing content;",
            "probe, overload or disrupt the service, get around usage limits or security, or reverse engineer it;",
            "resell the service unless we have agreed in writing.",
          ],
        },
        "Outbound calls and texts are your responsibility. For reminder calls, bulk and scheduled campaigns and text messages, you alone are responsible for TCPA compliance: getting prior express consent (written consent where required), honoring opt-outs and do-not-call requests, and respecting calling hours.",
        "We may suspend calls, messages or numbers that break these rules or draw carrier complaints.",
      ],
    },
    {
      id: "emergencies",
      title: "Not for emergencies",
      blocks: [
        `${name} is not a substitute for 911 or any emergency service. The agent cannot call emergency services or send help. It is designed to tell callers who describe an emergency to hang up and call 911 or their local emergency number, but it may not recognize every emergency. Do not rely on ${name} for urgent, medical or life-safety situations, and make sure your customers know how to reach you directly when it matters.`,
      ],
    },
    {
      id: "ai-mistakes",
      title: "The AI can make mistakes",
      blocks: [
        "The agent uses speech recognition and AI language models. It can mishear callers, misunderstand requests, give incomplete or wrong answers, or record a booking incorrectly, even though it reads key details back before booking. It answers only from the information you provide and does not give medical, legal, financial or other professional advice. Review its work and correct anything that matters to your business.",
      ],
    },
    {
      id: "numbers-and-messaging",
      title: "Phone numbers and messaging",
      blocks: [
        "Phone numbers we provide are leased from our telecom carriers. You can use them while your account is active, but you don't own them, and a number may be released after your account closes. Moving a number to or from another provider depends on carrier rules. Texting US numbers requires carrier registration (A2P 10DLC), which we file using information you give us; carriers may charge registration and messaging fees.",
      ],
    },
    {
      id: "sms-terms",
      title: "Text message terms",
      blocks: [...smsTermsBlocks(), "Our [Privacy Policy](/privacy#text-messages) explains how we handle mobile numbers."],
    },
    {
      id: "plans-and-billing",
      title: "Plans, billing and renewal",
      blocks: [
        "Plans are paid in advance, monthly or yearly. Add-ons are billed with your plan. Usage beyond your plan's allowance, such as extra call minutes or texts, is billed at the rates shown in your plan or on our [pricing page](/pricing). Prices exclude taxes, which you pay where they apply.",
        "Each plan renews for another period of the same length unless you cancel before the current period ends. If a renewal isn't paid, we may pause the service until it is. We will give you at least 30 days' notice of a price change, and it applies from your next renewal.",
        "Upgrades take effect right away; downgrades take effect at the end of the current period. Payments are processed by our payment provider. Fees are non-refundable except where the law requires or these Terms say otherwise.",
      ],
    },
    {
      id: "free-trial",
      title: "Free trial",
      blocks: [
        `When we offer a free trial, it lasts ${TRIAL.days} days and includes ${TRIAL.minutes} call minutes and ${TRIAL.texts} texts, or whatever we show when you sign up. One trial per business. The trial ends automatically, and you are not charged unless you choose a paid plan. We may change or end trials at any time.`,
      ],
    },
    {
      id: "cancellation",
      title: "Cancellation",
      blocks: [
        `You can cancel at any time in the portal or by contacting us. Cancellation takes effect at the end of the current billing period, and the service keeps working until then. We don't refund partial periods. Export anything you want to keep before your account closes; after that, we delete your data as described in the [Privacy Policy](/privacy#retention).`,
      ],
    },
    {
      id: "your-data",
      title: "Your data",
      blocks: [
        `You own your content and the information about your callers. You give us permission to host, process and transmit it only to provide, secure and support the service, and as described in our [Privacy Policy](/privacy). For caller data we act as your processor or service provider. We may use usage statistics and de-identified data, which can't identify you or your callers, to run and improve the service. To request a data processing addendum, ${CONTACT_US}.`,
      ],
    },
    {
      id: "our-property",
      title: "Our property",
      blocks: [
        `${name}, including its software, agents, conversation flows, website and brand, belongs to us and our licensors. These Terms give you a right to use the service, not ownership of it. If you send us feedback, we may use it without any obligation to you.`,
      ],
    },
    {
      id: "third-party-services",
      title: "Third-party services",
      blocks: [
        "The service relies on carriers and other providers, and connects to services you choose, such as Google Calendar, Meta messaging and payment providers. Your use of those services is subject to their terms. We are not responsible for their outages or actions.",
      ],
    },
    {
      id: "availability",
      title: "Availability",
      blocks: [
        "We work to keep the service available around the clock, but we don't promise it will be uninterrupted or error-free. Maintenance, carrier and provider outages, and events outside our control can affect calls and messages. Any service-level commitment must be agreed in writing.",
      ],
    },
    {
      id: "disclaimers",
      title: "Disclaimers",
      blocks: [
        `Except as these Terms expressly say, the service is provided "as is" and "as available". To the fullest extent the law allows, we disclaim all implied warranties, including merchantability, fitness for a particular purpose and non-infringement.`,
      ],
    },
    {
      id: "limitation-of-liability",
      title: "Limitation of liability",
      blocks: [
        "To the fullest extent the law allows, neither party is liable for indirect, incidental, special, consequential or punitive damages, or for lost profits, revenue, bookings or data, even if told they were possible.",
        "Our total liability for all claims relating to the service is limited to the fees you paid us in the 12 months before the event that caused the claim. These limits don't apply to your payment obligations or your obligations under Indemnity.",
      ],
    },
    {
      id: "indemnity",
      title: "Indemnity",
      blocks: [
        "You will defend and indemnify us against third-party claims, and the resulting costs, arising from your content, the calls and texts made for you (including claims under the TCPA or recording laws), your failure to give callers required notices or get their consent, or your breach of these Terms or the law.",
      ],
    },
    {
      id: "suspension-and-termination",
      title: "Suspension and termination",
      blocks: [
        "We may suspend or end your access if you break these Terms, don't pay, create legal or security risk, or if a carrier or the law requires it. Where reasonable, we will warn you first and give you a chance to fix the problem. You may stop using the service at any time. Sections that by their nature should survive (such as fees owed, your data, disclaimers, limitation of liability, indemnity and governing law) survive termination.",
      ],
    },
    {
      id: "governing-law",
      title: "Governing law and disputes",
      blocks: [
        `These Terms are governed by the laws of ${LEGAL.governingLaw}, without regard to conflict-of-laws rules. Before filing a claim, contact us and give us 30 days to try to resolve the dispute informally. Any claim that isn't resolved goes to ${LEGAL.courts}, and both parties agree to their jurisdiction.`,
      ],
    },
    {
      id: "changes",
      title: "Changes to these Terms",
      blocks: [
        "We may update these Terms. We will post changes here and update the date at the top. For significant changes, we will tell account holders by email or in the portal at least 30 days before they take effect. Using the service after that means you accept the updated Terms.",
      ],
    },
    {
      id: "general",
      title: "General",
      blocks: [
        "These Terms and any order or written agreement with us are the entire agreement on this subject. If a provision can't be enforced, the rest stays in effect. Not enforcing a right isn't a waiver. You may not transfer these Terms without our consent; we may transfer them in a merger or sale of our business. Neither party is liable for delays caused by events beyond its reasonable control.",
      ],
    },
    {
      id: "contact",
      title: "Contact us",
      blocks: [`Questions about these Terms: ${CONTACT_US}.`],
    },
  ],
};
