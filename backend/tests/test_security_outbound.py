"""SSRF guard for owner-typed URLs (webhook endpoint, iCal links): address rules, DNS
pinning (rebinding), redirects, body caps, and the routes / services that use it.
DNS is a fake resolver and HTTP an ``httpx.MockTransport`` — nothing leaves the process."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.ratelimit import backends
from app.core.security import boot_guard, issue_merchant_token, outbound
from app.db.session import get_db
from app.main import app
from app.schemas.merchant import MerchantSettingsUpdate
from app.services import webhook_service
from tests.security_fakes import FakeDB, db_override, make_merchant

PUBLIC_IP = "93.184.216.34"


class Net:
    """Fake DNS answers per host + a transport recording what was actually sent."""

    def __init__(self, answers: dict[str, list[str]], handler=None) -> None:
        self.answers = answers
        self.lookups: list[str] = []
        self.sent: list[httpx.Request] = []
        self.handler = handler or (lambda request: httpx.Response(200, text="ok"))

    async def resolve(self, host: str, port: int) -> list[str]:
        self.lookups.append(host)
        answer = self.answers.get(host)
        if answer is None:
            raise OSError("NXDOMAIN")
        return answer.pop(0) if answer and isinstance(answer[0], list) else answer

    def transport(self) -> httpx.MockTransport:
        def record(request: httpx.Request) -> httpx.Response:
            self.sent.append(request)
            return self.handler(request)

        return httpx.MockTransport(record)


@pytest.fixture
def net(monkeypatch):
    def install(answers: dict, handler=None) -> Net:
        fake = Net(answers, handler)
        monkeypatch.setattr(outbound, "resolver", fake.resolve)
        monkeypatch.setattr(outbound, "transport", fake.transport())
        return fake

    monkeypatch.setattr(get_settings(), "outbound_allow_private", False)
    return install


# ------------------------------------------------------------------ address rules
@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.1.2.3", "172.16.0.9", "172.31.255.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
     "224.0.0.1", "255.255.255.255", "198.18.0.1", "::1", "::", "fc00::1", "fd12:3456::1", "fe80::1", "::ffff:127.0.0.1",
     "::ffff:169.254.169.254", "64:ff9b::7f00:1", "2002:7f00:1::1", "fe80::1%eth0", "not-an-ip"],
)
def test_internal_addresses_are_not_public(ip):
    assert not outbound.is_public_ip(ip)


@pytest.mark.parametrize("ip", [PUBLIC_IP, "8.8.8.8", "2606:4700::1111"])
def test_public_addresses_are_public(ip):
    assert outbound.is_public_ip(ip)


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "file:///etc/passwd", "gopher://example.com/", "javascript:alert(1)", "http://localhost:8000/",
     "http://LOCALHOST./", "http://api.internal/x", "http://printer.local/", "http://metadata.google.internal/computeMetadata/v1/",
     "http://127.1/", "http://2130706433/", "http://0x7f000001/", "http://user:pass@example.com/", "http://[::1]/",
     "http://[fc00::1]/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1:6379/", "http://intranet/", ""],
)
def test_check_url_refuses_internal_and_odd_urls(net, url):
    with pytest.raises(outbound.UnsafeURLError):
        outbound.check_url(url)


def test_check_url_accepts_public_names_and_the_dev_override(monkeypatch):
    assert outbound.check_url("https://calendar.google.com/calendar/ical/x/basic.ics").host == "calendar.google.com"
    monkeypatch.setattr(get_settings(), "outbound_allow_private", True)
    assert outbound.check_url("http://localhost:5000/hook").host == "localhost"


async def test_every_dns_answer_must_be_public(net):
    net({"mixed.example.com": [PUBLIC_IP, "10.0.0.5"], "empty.example.com": [], "inside.example.com": ["169.254.169.254"]})
    for host in ("mixed.example.com", "empty.example.com", "inside.example.com", "missing.example.com"):
        with pytest.raises(outbound.UnsafeURLError):
            await outbound.resolve_public(host, 443)


# ------------------------------------------------------------------ pinning, redirects, caps
async def test_request_connects_to_the_vetted_address_with_host_and_sni(net):
    fake = net({"hooks.example.com": [PUBLIC_IP]})
    response = await outbound.request("POST", "https://hooks.example.com:8443/in?x=1", content=b"{}")
    assert response.status_code == 200 and response.text == "ok"
    sent = fake.sent[0]
    assert sent.url.host == PUBLIC_IP and sent.url.port == 8443 and sent.url.path == "/in" and sent.url.query == b"x=1"
    assert sent.headers["host"] == "hooks.example.com:8443" and sent.extensions["sni_hostname"] == "hooks.example.com"


async def test_dns_rebinding_cannot_reach_an_internal_address(net):
    # First answer public (the request goes there), the next one internal (refused).
    fake = net({"rebind.example.com": [[PUBLIC_IP], ["127.0.0.1"]]})
    await outbound.request("GET", "http://rebind.example.com/cal.ics")
    with pytest.raises(outbound.UnsafeURLError):
        await outbound.request("GET", "http://rebind.example.com/cal.ics")
    assert [request.url.host for request in fake.sent] == [PUBLIC_IP]


async def test_redirects_are_rechecked_hop_by_hop(net):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/to-metadata":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        if request.url.path == "/loop":
            return httpx.Response(301, headers={"Location": "/loop"})
        if request.url.path == "/moved":
            return httpx.Response(301, headers={"Location": "https://cdn.example.com/final.ics"})
        return httpx.Response(200, text="BEGIN:VCALENDAR")

    fake = net({"cal.example.com": [PUBLIC_IP], "cdn.example.com": ["8.8.8.8"]}, handler)
    with pytest.raises(outbound.UnsafeURLError):
        await outbound.request("GET", "https://cal.example.com/to-metadata", follow_redirects=True)
    with pytest.raises(outbound.UnsafeURLError, match="redirects"):
        await outbound.request("GET", "https://cal.example.com/loop", follow_redirects=True)
    final = await outbound.request("GET", "https://cal.example.com/moved", follow_redirects=True)
    assert final.text == "BEGIN:VCALENDAR" and fake.sent[-1].headers["host"] == "cdn.example.com"
    # Webhooks never follow: the 302 is the answer.
    assert (await outbound.request("POST", "https://cal.example.com/to-metadata")).status_code == 302
    assert all(request.url.host != "169.254.169.254" for request in fake.sent)


async def test_bodies_are_capped_while_streaming(net):
    net({"big.example.com": [PUBLIC_IP]}, lambda request: httpx.Response(200, content=b"x" * 50_000))
    with pytest.raises(outbound.UnsafeURLError, match="too large"):
        await outbound.request("GET", "https://big.example.com/huge.ics", max_bytes=10_000)
    assert len((await outbound.request("GET", "https://big.example.com/huge.ics", max_bytes=60_000)).content) == 50_000


def test_owner_facing_errors_are_generic():
    assert outbound.describe_error(httpx.ConnectError("[Errno 111] Connection refused to 10.0.0.7:6379")) == "Couldn't reach that address"
    assert outbound.describe_error(httpx.ReadTimeout("timed out")) == "The address took too long to answer"
    assert outbound.describe_error(outbound.UnsafeURLError("That address points to a private network")).endswith("private network")


# ------------------------------------------------------------------ webhook service + routes
async def test_webhook_events_are_signed_and_guarded(net):
    fake = net({"hooks.example.com": [PUBLIC_IP]})
    merchant = make_merchant(webhook_url="https://hooks.example.com/callisa", plan="growth")
    merchant.webhook_secret = "s" * 48
    result = await webhook_service.send_test_event(merchant)
    assert result == {"ok": True, "status": 200}
    sent = fake.sent[0]
    assert sent.headers["x-agent-signature"] == webhook_service.sign("s" * 48, sent.content)
    assert json.loads(sent.content)["event"] == "test"
    merchant.webhook_url = "http://10.0.0.1/admin"
    blocked = await webhook_service.send_test_event(merchant)
    assert blocked == {"ok": False, "error": "That address points to a private network"} and len(fake.sent) == 1


def test_private_webhook_urls_are_refused_when_saved():
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/latest", "http://localhost/hook", "http://[::1]/"):
        with pytest.raises(ValidationError):
            MerchantSettingsUpdate(webhook_url=url)
    assert MerchantSettingsUpdate(webhook_url="https://hooks.example.com/x").webhook_url == "https://hooks.example.com/x"


@pytest.fixture
def owner():
    backends.memory.reset()
    merchant = make_merchant()
    app.dependency_overrides[get_db] = db_override(FakeDB(merchant))
    yield TestClient(app), {"Authorization": f"Bearer {issue_merchant_token(merchant)}"}
    app.dependency_overrides.pop(get_db, None)


def test_calendar_check_is_no_internal_network_probe(net, owner):
    client, headers = owner

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 111] Connection refused")

    fake = net({"cal.example.com": [PUBLIC_IP]}, refuse)
    internal = client.post("/api/integrations/calendar/check", json={"url": "http://169.254.169.254/latest/meta-data/"}, headers=headers)
    assert internal.json() == {"ok": False, "error": "calendar link: That address points to a private network"}
    down = client.post("/api/integrations/calendar/check", json={"url": "webcal://cal.example.com/a.ics"}, headers=headers)
    assert down.json() == {"ok": False, "error": "Couldn't reach that address"}
    assert [request.url.host for request in fake.sent] == [PUBLIC_IP]
    saved = client.patch("/api/integrations/calendar", json={"busy_ics_urls": ["http://192.168.0.10/cal.ics"]}, headers=headers)
    assert saved.status_code == 422


def test_production_refuses_the_private_outbound_override():
    production = SimpleNamespace(
        environment="production", admin_token_secret="x" * 40, admin_password="a-strong-admin-passphrase", admin_username="ops",
        encryption_secret="e" * 40, telnyx_webhook_secret=None, outbound_allow_private=True,
    )
    assert any("OUTBOUND_ALLOW_PRIVATE" in problem for problem in boot_guard.check_settings(production))
    production.outbound_allow_private = False
    assert boot_guard.check_settings(production) == []
