"""Talk to an agent in the terminal — the real engine and model, no database, no phone.

Builds the demo accounts in memory (the same seed functions the app uses on
boot, run against an in-memory session), then runs a text conversation through
the exact flow / tools / fast paths / commits a phone call runs. Writes go to an
in-memory store and are printed.

    venv/bin/python -m scripts.simulate clinic                         # interactive, inbound
    venv/bin/python -m scripts.simulate clinic --say "I'd like to see a pediatrician tomorrow morning" --say "Emma Stone" ...
    venv/bin/python -m scripts.simulate clinic --direction outbound --record 0
    venv/bin/python -m scripts.simulate home_service --chat            # website-chat style

Needs OPENAI_API_KEY in .env (each turn is one gpt-5.4-mini request).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from app.core.config import get_settings
from app.db.base import new_id
from app.db import demo_accounts
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz, local_now
from app.models import CatalogItem, Merchant, Order
from app.verticals import flow_for
from app.voice.llm import ChatLLM
from app.voice.text_session import TextSession
from app.voice.tools import NullCallStore

SEEDS = {
    "ecommerce": demo_accounts.seed_shop,
    "clinic": demo_accounts.seed_clinic,
    "real_estate": demo_accounts.seed_real_estate,
    "home_service": demo_accounts.seed_home_service,
}
REF_PREFIX = {"doctor": "D", "property": "P", "service": "S"}


class MemorySession:
    """Just enough of an AsyncSession for the seed functions."""

    def __init__(self) -> None:
        self.objects: list[Any] = []

    async def scalar(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add(self, obj: Any) -> None:
        self.objects.append(obj)

    def add_all(self, objs: list[Any]) -> None:
        self.objects.extend(objs)

    async def flush(self) -> None:
        for obj in self.objects:
            if getattr(obj, "id", None) is None:
                obj.id = new_id()

    async def commit(self) -> None:
        await self.flush()


class LoggingLLM(ChatLLM):
    async def complete(self, messages, **kwargs):  # type: ignore[override]
        started = time.monotonic()
        reply = await super().complete(messages, **kwargs)
        ms = int((time.monotonic() - started) * 1000)
        usage = reply.usage or {}
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        for call in reply.tool_calls:
            print(f"      · {call.name}({call.arguments})  [{ms} ms, prompt {usage.get('prompt_tokens')} / cached {cached}]")
        if not reply.tool_calls:
            print(f"      · text reply  [{ms} ms, prompt {usage.get('prompt_tokens')} / cached {cached}]")
        return reply


async def build(vertical: str) -> tuple[Merchant, list[CatalogItem], list[Order]]:
    session = MemorySession()
    await SEEDS[vertical](session)  # type: ignore[arg-type]
    await session.flush()
    merchant = next(obj for obj in session.objects if isinstance(obj, Merchant))
    # Column defaults are applied by the database; set the ones the engine reads.
    for name, value in (("max_call_seconds", 0), ("silence_hangup_secs", 10), ("custom_greeting", ""), ("support_phone", ""), ("verify_address", bool(merchant.verify_address))):
        if getattr(merchant, name, None) is None:
            setattr(merchant, name, value)
    items = [obj for obj in session.objects if isinstance(obj, CatalogItem)]
    records = [obj for obj in session.objects if isinstance(obj, Order)]
    for record in records:
        record.call_attempts = 0
    return merchant, items, records


def context(merchant: Merchant, items: list[CatalogItem], records: list[Order], *, direction: str, record: Order | None, caller: str, chat: bool) -> CallContext:
    catalog = [
        CatalogEntry(id=item.id, ref=f"{REF_PREFIX.get(item.kind, 'I')}{index}", kind=item.kind, name=item.name, data=dict(item.data or {}))
        for index, item in enumerate(items, start=1)
    ]
    booked: dict[str, int] = {}
    for row in records:
        if row.scheduled_at is not None:
            for key in {slot_key(row.catalog_item_id, row.scheduled_at), slot_key(None, row.scheduled_at)}:
                booked[key] = booked.get(key, 0) + 1
    digits = "".join(ch for ch in caller if ch.isdigit())
    callers = [row for row in records if digits and "".join(ch for ch in row.customer_phone if ch.isdigit()).endswith(digits[-10:])]
    return CallContext(
        merchant=merchant,
        record=record,
        direction=direction,
        caller_number=caller,
        catalog=catalog,
        booked=booked,
        caller_records=callers if direction == DIRECTION_INBOUND else [],
        now=local_now(business_tz(merchant.timezone)),
        test=True,
        channel="chat" if chat else "voice",
    )


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.openai_api_key:
        print("OPENAI_API_KEY is not set (.env)")
        return 2
    merchant, items, records = await build(args.vertical)
    if args.language:
        merchant.language = args.language
    record = records[args.record] if args.direction == "outbound" else None
    ctx = context(merchant, items, records, direction=args.direction, record=record, caller=args.caller, chat=args.chat)
    flow = flow_for(merchant, args.direction)
    store = NullCallStore(taken=set(args.taken or []))
    llm = LoggingLLM(
        api_key=settings.openai_api_key,
        model=settings.openai_llm_model,
        reasoning_effort=settings.openai_llm_reasoning_effort,
        max_output_tokens=settings.openai_llm_max_output_tokens,
        prompt_cache_key=f"{flow.key}:sim",
    )
    session = TextSession(merchant=merchant, ctx=ctx, flow=flow, store=store, call_log_id="sim", llm=llm)
    print(f"== {merchant.business_name} · {flow.key} · {ctx.now:%a %Y-%m-%d %H:%M %Z} ==")
    for line in await session.start():
        print(f"AGENT: {line}")
    turns = list(args.say or [])
    while not session.ended:
        if turns:
            text = turns.pop(0)
            print(f"\nCALLER: {text}")
        elif args.say is not None and not args.interactive:
            break
        else:
            try:
                text = input("\nYOU: ").strip()
            except EOFError:
                break
            if not text:
                continue
        started = time.monotonic()
        for line in await session.say(text):
            print(f"AGENT: {line}")
        print(f"      ({int((time.monotonic() - started) * 1000)} ms, stage → {session.agent.runtime.stage})")
    await session.finish()
    print("\n== result ==")
    print(json.dumps(session.state(), indent=2, default=str, ensure_ascii=False))
    for commit in store.commits:
        action = commit["action"]
        print(f"COMMIT {action.outcome} → status {action.status}, record {commit['record_id']}")
        print(json.dumps({**action.fields, "capacity": action.capacity}, indent=2, default=str, ensure_ascii=False))
    for outcome in store.outcomes:
        if "action" not in outcome:
            print(f"OUTCOME {outcome.get('outcome')} → {outcome.get('status')} {outcome.get('note') or ''}")
    stats = llm.stats()
    print(f"LLM: {stats['requests']} requests, {stats['prompt_tokens']} prompt tokens ({stats['cached_prompt_tokens']} cached), {stats['completion_tokens']} completion; fast-path turns {session.agent.fast_turns}/{session.agent.turns}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vertical", choices=sorted(SEEDS))
    parser.add_argument("--direction", choices=["inbound", "outbound"], default="inbound")
    parser.add_argument("--record", type=int, default=0, help="index of the demo record to call (outbound)")
    parser.add_argument("--caller", default="", help="pretend caller number (inbound)")
    parser.add_argument("--say", action="append", help="scripted caller turn (repeatable)")
    parser.add_argument("--interactive", action="store_true", help="continue interactively after the scripted turns")
    parser.add_argument("--chat", action="store_true", help="website-chat channel instead of a phone call")
    parser.add_argument("--language", choices=["en", "bn"])
    parser.add_argument("--taken", action="append", help="slot key that is already booked (forces a conflict)")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
