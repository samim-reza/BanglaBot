from app.core.config import get_settings
from app.models import OrderStatus
from app.services.call_service import _settle_from_call_status, is_machine_answer, normalize_bd_phone
from app.voice import twiml


class _Order:
    def __init__(self, status):
        self.status = status


class _Log:
    def __init__(self, outcome=""):
        self.outcome = outcome


def test_normalize_bd_phone():
    assert normalize_bd_phone("01712345678") == "+8801712345678"
    assert normalize_bd_phone("017-1234 5678") == "+8801712345678"
    assert normalize_bd_phone("8801712345678") == "+8801712345678"
    assert normalize_bd_phone("+8801712345678") == "+8801712345678"
    assert normalize_bd_phone("+1 (415) 555-0100") == "+14155550100"
    assert normalize_bd_phone("0044 20 7946 0958") == "+442079460958"


def test_settle_from_call_status():
    order = _Order(OrderStatus.calling)
    _settle_from_call_status(order, _Log(), "no-answer")
    assert order.status == OrderStatus.no_answer
    order = _Order(OrderStatus.calling)
    _settle_from_call_status(order, _Log(), "completed")
    assert order.status == OrderStatus.needs_review
    order = _Order(OrderStatus.calling)
    _settle_from_call_status(order, _Log("auto_dropped"), "completed")
    assert order.status == OrderStatus.no_answer
    order = _Order(OrderStatus.calling)
    _settle_from_call_status(order, _Log("confirmed"), "completed")
    assert order.status == OrderStatus.confirmed
    for unanswered in ("diverted", "voicemail"):
        order = _Order(OrderStatus.calling)
        _settle_from_call_status(order, _Log(unanswered), "completed")
        assert order.status == OrderStatus.no_answer  # the customer never took the call → callable again
    order = _Order(OrderStatus.confirmed)
    _settle_from_call_status(order, _Log(), "failed")
    assert order.status == OrderStatus.confirmed  # never touches a settled order


def test_stream_twiml_carries_signed_parameters(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", "https://example.ngrok-free.app")
    body = twiml.stream_twiml(order_id="o1", call_log_id="c1")
    assert 'url="wss://example.ngrok-free.app/twilio/media"' in body
    assert '<Parameter name="order_id" value="o1"/>' in body
    assert '<Parameter name="media_token" value="' in body
    assert "<Say" not in body
    assert twiml.status_callback_url("o1") == "https://example.ngrok-free.app/twilio/status/o1"
    assert "<Dial" in twiml.dial_twiml("+8801999999999", caller_id="+15550000000")


def test_public_base_url_missing_is_a_clear_error(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", None)
    try:
        twiml.stream_url()
    except twiml.PublicUrlMissing as exc:
        assert "PUBLIC_BASE_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected PublicUrlMissing")


def test_machine_answer_detection():
    assert is_machine_answer("machine_start")
    assert is_machine_answer("machine_end_beep")
    assert is_machine_answer("fax")
    assert not is_machine_answer("human")
    assert not is_machine_answer("unknown")
    assert not is_machine_answer("")
