"""Point the Telnyx TeXML application's voice webhook at a server's SIGNED inbound URL.

    python -m scripts.telnyx_route prod                                   # PUBLIC_BASE_URL or https://api.banglabot.xyz
    python -m scripts.telnyx_route local --url https://xyz.ngrok-free.app
    python -m scripts.telnyx_route prod --dry-run                         # only show what would change

The signature in the URL is computed from THIS shell's settings
(TELNYX_WEBHOOK_SECRET, else ADMIN_TOKEN_SECRET), so run it with the same secrets
as the server that will receive the calls. Before repointing, the script asks
that server (GET /telnyx/inbound/{sig}) whether it accepts the signature and
stops if it doesn't — a mismatch would leave inbound calls unanswered.
Signatures are shown shortened unless --show-signature is given.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

PROD_BASE_URL = "https://api.banglabot.xyz"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.telnyx_route", description=__doc__.split("\n\n")[0])
    parser.add_argument("target", choices=("prod", "local"), help="prod = the deployed API, local = a tunnel to this machine")
    parser.add_argument("--url", help="public https base URL (required for local, e.g. https://xyz.ngrok-free.app)")
    parser.add_argument("--dry-run", action="store_true", help="print the URLs, change nothing at Telnyx")
    parser.add_argument("--skip-check", action="store_true", help="repoint even if the server can't confirm the signature")
    parser.add_argument("--show-signature", action="store_true", help="print full URLs (they are secrets)")
    return parser.parse_args(argv)


def base_url(args: argparse.Namespace) -> str:
    from app.core.config import get_settings

    if args.target == "local":
        if not args.url:
            raise SystemExit("local needs --url https://<your tunnel>")
        base = args.url
    else:
        base = args.url or get_settings().public_base_url or PROD_BASE_URL
    base = base.strip().rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("The base URL must be https:// (Telnyx only calls public https endpoints)")
    return base


def server_accepts(inbound_url: str) -> tuple[bool, str]:
    try:
        response = httpx.get(inbound_url, timeout=10.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        return False, f"unreachable ({type(exc).__name__})"
    if response.status_code == 204:
        return True, "signature accepted"
    if response.status_code == 403:
        return False, "the server rejects this signature (different secret than this shell?)"
    return False, f"unexpected HTTP {response.status_code} (is this server running the signed routes?)"


async def repoint(url: str) -> None:
    from app.services import telnyx

    await telnyx.point_app_at(url)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from app.core.config import get_settings
    from app.services import telnyx_urls

    settings = get_settings()
    base = base_url(args)
    inbound = telnyx_urls.inbound_url(base)
    shown = (lambda url: url) if args.show_signature else telnyx_urls.mask
    print(f"TeXML app {settings.telnyx_texml_app_id or '(TELNYX_TEXML_APP_ID not set)'}")
    print(f"  voice URL        -> {shown(inbound)}  (POST)")
    print(f"  messaging profile webhook (set in the portal) -> {shown(telnyx_urls.sms_events_url(base))}")
    if not args.skip_check:
        ok, reason = server_accepts(inbound)
        print(f"  server check: {reason}")
        if not ok:
            print("Not repointed. Fix the secret / start the server, or pass --skip-check.", file=sys.stderr)
            return 2
    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0
    if not settings.telnyx_api_key or not settings.telnyx_texml_app_id:
        print("TELNYX_API_KEY and TELNYX_TEXML_APP_ID must be set.", file=sys.stderr)
        return 2
    asyncio.run(repoint(inbound))
    print("Repointed. Once every Telnyx URL is signed, set ENFORCE_WEBHOOK_SIGNATURES=true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
