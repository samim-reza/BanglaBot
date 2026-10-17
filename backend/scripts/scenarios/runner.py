"""Run one scenario through the real engine (TextSession, in-memory data) and grade it."""

from __future__ import annotations

import time
import traceback
from collections import Counter
from datetime import datetime
from datetime import time as dtime
from typing import Any

from sqlalchemy import inspect as sa_inspect

from app.flows.scheduling import slot_key
from app.verticals import flow_for
from app.voice.providers.llm import llm_for_call
from app.voice.text_session import TextSession
from app.voice.tools import NullCallStore
from scripts.scenarios.caller import HANGUP, CallerBot
from scripts.scenarios.dates import next_weekday
from scripts.scenarios.judge import judge
from scripts.scenarios.model import RunResult, Scenario, Turn
from scripts.scenarios.openai_chat import OpenAIChat
from scripts.simulate import build, context

#: An agent sentence repeated more often than this is a loop.
MAX_REPEATS = 2


def _recovery_line() -> str:
    try:
        from app.voice.languages import phrase

        return phrase("recovery", "en")
    except Exception:  # noqa: BLE001
        return ""


def slot_keys(specs: tuple[tuple[str, str, str], ...], items: list[Any], now: datetime) -> list[str]:
    """(item name, weekday, "HH:MM") → slot keys on the first such weekday after today (resource + business-wide)."""
    keys: list[str] = []
    for name, weekday, hhmm in specs:
        day = next_weekday(now, weekday)
        hour, minute = (int(part) for part in hhmm.split(":"))
        start = datetime.combine(day, dtime(hour, minute), tzinfo=now.tzinfo)
        item = next((i for i in items if name and i.name.lower() == name.lower()), None)
        keys += [slot_key(item.id if item else None, start), slot_key(None, start)]
    return keys


def apply_closures(merchant: Any, specs: tuple[tuple[str, str, str], ...], items: list[Any], now: datetime) -> None:
    """(item name or "", weekday, label) → closures on the account's settings, on the first such weekday after today."""
    if not specs:
        return
    rows = []
    for name, weekday, label in specs:
        item = next((i for i in items if name and i.name.lower() == name.lower()), None)
        day = next_weekday(now, weekday).isoformat()
        rows.append({"start": day, "end": day, "label": label, "item_id": item.id if item else ""})
    merchant.vertical_config = {**dict(merchant.vertical_config or {}), "closures": rows}


def _columns(row: Any) -> dict[str, Any]:
    """Every column of a record (items, totals, address ...) — the judge's ground truth."""
    skip = {"id", "merchant_id", "catalog_item_id", "created_at", "updated_at", "flow_data", "call_attempts"}
    try:
        keys = [attr.key for attr in sa_inspect(row).mapper.column_attrs]
    except Exception:  # noqa: BLE001 — a record written during this call (plain object)
        keys = list(vars(row))
    return {key: getattr(row, key) for key in keys if key not in skip and getattr(row, key) not in (None, "", [], {})}


_PRIVATE = ("password", "secret", "token", "key", "hash", "locks", "provider_settings")


def configured_lines(merchant: Any, direction: str) -> list[str]:
    """Every line the account's agent is configured to say (defaults + owner edits)."""
    from app.services import agent_flow_service

    try:
        described = agent_flow_service.describe(merchant)
    except Exception:  # noqa: BLE001 — verticals without a pipeline
        return []
    blueprint = ((described.get("directions") or {}).get(direction) or {}).get("blueprint") or {}
    lines: list[str] = []
    for skill in (blueprint.get("skills") or {}).values():
        for spec in skill.get("lines") or []:
            text = (spec.get("default") or {}).get("en")
            if text:
                lines.append(text)
    return lines


def business_data(merchant: Any, items: list[Any], ctx: Any) -> dict[str, Any]:
    profile = {k: v for k, v in _columns(merchant).items() if not any(p in k for p in _PRIVATE)}
    return {
        "business_profile": profile,
        "catalog": [{"kind": item.kind, "name": item.name, **dict(item.data or {})} for item in items],
        "caller_id_of_this_call": ctx.caller_number or "(none)",
        "callers_existing_records": [_columns(r) for r in ctx.caller_records],
        "outbound_record": _columns(ctx.record) if ctx.record is not None else None,
        "platform_behaviour": (
            "The agent may use the caller ID as the phone number without asking. A text (SMS) confirmation is sent "
            "after bookings/orders/messages, so 'we'll text you the details' is true. Lines listed in "
            "configured_lines are the business's own scripted wording (policies in them are real). Saved records also carry "
            "fields the system derives (lead score, serial numbers, prices and names from the catalog, 'unfinished' flags)."
            + (" E-commerce outbound calls confirm cash-on-delivery orders: every order is paid cash on delivery." if merchant.vertical == "ecommerce" else "")
        ),
        "configured_lines": configured_lines(merchant, ctx.direction),
    }


