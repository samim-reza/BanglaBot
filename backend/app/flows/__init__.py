"""Pure conversation logic for confirmation calls (no I/O, no network).

- ``base``      — stage/node vocabulary, the ``Flow`` contract, scripted lines
- ``ecommerce`` — the order-confirmation flow (identity → address → decision)
- ``runtime``   — per-call slot store that derives the current node
- ``hearing``   — did the caller's own words actually support an outcome?
"""

from app.flows.base import Flow, Instruction, Terminal
from app.flows.ecommerce import EcommerceFlow, flow_preview_steps
from app.flows.runtime import FlowRuntime

__all__ = ["EcommerceFlow", "Flow", "FlowRuntime", "Instruction", "Terminal", "flow_preview_steps"]
