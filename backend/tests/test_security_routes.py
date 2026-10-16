"""Route inventory: every route is either deliberately public (allow-listed below, with
the control that protects it) or behind the right sign-in; admin routes carry the roles
the console's role model promises (finance reads, support edits accounts, superadmin
does everything). No database: ``get_db`` is a ``FakeDB``.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from app.api.deps import AdminGuard, get_current_merchant
from app.core.config import get_settings
from app.core.ratelimit import backends
from app.core.security import boot_guard, issue_admin_token, issue_merchant_token, sign_media_stream_token, sign_token
from app.core.security.tokens import TYP_GOOGLE_OAUTH, TYP_PAY, TYP_VERIFY
from app.db.session import get_db
from app.main import app
from app.models import AdminUser
from tests.security_fakes import FakeDB, db_override, make_merchant

#: (method, path) → why it needs no session.
PUBLIC = {
    ("GET", "/health"): "status words only",
    ("GET", "/api/public/catalog"): "website data",
    ("POST", "/api/public/signup/quote"): "rate limited, no writes",
    ("POST", "/api/public/signup"): "honeypot + per-IP / per-email limits",
    ("POST", "/api/public/signup/verify-email"): "hashed single-purpose token, rate limited",
    ("GET", "/api/public/signup/status"): "unguessable reference, rate limited",
    ("POST", "/api/public/contact"): "honeypot + rate limit",
    ("GET", "/api/public/calendar/{token}.ics"): "secret feed token (hashed lookup)",
    ("GET", "/api/public/widget.js"): "static script",
    ("GET", "/api/public/widget/{key}/config"): "embed key, rate limited",
    ("POST", "/api/public/widget/{key}/start"): "embed key, per-IP + per-site limits",
    ("POST", "/api/public/widget/{key}/say"): "session id bound to the embed key, turn cap",
    ("POST", "/api/auth/login"): "lockout",
    ("POST", "/api/admin/login"): "lockout + TOTP",
    ("GET", "/api/integrations/google/callback"): "signed OAuth state (typ google_oauth)",
    ("GET", "/api/meta/webhook"): "verify token (constant time)",
    ("POST", "/api/meta/webhook"): "X-Hub-Signature-256",
    ("GET", "/api/public/pay/{token}"): "signed pay token",
    ("POST", "/api/public/pay/{token}/complete"): "signed pay token, dummy provider only",
    ("POST", "/api/payments/stripe/webhook"): "Stripe-Signature",
    ("POST", "/twilio/whatsapp"): "X-Twilio-Signature (refused in production without a token)",
}
#: Telnyx can't send a bearer token: signed URL paths (unsigned refused in production) / media token.
TELNYX_PREFIX = "/telnyx/"
#: Admin writes any role may make: the admin's own account only.
OWN_ACCOUNT = re.compile(r"^/api/admin/users/me(/|$)")
SUPPORT_EDITS = {"superadmin", "support"}
EXPECTED_ROLES = {
    ("POST", "/api/admin/merchants"): SUPPORT_EDITS,
    ("PATCH", "/api/admin/merchants/{merchant_id}"): SUPPORT_EDITS,
    ("DELETE", "/api/admin/merchants/{merchant_id}"): {"superadmin"},
    ("PUT", "/api/admin/merchants/{merchant_id}/addons"): SUPPORT_EDITS,
    ("POST", "/api/admin/addon-requests/{request_id}/{decision}"): SUPPORT_EDITS,
    ("PATCH", "/api/admin/inquiries/{inquiry_id}"): SUPPORT_EDITS,
    ("DELETE", "/api/admin/inquiries/{inquiry_id}"): SUPPORT_EDITS,
    ("POST", "/api/admin/merchants/{merchant_id}/impersonate"): SUPPORT_EDITS,
    ("GET", "/api/admin/users"): {"superadmin"},
    ("POST", "/api/admin/users"): {"superadmin"},
    ("PUT", "/api/admin/plans/catalog"): {"superadmin"},
    ("PUT", "/api/admin/merchants/{merchant_id}/providers"): {"superadmin"},
    ("PUT", "/api/admin/merchants/{merchant_id}/agent-flow-locks"): {"superadmin"},
    ("GET", "/api/admin/finance/overview"): {"superadmin", "finance"},
    ("GET", "/api/admin/finance/export.csv"): {"superadmin", "finance"},
    ("GET", "/api/admin/audit"): SUPPORT_EDITS,
}


def _guards(route) -> tuple[bool, list[tuple[str, ...]]]:
    merchant, admin = False, []

    def walk(dependant) -> None:
        nonlocal merchant
        for sub in dependant.dependencies:
            if sub.call is get_current_merchant:
                merchant = True
            if isinstance(sub.call, AdminGuard):
                admin.append(sub.call.roles)
            walk(sub)

    walk(route.dependant)
    return merchant, admin


def _routes() -> list[tuple[str, str, bool, list[tuple[str, ...]]]]:
    out = []
    for route in app.routes:
        if isinstance(route, APIWebSocketRoute):
            out.append(("WS", route.path, *_guards(route)))
        elif isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                out.append((method, route.path, *_guards(route)))
    return out


ROUTES = _routes()
PROTECTED = [(m, p, merchant, admin) for m, p, merchant, admin in ROUTES if (merchant or admin) and m != "WS"]


@pytest.fixture(autouse=True)
def _isolated():
    backends.memory.reset()
    app.dependency_overrides[get_db] = db_override(FakeDB(make_merchant(), *ADMINS.values()))
    yield
    app.dependency_overrides.pop(get_db, None)
    backends.memory.reset()


ADMINS = {
    role: AdminUser(id=f"a-{role}", username=role, password_hash="", role=role, totp_enabled=False, totp_last_step=0, token_version=0, active=True)
    for role in ("superadmin", "support", "finance")
}


def _admin_bearer(role: str) -> dict[str, str]:
    user = ADMINS[role]
    return {"Authorization": f"Bearer {issue_admin_token(sub=user.id, username=user.username, role=role, ver=0)}"}


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ------------------------------------------------------------------ inventory
def test_every_route_is_public_by_design_or_signed_in():
    unexpected = [
        f"{method} {path}" for method, path, merchant, admin in ROUTES
        if not merchant and not admin and (method, path) not in PUBLIC and not path.startswith(TELNYX_PREFIX)
    ]
    assert unexpected == [], f"routes without a session dependency (add auth or allow-list them): {unexpected}"
    known = {(method, path) for method, path, *_ in ROUTES}
    assert sorted(set(PUBLIC) - known) == []  # the allow-list has no stale entries


def test_admin_and_portal_sessions_never_mix():
    for method, path, merchant, admin in ROUTES:
        assert not (merchant and admin), f"{method} {path} accepts both session kinds"
        if path.startswith("/api/admin/") and path != "/api/admin/login":
            assert admin, f"{method} {path} is under /api/admin but has no admin guard"
        if admin:
            assert path.startswith("/api/admin/"), f"{method} {path}: admin guard outside /api/admin"


def test_admin_writes_name_their_roles():
    for method, path, _, admin in ROUTES:
        if admin and method != "GET" and not OWN_ACCOUNT.match(path):
            assert admin[0], f"{method} {path} lets every admin role write (finance is read-only)"
    by_route = {(method, path): admin for method, path, _, admin in ROUTES}
    for key, roles in EXPECTED_ROLES.items():
        assert set(by_route[key][0]) == roles, key


def test_telnyx_paths_are_signed_or_token_bound():
    known = {(method, path) for method, path, *_ in ROUTES}
    for method, path, *_ in ROUTES:
        if path.startswith(TELNYX_PREFIX) and method == "POST" and not path.endswith("/{sig}"):
            # Every legacy unsigned path has its signed twin (the unsigned one is refused in production).
            assert ("POST", f"{path}/{{sig}}") in known, path
    assert ("POST", "/telnyx/texml/{order_id}") not in known  # would hand out media tokens unsigned
    assert ("WS", "/telnyx/media") in known


# ------------------------------------------------------------------ live checks against every protected route
def test_every_protected_route_answers_401_without_a_token(client):
    for method, path, *_ in PROTECTED:
        response = client.request(method, _url(path))
        assert response.status_code == 401, (method, path, response.status_code)


@pytest.mark.parametrize(
    "token",
    [
        sign_media_stream_token(order_id="o1", call_log_id="c1"),
        sign_token({"r": "p1", "a": "1.00", "c": "USD"}, typ=TYP_PAY),
        sign_token({"sub": "m1"}, typ=TYP_VERIFY),
        sign_token({"mid": "m1"}, typ=TYP_GOOGLE_OAUTH),
        # "alg: none" JWT and a well-formed token signed with another key.
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJtMSIsInJvbGUiOiJtZXJjaGFudCJ9.",
        "eyJzdWIiOiJtMSIsInJvbGUiOiJtZXJjaGFudCIsInR5cCI6InNlc3Npb24ifQ." + "0" * 64,
    ],
    ids=["media", "pay", "verify", "oauth-state", "alg-none", "foreign-signature"],
)
def test_non_session_tokens_are_refused_everywhere(client, token):
    for method, path, *_ in PROTECTED:
        response = client.request(method, _url(path), headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, (method, path, response.status_code)


def test_owner_tokens_never_open_admin_routes_and_admin_tokens_never_open_the_portal(client):
    owner = {"Authorization": f"Bearer {issue_merchant_token(make_merchant())}"}
    admin = _admin_bearer("superadmin")
    for method, path, merchant, guards in PROTECTED:
        if guards:
            assert client.request(method, _url(path), headers=owner).status_code == 403, (method, path)
        if merchant:
            assert client.request(method, _url(path), headers=admin).status_code == 403, (method, path)


def test_finance_reads_but_cannot_change_accounts(client):
    finance, support, superadmin = (_admin_bearer(role) for role in ("finance", "support", "superadmin"))
    writes = [("PATCH", "/api/admin/merchants/x", {"business_name": "X"}), ("DELETE", "/api/admin/merchants/x", None),
              ("PUT", "/api/admin/merchants/x/addons", {"addons": {}}), ("POST", "/api/admin/merchants", None),
              ("DELETE", "/api/admin/inquiries/x", None), ("POST", "/api/admin/addon-requests/x/approve", {})]
    for method, url, body in writes:
        assert client.request(method, url, json=body, headers=finance).status_code == 403, (method, url)
    # Support edits accounts (the missing account is a 404 past the guard) but can't delete one.
    assert client.patch("/api/admin/merchants/missing", json={"business_name": "X"}, headers=support).status_code == 404
    assert client.delete("/api/admin/merchants/missing", headers=support).status_code == 403
    assert client.delete("/api/admin/merchants/missing", headers=superadmin).status_code == 404
    assert client.get("/api/admin/merchants", headers=finance).status_code == 200


def test_revoked_and_disabled_admins_are_signed_out(client):
    stale = {"Authorization": f"Bearer {issue_admin_token(sub='a-support', username='support', role='support', ver=3)}"}
    assert client.get("/api/admin/users/me", headers=stale).status_code == 401
    ADMINS["finance"].active = False
    try:
        assert client.get("/api/admin/users/me", headers=_admin_bearer("finance")).status_code == 401
    finally:
        ADMINS["finance"].active = True


# ------------------------------------------------------------------ interactive docs
def test_api_docs_are_off_in_production_unless_asked_for():
    production = SimpleNamespace(environment="production", expose_api_docs=None)
    assert not boot_guard.api_docs_enabled(production)
    assert boot_guard.api_docs_enabled(SimpleNamespace(environment="production", expose_api_docs=True))
    assert boot_guard.api_docs_enabled(SimpleNamespace(environment="development", expose_api_docs=None))
    assert "EXPOSE_API_DOCS=true: /docs and /openapi.json are public" in boot_guard.advisories(
        SimpleNamespace(environment="production", expose_api_docs=True, enforce_webhook_signatures=None)
    )
    assert (app.docs_url is not None) == boot_guard.api_docs_enabled(get_settings())
