"""The main conversation engine — pure logic, no I/O, no network.

- ``base``       — the ``Flow`` contract every business engine implements, outcomes, commits
- ``context``    — ``CallContext``: merchant, record, caller, catalog snapshot, clock
- ``runtime``    — per-call slot store that derives the current stage / node
- ``steps``      — shared machinery for slot-filling business flows (read-back → commit)
- ``scheduling`` — sessions, slots, serial numbers, free capacity
- ``timefmt``    — dates and times as callers say and hear them (Bangla / English)
- ``hearing``    — did the caller's own words actually support an outcome?

The business engines themselves live in ``app.verticals``.
"""

from app.flows.base import CommitAction, CommitResult, Flow, Instruction, Terminal
from app.flows.context import CallContext, CatalogEntry
from app.flows.runtime import FlowRuntime

__all__ = ["CallContext", "CatalogEntry", "CommitAction", "CommitResult", "Flow", "FlowRuntime", "Instruction", "Terminal"]
