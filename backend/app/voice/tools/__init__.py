"""The tools the model may call during a call, and what they do.

* ``save_details``      → validated by the flow, stored in the runtime. When the
                          next line is backend-owned (verbatim) the tool result
                          carries it as ``say`` and the turn ends — the model's
                          optional ``reply`` (an answer to a side question) is
                          spoken first. One model round-trip per caller turn.
                          Reaching the *commit* stage writes the result through
                          the store (booking with a capacity re-check, record
                          update) and speaks the closing line.
* terminals             → flow-specific call-ending tools (``confirm_order``,
                          ``report_emergency``, …), gated by :mod:`app.flows.hearing`:
                          an outcome is only committed when the caller's own
                          words support it; otherwise the backend re-asks
                          (twice), then settles as ``needs_review`` / ``unclear``.
* ``transfer_to_human`` → ``needs_review`` / ``transfer``; the bridge dials the
                          business's support line after the transfer line.
* ``end_call``          → settles relay / wrong number / "call me later" /
                          inquiry, speaks the matching closing line, hangs up.

Persistence goes through a small ``CallStore`` so calls can be driven in tests
(and the text simulator) without a database.
"""

from app.voice.tools.core import CallTools
from app.voice.tools.store import CallStore, NullCallStore, ToolResult
from app.voice.tools.text import END_CALL, REPLY_FIELD, SAVE_DETAILS, TRANSFER_TO_HUMAN, answer_only

__all__ = ["END_CALL", "REPLY_FIELD", "SAVE_DETAILS", "TRANSFER_TO_HUMAN", "CallStore", "CallTools", "NullCallStore", "ToolResult", "answer_only"]
