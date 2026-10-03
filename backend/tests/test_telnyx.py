"""Telnyx helpers that need no network: webhook signatures, call-id storage, sender config."""

import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core.config import get_settings
from app.services import sms_service, telnyx


def _keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, base64.b64encode(public).decode()


def test_signature_round_trip(monkeypatch):
    private, public_b64 = _keypair()
    monkeypatch.setattr(get_settings(), "telnyx_public_key", public_b64)
    body = b"CallSid=v3%3Aabc&CallStatus=completed"
    stamp = str(int(time.time()))
    signature = base64.b64encode(private.sign(stamp.encode() + b"|" + body)).decode()
    assert telnyx.verify_signature(body, signature, stamp)
    assert not telnyx.verify_signature(body + b"x", signature, stamp)
    assert not telnyx.verify_signature(body, signature, str(int(time.time()) - 3600))  # replayed
    assert not telnyx.verify_signature(body, "not-base64!", stamp)
    assert not telnyx.verify_signature(body, signature, "")


def test_signature_needs_a_public_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "telnyx_public_key", None)
    assert not telnyx.verify_signature(b"x", "c2ln", str(int(time.time())))


def test_sid_key_fits_the_column():
    long_sid = "v3:" + "A" * 100
    assert len(telnyx.sid_key(long_sid)) == telnyx.SID_COLUMN_WIDTH
    assert telnyx.sid_key("v3:short") == "v3:short"
    assert telnyx.sid_key(None) == ""


def test_account_sid_is_learned_unless_pinned(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(telnyx, "_learned_account_sid", None)
    monkeypatch.setattr(settings, "telnyx_account_sid", None)
    telnyx.remember_account_sid("")
    assert telnyx.account_sid() is None
    telnyx.remember_account_sid("user-123")
    assert telnyx.account_sid() == "user-123"
    monkeypatch.setattr(settings, "telnyx_account_sid", "pinned")
    telnyx.remember_account_sid("other")
    assert telnyx.account_sid() == "pinned"


def test_sms_ready_needs_key_and_sender(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(settings, "telnyx_api_key", "KEY_test")
    monkeypatch.setattr(settings, "telnyx_sms_from", None)
    monkeypatch.setattr(settings, "telnyx_from_number", None)
    assert not sms_service.platform_ready()
    monkeypatch.setattr(settings, "telnyx_from_number", "+18723428160")
    assert sms_service.platform_ready()
    monkeypatch.setattr(settings, "telnyx_api_key", None)
    assert not sms_service.platform_ready()


def test_telnyx_receipt_statuses_map_to_ours():
    assert sms_service.TELNYX_STATUS["delivered"] == "delivered"
    assert sms_service.TELNYX_STATUS["sending_failed"] == "failed"
    assert sms_service.TELNYX_STATUS["delivery_failed"] == "undelivered"
    assert sms_service.TELNYX_STATUS["sending"] == "sent"


def test_each_account_calls_and_texts_from_its_own_number(monkeypatch):
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.services import telnyx as telnyx_service

    monkeypatch.setattr(get_settings(), "telnyx_from_number", "+18723428160")
    home = SimpleNamespace(inbound_number="(312) 555-0188", region="US")
    assert telnyx_service.number_for(home) == "+13125550188"
    assert telnyx_service.number_for(SimpleNamespace(inbound_number="", region="US")) == "+18723428160"
