"""Inbound reception: answer from the business facts, or take a message for a callback.

Used for inbound calls of a vertical without an inbound engine of its own
(e-commerce). Runs on the skill pipeline (``blueprint.py``, wired by the vertical
that uses it) unless ``PIPELINE_VERTICALS`` leaves that vertical out, in which
case the legacy hand-written flow (``legacy.py``) is used.

This top level stays light — the skill library imports the contact helpers from
here — so the pipeline modules are imported explicitly where needed.
"""

from __future__ import annotations

from app.verticals.reception.contact import PHONE_HINT, caller_phone, clean_phone
from app.verticals.reception.legacy import ReceptionFlow

__all__ = ["PHONE_HINT", "ReceptionFlow", "caller_phone", "clean_phone"]
