/** Privacy Policy content, rendered by app/(site)/privacy/page.tsx. Shared facts live in ./legal.ts. */

import { BRAND } from "@/lib/brand";

import { CONTACT_US, LEGAL, RETENTION, SUBPROCESSORS, smsTermsBlocks, type LegalDoc } from "./legal";

const name = BRAND.name;

export const PRIVACY: LegalDoc = {
  title: "Privacy Policy",
  description: `How ${name} collects, uses and protects information about the businesses that use it and the people who call or message them.`,
  updated: LEGAL.updated,
  summary: `${name} answers calls and messages for businesses. This policy explains what information that involves, who controls it, and the choices you have.`,
  sections: [
    {
      id: "who-we-are",
      title: "Who we are",
      blocks: [
        `${LEGAL.entity} ("${name}", "we", "us") provides AI receptionists: voice and chat agents that answer phone calls, website chats and WhatsApp, Messenger and Instagram messages for businesses, book appointments and orders, and send confirmations and reminders.`,
        `This policy covers people who visit our website or hold a ${name} account, and people who call, text or chat with a business that uses ${name} ("callers"). Our [Terms of Service](/terms) govern use of the service.`,
      ],
    },
    {
      id: "roles",
      title: "Our role",
      blocks: [
        {
          terms: [
            ["Account and website data", `${name} is the controller. We decide how this information is used, as described here.`],
            [
              "Caller data",
              `The business you called or messaged is the controller, and ${name} processes the information on its behalf, as its processor or service provider. The business's own privacy notice applies, and requests about caller data should go to that business first. We help businesses answer them.`,
            ],
          ],
        },
      ],
    },
    {
      id: "information-we-collect",
      title: "Information we collect",
      blocks: [
        {
          terms: [
            ["Account information", "Name, business name, email address, phone number, sign-in details (passwords are stored only as secure hashes), country and team members."],
            ["Business content", "What a business sets up for its agent: services, menus, staff, prices, opening hours, knowledge base, greetings and settings."],
            ["Call audio and recordings", "The audio of calls the agent answers or places. When recording is on, the call is recorded and stored."],
            ["Transcripts and messages", "The text of what was said on calls, and the messages exchanged in chats and on messaging channels."],
            ["Bookings and records", "Appointments, orders, reservations, visits and leads, with the details callers give: names, phone numbers, email and street addresses, and notes."],
            ["Phone numbers and call details", "Caller ID, numbers called, time, duration, outcome, transfer and text-message delivery status."],
            ["Usage and billing", "Minutes, chats and texts used, plan and add-ons, invoices and payment status. Card details go directly to our payment processor; we never see or store full card numbers."],
            ["Connected accounts", "Access tokens for services a business connects, such as Google Calendar or a Facebook Page. We store them encrypted."],
            ["Website and device data", "IP address, browser type, pages visited and what you send through our contact and sign-up forms."],
          ],
        },
      ],
    },
    {
      id: "how-we-use-it",
      title: "How we use information",
      blocks: [
        {
          list: [
            "To provide the service: answer calls and messages, check availability, make bookings, send confirmations and reminders, and transfer calls.",
            "To show each business its own calls, recordings, transcripts and records.",
            "To bill for plans, add-ons and usage, and to prevent fraud and abuse.",
            "To keep the service secure and reliable, and to fix errors, including reviewing conversations when a business asks for help or a problem is reported.",
            "To improve the service using usage statistics and de-identified data.",
            "To contact account holders about their account, billing, security and product updates. You can opt out of non-essential emails.",
            "To meet legal obligations and enforce our terms.",
          ],
        },
        `We do not sell personal information, we do not use it for targeted advertising, and we do not use caller conversations to train our own AI models.`,
      ],
    },
    {
      id: "ai-processing",
      title: "AI processing",
      blocks: [
        `The agent is automated. During a call or chat, the caller's audio and messages are sent in real time to speech-recognition, language-model and text-to-speech providers (listed under [Service providers](#service-providers)) so the agent can understand and reply. Providers process this content under their API terms to deliver the service.`,
        "The agent answers from the information the business provides. It can mishear or make mistakes, so businesses can review every call and change or cancel any booking. The agent does not make decisions with legal or similarly significant effects about callers.",
      ],
    },
    {
      id: "call-recording",
      title: "Call recording",
      blocks: [
        "When a business turns recording on, calls are recorded and transcribed. Some US states and many countries require every party to agree before a call is recorded.",
        `The business is responsible for giving callers any notice the law requires and getting any required consent. The agent can announce at the start of each call that the caller is speaking with an AI assistant and that the call is recorded. Callers who don't want to be recorded can ask for a person, end the call, or contact the business another way.`,
      ],
    },
    {
      id: "text-messages",
      title: "Text messages",
      blocks: smsTermsBlocks(),
    },
    {
      id: "sharing",
      title: "How we share information",
      blocks: [
        {
          list: [
            "With the business the conversation or booking belongs to.",
            "With the service providers below, who process it only to run the service for us, under contracts that protect it.",
            "With services a business connects, such as its calendar, webhooks or messaging accounts, only as that business configures.",
            "When the law requires it, or to protect the rights, safety and property of our users, callers, the public or us.",
            "With a buyer or successor if our business is merged or sold, subject to this policy.",
          ],
        },
        "We never share mobile numbers or text-message opt-in data for marketing (see [Text messages](#text-messages)).",
      ],
    },
    {
      id: "service-providers",
      title: "Service providers",
      blocks: [
        "These companies process personal information for us. Not every provider handles every conversation: the agent uses one provider at a time and switches if one is unavailable.",
        { table: { head: ["Provider", "What it does", "Location"], rows: SUBPROCESSORS.map((item) => [item.name, item.purpose, item.location]) } },
        "We update this list when providers change.",
      ],
    },
    {
      id: "retention",
      title: "How long we keep information",
      blocks: [
        {
          terms: [
            ["Call recordings", `${RETENTION.recordingDays} days, then deleted. ${RETENTION.extendedRecordingMonths} months on the Pro plan or with the ${RETENTION.extendedRecordingMonths}-month recordings add-on.`],
            ["Transcripts, messages, bookings and records", "While the account is active, unless the business deletes them sooner."],
            ["Account information", `While the account is active. When an account closes, its data is deleted within ${RETENTION.closedAccountDays} days.`],
            ["Billing records", "As long as tax and accounting laws require."],
            ["Contact form messages", "As long as needed to reply and follow up."],
          ],
        },
        "Backups are overwritten on a rolling schedule. We may keep information longer when the law requires it or to resolve a dispute.",
      ],
    },
    {
      id: "security",
      title: "Security",
      blocks: [
        {
          list: [
            "Encryption in transit (HTTPS/TLS) for the website, portal and our providers.",
            "Connected-account tokens and other secrets encrypted at rest; passwords stored only as secure hashes.",
            "Each business's records are visible only to people signed in to that account, and to authorized staff who need them to provide support.",
            "Role-based staff access with optional two-factor authentication, and an audit log of administrative actions.",
            "Signed webhook URLs, rate limits and monitoring to block abuse.",
          ],
        },
        "No system is perfectly secure. If a breach affects your information, we will notify you as the law requires.",
      ],
    },
    {
      id: "health-information",
      title: "Health information",
      blocks: [
        `Clinics, dental practices and veterinary practices use ${name} to book appointments. If you are a HIPAA covered entity or business associate, contact us before using ${name} with protected health information. We process protected health information only under a signed business associate agreement.`,
      ],
    },
    {
      id: "your-rights",
      title: "Your rights and choices",
      blocks: [
        `Account holders can view and update most of their information in the portal. To access, correct, export or delete your information, or to close your account, ${CONTACT_US}. We may need to verify your identity first.`,
        `Callers: contact the business you called. If you contact us instead, we will pass your request to that business and help it respond.`,
        {
          terms: [
            ["US state privacy laws", "Depending on where you live (for example, California), you may have the right to know what we collect, to get a copy, to correct or delete it, and to opt out of its sale or sharing. We don't sell or share personal information for advertising. You can use an authorized agent, and we won't treat you differently for using your rights."],
            ["EEA, UK and Switzerland", "You may also object to or restrict processing, ask for portability, and complain to your data protection authority. We rely on contract, legitimate interests, consent and legal obligation as our legal bases."],
          ],
        },
        "We respond within the time the law requires, usually 30 to 45 days.",
      ],
    },
    {
      id: "cookies",
      title: "Cookies and browser storage",
      blocks: [
        `Our website and portal use your browser's storage only to keep you signed in and remember settings such as the theme. The chat widget on a business's website remembers your conversation for the browser session. We don't use advertising cookies or third-party trackers.`,
      ],
    },
    {
      id: "children",
      title: "Children",
      blocks: [
        `${name} is a service for businesses and is not directed to children under 13. We don't knowingly collect children's information for our own purposes. When a parent or guardian gives a business details about a child, for example to book a pediatric appointment, we process them on that business's behalf.`,
      ],
    },
    {
      id: "international-transfers",
      title: "International transfers",
      blocks: [
        `Our servers and database are hosted in ${LEGAL.hostingRegion}, and our providers process information in the United States and other countries. Where the law requires it, we protect transfers with safeguards such as the European Commission's standard contractual clauses.`,
      ],
    },
    {
      id: "changes",
      title: "Changes to this policy",
      blocks: [
        "We will post any changes here and update the date at the top. If a change is significant, we will tell account holders by email or in the portal before it takes effect.",
      ],
    },
    {
      id: "contact",
      title: "Contact us",
      blocks: [`Questions or requests about privacy: ${CONTACT_US}.`],
    },
  ],
};
