"""HTTP-level checks that need no database (the app's lifespan is never started)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes import public
from app.main import app
from app.schemas.admin import MerchantCreate
from app.schemas.merchant import MerchantSettingsUpdate


@pytest.fixture
def client() -> TestClient:
    # No `with`: the lifespan (database bootstrap) does not run.
    return TestClient(app)


def test_widget_script_is_public_and_cross_origin(client):
    response = client.get("/api/public/widget.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["access-control-allow-origin"] == "*"
    assert "data-key" in response.text


def test_widget_config_for_an_unknown_or_disabled_key(client, monkeypatch):
    async def none(key):
        return None

    monkeypatch.setattr(public, "_widget_merchant", none)
    response = client.get("/api/public/widget/nope/config")
    assert response.json() == {"enabled": False}
    response = client.post("/api/public/widget/nope/start", content="{}")
    assert response.status_code == 404 and response.headers["access-control-allow-origin"] == "*"


def test_widget_config_uses_the_account_look(client, monkeypatch):
    async def merchant(key):
        return SimpleNamespace(business_name="CityCare", widget_settings={"color": "#123456", "position": "left"})

    monkeypatch.setattr(public, "_widget_merchant", merchant)
    body = client.get("/api/public/widget/k/config").json()
    assert body == {"enabled": True, "title": "CityCare", "subtitle": "", "color": "#123456", "position": "left"}


def test_contact_form_honeypot_is_silently_accepted(client):
    # A bot filled the hidden field: 201 without touching the database.
    response = client.post("/api/public/contact", json={"name": "Bot", "email": "x@y.z", "website": "spam.example"})
    assert response.status_code == 201 and response.json() == {"ok": True}


def test_portal_routes_require_a_login(client):
    for path in ("/api/auth/workspace", "/api/catalog", "/api/calls", "/api/orders", "/api/integrations", "/api/integrations/messages"):
        assert client.get(path).status_code == 401
    assert client.patch("/api/integrations/sms", json={"enabled": True}).status_code == 401
    assert client.post("/api/integrations/sms/test", json={"to": "+15550100"}).status_code == 401
    assert client.get("/api/integrations/google/connect").status_code == 401
    assert client.post("/api/agent/chat", json={"direction": "inbound"}).status_code == 401
    assert client.get("/api/admin/meta").status_code == 401


def test_google_callback_rejects_a_denied_or_forged_consent(client):
    from app.db.session import get_db

    async def no_db():
        yield None  # never reached for a denied or forged callback

    app.dependency_overrides[get_db] = no_db
    try:
        denied = client.get("/api/integrations/google/callback?error=access_denied", follow_redirects=False)
        assert denied.status_code in (302, 307) and denied.headers["location"].endswith("/addons?google=denied#calendar")
        forged = client.get("/api/integrations/google/callback?code=c&state=forged", follow_redirects=False)
        assert forged.headers["location"].endswith("/addons?google=expired#calendar")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_settings_validation():
    data = MerchantSettingsUpdate(widget_settings={"title": "  Hi  ", "color": "#0f766e", "position": "LEFT"}, currency="gbp", emergency_number="9-9-9")
    assert data.widget_settings == {"title": "Hi", "color": "#0f766e", "position": "left"}
    assert data.currency == "GBP" and data.emergency_number == "999"
    with pytest.raises(ValidationError):
        MerchantSettingsUpdate(widget_settings={"color": "red"})
    with pytest.raises(ValidationError):
        MerchantSettingsUpdate(webhook_url="ftp://example.com")
    with pytest.raises(ValidationError):
        MerchantSettingsUpdate(timezone="Mars/Olympus")


def test_account_creation_validates_engine_and_region():
    created = MerchantCreate(business_name="X", username="clinic_two", password="secret1", vertical="Clinic", region="gb")
    assert created.vertical == "clinic" and created.region == "GB" and created.language == "en"
    with pytest.raises(ValidationError):
        MerchantCreate(business_name="X", username="x_y", password="secret1", vertical="restaurant")
