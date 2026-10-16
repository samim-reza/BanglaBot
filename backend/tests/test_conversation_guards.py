"""Conversation guards found by the live scenario suite (scripts/scenarios), pinned as unit tests.

- garbled words never trigger a transfer; they get a re-ask
- after a booking the call stays open ("anything else?"): done → goodbye, new details → the same record is updated
- a detail the caller refuses is explained once, then skipped (no endless loop)
- placeholder names ("caller") are never saved as the person's name
- a "yes" that repeats a known detail confirms the read-back instead of reading it again
"""

from __future__ import annotations

import pytest

from app.flows import hearing
from tests.test_verticals import _clinic, _tools

BOOK = {"intent": "book", "doctor": "D2", "date": "2026-10-07", "time_pref": "morning"}


async def _booked(caller: str = "+16175550100"):
    tools, runtime, store = _tools(_clinic(caller_number=caller))
    await tools.execute("save_details", dict(BOOK), caller_text="the children's doctor on Wednesday morning")
    await tools.execute("save_details", {"patient_name": "Leo Carter"}, caller_text="Leo Carter")
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes please")
    return tools, runtime, store, result


@pytest.mark.asyncio
async def test_garbled_words_get_a_reask_not_a_transfer():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    result = await tools.execute("transfer_to_human", {"reason": "unclear"}, caller_text="asdf qwer zxcv")
    assert result.say and not result.hang_up and not result.transfer_to and not tools.outcome
    assert result.say.startswith("Sorry")
    # A real request for a person still transfers (here: a callback, no support line set).
    result = await tools.execute("transfer_to_human", {}, caller_text="can I talk to a real person please")
    assert result.hang_up and tools.outcome == "transfer"


@pytest.mark.asyncio
async def test_after_booking_the_call_stays_open_until_the_caller_is_done():
    tools, runtime, store, result = await _booked()
    assert result.outcome == "booked" and not result.hang_up
    assert result.say.endswith("Is there anything else I can help you with?")
    assert runtime.stage == "intent" and tools.completed == ["booked"]
    done = await tools.execute("end_call", {}, caller_text="no thanks, that's all")
    assert done.hang_up and done.outcome == "booked" and "goodbye" in done.say.lower()
    assert len(store.commits) == 1


@pytest.mark.asyncio
async def test_new_details_after_booking_update_the_same_record():
    tools, runtime, store, _ = await _booked()
    first = store.commits[0]["record_id"]
    result = await tools.execute("save_details", {"date": "2026-10-09"}, caller_text="actually can you move it to Friday")
    assert runtime.stage == "confirm" and "Friday" in result.say
    result = await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert len(store.commits) == 2
    amended = store.commits[1]["action"]
    assert amended.record_id == first and amended.outcome == "rescheduled"
    assert amended.fields["scheduled_at"].day == 9 and amended.fields["customer_name"] == "Leo Carter"


@pytest.mark.asyncio
async def test_another_request_after_booking_is_a_new_record():
    tools, runtime, store, _ = await _booked()
    await tools.execute("save_details", {**BOOK, "date": "2026-10-09", "patient_name": "Mia Carter"}, caller_text="and one for my daughter Mia on Friday morning")
    await tools.execute("save_details", {"confirmed": True}, caller_text="yes")
    assert len(store.commits) == 2 and not store.commits[1]["action"].record_id
    assert store.commits[1]["action"].fields["customer_name"] == "Mia Carter"


@pytest.mark.asyncio
async def test_a_refused_detail_is_explained_once_then_skipped():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    await tools.execute("save_details", dict(BOOK), caller_text="the children's doctor on Wednesday morning")
    assert runtime.stage == "patient_name"
    first = await tools.declined("patient_name")
    assert "No problem" in first.say and runtime.stage == "patient_name"
    second = await tools.declined("patient_name")
    assert runtime.stage == "confirm" and "go ahead without it" in second.say
    assert "for you" in second.say or "for ," not in second.say


@pytest.mark.asyncio
async def test_placeholder_names_are_not_saved():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    await tools.execute("save_details", {**BOOK, "patient_name": "caller"}, caller_text="the children's doctor on Wednesday morning")
    assert "patient_name" not in runtime.slots and runtime.stage == "patient_name"


@pytest.mark.asyncio
async def test_a_yes_that_repeats_known_details_confirms():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    await tools.execute("save_details", dict(BOOK), caller_text="the children's doctor on Wednesday morning")
    await tools.execute("save_details", {"patient_name": "Leo Carter"}, caller_text="Leo Carter")
    assert runtime.stage == "confirm"
    result = await tools.execute(
        "save_details", {"confirmed": True, "patient_name": "Leo Carter", "phone": "+16175550100"},
        caller_text="Yes, book it. It's Leo Carter and my number is 617 555 0100",
    )
    assert result.outcome == "booked"


def test_hearing_tells_done_goodbye_refusal_and_human_apart():
    assert hearing.is_done("no thanks, that's all") and not hearing.is_done("no but can I change the time to Thursday?")
    assert hearing.says_goodbye("Thanks, that's all I needed — goodbye") and not hearing.says_goodbye("I'll stop by next week")
    assert hearing.declines_detail("I'd rather not say") and not hearing.declines_detail("Leo Carter")
    assert hearing.asks_for_human("can I speak to the manager") and not hearing.asks_for_human("asdf qwer zxcv")


@pytest.mark.asyncio
async def test_moving_a_booking_never_counts_its_own_slot_as_taken():
    tools, runtime, store, _ = await _booked()
    first = store.commits[0]["action"].fields["scheduled_at"]
    # Same day, the caller names the very time they already hold: that is theirs, not "taken".
    result = await tools.execute("save_details", {"date": first.date().isoformat(), "time_pref": first.strftime("%H:%M")}, caller_text="actually keep the day but can you move it to that same time")
    assert "isn't free" not in result.say


@pytest.mark.asyncio
async def test_a_yes_with_a_change_reads_the_new_summary_back():
    tools, runtime, store = _tools(_clinic(caller_number="+16175550100"))
    await tools.execute("save_details", dict(BOOK), caller_text="the children's doctor on Wednesday morning")
    await tools.execute("save_details", {"patient_name": "Leo Carter"}, caller_text="Leo Carter")
    result = await tools.execute(
        "save_details", {"confirmed": True, "date": "2026-10-09"}, caller_text="Yes, book it. Actually, make it Friday instead."
    )
    assert runtime.stage == "confirm" and "yes or no" not in result.say.lower() and "Friday" in result.say


def test_preferences_are_not_refusals():
    assert not hearing.declines_detail("Actually, I'd rather have it delivered to my address")
    assert hearing.declines_detail("I'd rather get the valuation first before naming a number")
