"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LoaderCircle, MessageCircle, PhoneOff } from "lucide-react";

import { API_BASE, publicApi } from "@/services/api";

/*
 * The demo chat widget is a third-party style <script> that appends a fixed
 * bubble to <body>. It is injected once per page session; pages that show the
 * demo section make it visible, every other page hides it, so it never follows
 * a visitor into the portal.
 */

/** The widget marks its host element with this attribute. */
const WIDGET_ATTRIBUTE = "data-agent-widget";
const HOST_MARK = "siteDemoWidget";

let keyPromise: Promise<string> | null = null;
let injected = false;
let mounted = 0;

function demoKey(): Promise<string> {
  if (!keyPromise) {
    keyPromise = publicApi.catalog().then(
      (catalog) => (catalog.demo_widget_key || "").trim(),
      (error: unknown) => {
        keyPromise = null; // let the next visit retry
        throw error;
      },
    );
  }
  return keyPromise;
}

function widgetHost(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>(`:scope > [data-site-demo-widget]`);
}

function applyVisibility() {
  const host = widgetHost();
  if (host) host.style.display = mounted > 0 ? "" : "none";
}

function injectWidget(key: string) {
  if (injected) return;
  injected = true;
  // Tag the widget's host as soon as it appears (its config loads asynchronously).
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of Array.from(record.addedNodes)) {
        if (node instanceof HTMLElement && node.hasAttribute(WIDGET_ATTRIBUTE)) {
          node.dataset[HOST_MARK] = "1";
          observer.disconnect();
          applyVisibility();
          return;
        }
      }
    }
  });
  observer.observe(document.body, { childList: true });
  window.setTimeout(() => observer.disconnect(), 30_000);

  const script = document.createElement("script");
  script.src = `${API_BASE}/api/public/widget.js`;
  script.async = true;
  script.dataset.key = key;
  document.body.appendChild(script);
}

type DemoState = "loading" | "ready" | "offline";

/** Loads the demo agent's chat bubble and tells the visitor where to find it. */
export function LiveDemo() {
  const [state, setState] = useState<DemoState>("loading");

  useEffect(() => {
    let cancelled = false;
    mounted += 1;
    applyVisibility();
    demoKey()
      .then((key) => {
        if (!key) {
          if (!cancelled) setState("offline");
          return;
        }
        injectWidget(key);
        applyVisibility();
        if (!cancelled) setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("offline");
      });
    return () => {
      cancelled = true;
      mounted -= 1;
      applyVisibility();
    };
  }, []);

  if (state === "loading") {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground" role="status">
        <LoaderCircle className="h-5 w-5 animate-spin text-primary" aria-hidden />
        Connecting to the demo agent…
      </div>
    );
  }

  if (state === "offline") {
    return (
      <div className="rounded-xl border border-border bg-card p-5" role="status">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-secondary text-muted-foreground">
            <PhoneOff className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="font-semibold text-foreground">The demo is offline right now</p>
            <p className="mt-1 text-sm text-muted-foreground">
              We&apos;ll happily show you a live agent instead — it takes 20 minutes.
            </p>
            <Link href="/contact?plan=demo" className="mt-3 inline-block text-sm font-semibold text-primary-dark hover:underline">
              Talk to sales →
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-primary bg-accent p-5" role="status">
      <div className="flex items-start gap-3">
        <span className="relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <MessageCircle className="h-5 w-5" aria-hidden />
          <span className="absolute -right-0.5 -top-0.5 h-3 w-3 animate-pulse rounded-full border-2 border-accent bg-[#22c55e]" aria-hidden />
        </span>
        <div>
          <p className="font-semibold text-foreground">The demo agent is live</p>
          <p className="mt-1 text-sm text-foreground/80">
            Open the chat bubble at the bottom right — it&apos;s a real clinic agent (CityCare Family Clinic demo).
          </p>
        </div>
      </div>
    </div>
  );
}
