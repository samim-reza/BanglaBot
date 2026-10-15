"""Swappable speech-to-text, text-to-speech and LLM providers.

Every provider implements one of the protocols in :mod:`.base`; which one a
call uses is decided by an ordered *chain* (``settings.py``) so a provider that
is down, out of free quota or rate-limited falls through to the next one.
"""