async def run_scenario(scenario: Scenario, chat: OpenAIChat, *, now: datetime | None, use_judge: bool = True) -> RunResult:
    started = time.monotonic()
    result = RunResult(scenario)
    try:
        await _converse(scenario, chat, result, now=now, use_judge=use_judge)
    except Exception as exc:  # noqa: BLE001 — a crashed scenario is a failed scenario
        result.error = f"{type(exc).__name__}: {exc}"
    result.seconds = round(time.monotonic() - started, 1)
    return result


async def _converse(scenario: Scenario, chat: OpenAIChat, result: RunResult, *, now: datetime | None, use_judge: bool) -> None:
    merchant, items, records = await build(scenario.vertical)
    record = records[scenario.record] if scenario.direction == "outbound" else None
    is_chat = scenario.channel == "chat"
    caller_number = scenario.caller
    if caller_number.startswith("@record:"):
        # Calling from an existing customer's number (their records are found by caller ID).
        caller_number = records[int(caller_number.split(":", 1)[1])].customer_phone
    ctx = context(merchant, items, records, direction=scenario.direction, record=record, caller=caller_number, chat=is_chat)
    if now is not None:
        ctx.now = now.astimezone(ctx.now.tzinfo) if ctx.now is not None else now
    for key in slot_keys(scenario.full, items, ctx.now):
        ctx.booked[key] = 999
    apply_closures(merchant, scenario.closed, items, ctx.now)
    flow = flow_for(merchant, scenario.direction)
    store = NullCallStore(taken=set(slot_keys(scenario.race, items, ctx.now)))
    llm = llm_for_call(flow_key=f"{flow.key}:scenario", merchant=merchant, channel="chat" if is_chat else "voice")
    session = TextSession(merchant=merchant, ctx=ctx, flow=flow, store=store, call_log_id="scenario", llm=llm)
    # A voice scenario plays a phone call: the agent may put the caller through (emergency offer).
    session.agent.tools.phone_call = not is_chat
    recovery = _recovery_line()
    _trace_turns(session, result)

    opening = await session.start()
    if opening:
        result.turns.append(Turn("agent", " ".join(opening)))
    else:
        result.problems.append("agent said nothing when the call started")
    caller = CallerBot(chat, business=merchant.business_name, persona=scenario.persona, channel=scenario.channel) if scenario.persona else None
    script = list(scenario.script)
    for _ in range(scenario.max_turns):
        if session.ended:
            break
        if script:
            text = script.pop(0)
        elif caller is not None:
            text = await caller.next_line(result.turns)
            if not text or HANGUP in text:
                break
        else:
            break
        result.turns.append(Turn("caller", text))
        lines = await session.say(text)
        if lines:
            result.turns.append(Turn("agent", " ".join(lines)))
            if recovery and recovery in lines:
                result.problems.append(f"agent hit an internal error after: {text[:80]!r}")
        elif not session.ended:
            result.problems.append(f"agent went silent after: {text[:80]!r}")
    caller_hung_up = not session.ended
    await session.finish()

    result.commits = list(store.commits)
    result.outcomes = list(store.outcomes)
    result.state = session.state()
    stats = llm.stats() if callable(getattr(llm, "stats", None)) else {}
    result.stats = {**stats, "fast_turns": session.agent.fast_turns, "turns": session.agent.turns}
    _check(scenario, result, caller_hung_up=caller_hung_up)
    if use_judge:
        data = business_data(merchant, items, ctx)
        result.verdict = await judge(chat, result, business=merchant.business_name, data=data, now=f"{ctx.now:%A %Y-%m-%d %H:%M %Z}")


def _trace_turns(session: TextSession, result: RunResult) -> None:
    """Keep the traceback of a turn that crashed (the session itself only speaks the recovery line)."""
    handle = session.agent.handle_turn

    async def traced(text: str) -> None:
        try:
            await handle(text)
        except Exception:
            result.problems.append("crash: " + traceback.format_exc()[-1800:])
            raise

    session.agent.handle_turn = traced


def _check(scenario: Scenario, result: RunResult, *, caller_hung_up: bool) -> None:
    expect = scenario.expect
    if expect.commit is True and not result.commits:
        result.problems.append("expected a saved record, none was saved")
    if expect.commit is False and result.commits:
        result.problems.append(f"nothing should have been saved, but saved: {[c['action'].outcome for c in result.commits]}")
    if expect.outcomes:
        final = {str(result.state.get("outcome") or "")} | {str(o.get("outcome") or "") for o in result.outcomes}
        if not final & set(expect.outcomes):
            result.problems.append(f"outcome {sorted(final - {''}) or 'none'} not in expected {list(expect.outcomes)}")
    if expect.ended is True and caller_hung_up:
        result.problems.append("the agent never ended the conversation")
    repeats = Counter(t.text for t in result.turns if t.role == "agent")
    for text, count in repeats.items():
        if count > MAX_REPEATS:
            result.problems.append(f"agent repeated itself {count}x: {text[:90]!r}")
