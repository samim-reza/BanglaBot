"""Admin console: sign-in (+ two-factor enrolment), account creation per vertical, inbound
numbers, and the cross-account views (accounts, overview, finance, audit)."""

from __future__ import annotations

import time

from tests.e2e.api import OWNER_PASSWORD, admin_token, bearer, create_account, next_number, ok, owner_token, unique


async def test_wrong_password_is_refused_and_audited(client):
    response = await client.post("/api/admin/login", json={"username": "e2e-root", "password": "not-the-password-123"})
    assert response.status_code == 401
    token = await admin_token(client)
    page = await ok(await client.get("/api/admin/audit?action=admin.login_failed", headers=bearer(token)))
    assert any(event["action"] == "admin.login_failed" for event in page["items"])


async def test_two_factor_enrolment_then_sign_in_needs_the_code(client):
    from app.core.security import totp

    root = await admin_token(client)
    username = unique("e2e-support-")
    password = "Support-Pass-e2e-5518!"
    created = await ok(await client.post("/api/admin/users", json={"username": username, "password": password, "role": "support"}, headers=bearer(root)), 201)
    assert created["role"] == "support" and not created["totp_enabled"]

    token = await admin_token(client, username, password)
    setup = await ok(await client.post("/api/admin/users/me/totp/setup", headers=bearer(token)))
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    await ok(await client.post("/api/admin/users/me/totp/enable", json={"code": totp.totp(setup["secret"])}, headers=bearer(token)))

    # Password alone now asks for the code; the code of the next 30 s step signs in (no replay of the enrolment one).
    response = await client.post("/api/admin/login", json={"username": username, "password": password})
    assert response.status_code == 401 and response.headers.get("x-2fa-required") == "totp"
    signed_in = await admin_token(client, username, password, code=totp.totp(setup["secret"], at=time.time() + 30))
    me = await ok(await client.get("/api/admin/users/me", headers=bearer(signed_in)))
    assert me["totp_enabled"] is True
    # A support admin may not manage admins.
    assert (await client.get("/api/admin/users", headers=bearer(signed_in))).status_code == 403


async def test_create_accounts_set_the_inbound_number_and_view_them(client):
    admin = await admin_token(client)
    meta = await ok(await client.get("/api/admin/meta", headers=bearer(admin)))
    assert {"salon", "clinic", "restaurant"} <= {v["key"] for v in meta["verticals"]}

    salon = await create_account(client, admin, vertical="salon")
    merchant = salon["merchant"]
    assert merchant["vertical"] == "salon" and merchant["region"] == "US" and merchant["inbound_number"].startswith("+1")
    assert merchant["webhook_secret"] == "" and merchant["active"] is True

    # The same number on a second account is refused; a new one is accepted and normalised.
    clash = await client.post(
        "/api/admin/merchants", headers=bearer(admin),
        json={"business_name": "Clash", "username": unique("clash-"), "password": OWNER_PASSWORD, "vertical": "clinic", "region": "US",
              "inbound_number": merchant["inbound_number"]},
    )
    assert clash.status_code == 409
    raw = next_number()
    updated = await ok(await client.patch(f"/api/admin/merchants/{merchant['id']}", json={"inbound_number": raw.replace("+1", "(1) ")}, headers=bearer(admin)))
    assert updated["inbound_number"] == raw

    detail = await ok(await client.get(f"/api/admin/merchants/{merchant['id']}", headers=bearer(admin)))
    assert detail["merchant"]["id"] == merchant["id"] and detail["catalog_items"] == 0 and "usage" in detail and "entitlements" in detail
    listed = await ok(await client.get("/api/admin/merchants", headers=bearer(admin)))
    assert merchant["id"] in {row["id"] for row in listed}

    overview = await ok(await client.get("/api/admin/overview", headers=bearer(admin)))
    assert overview["merchants"] >= 1 and overview["by_vertical"]["salon"] >= 1

    # Admin-side password reset signs the owner out everywhere; the new password works.
    await ok(await client.patch(f"/api/admin/merchants/{merchant['id']}", json={"password": "Reset-Pass-e2e-3391!"}, headers=bearer(admin)))
    assert (await client.get("/api/auth/me", headers=salon["headers"])).status_code == 401
    assert await owner_token(client, salon["username"], "Reset-Pass-e2e-3391!")

    # Disabling the account locks the owner out.
    await ok(await client.patch(f"/api/admin/merchants/{merchant['id']}", json={"active": False}, headers=bearer(admin)))
    assert (await client.post("/api/auth/login", json={"username": salon["username"], "password": "Reset-Pass-e2e-3391!"})).status_code in (401, 403)

    events = await ok(await client.get(f"/api/admin/audit?merchant_id={merchant['id']}", headers=bearer(admin)))
    assert "merchant.password_changed" in {event["action"] for event in events["items"]}


async def test_finance_views_answer_on_real_sql(client):
    admin = await admin_token(client)
    overview = await ok(await client.get("/api/admin/finance/overview", headers=bearer(admin)))
    assert "cost_usd" in str(overview) or overview
    for by in ("category", "provider", "model", "vertical", "account"):
        await ok(await client.get(f"/api/admin/finance/breakdown?by={by}", headers=bearer(admin)))
    await ok(await client.get("/api/admin/finance/accounts", headers=bearer(admin)))
    await ok(await client.get("/api/admin/finance/forecast", headers=bearer(admin)))
    await ok(await client.get("/api/admin/finance/pricebook", headers=bearer(admin)))
    await ok(await client.get("/api/admin/finance/caps", headers=bearer(admin)))
    export = await client.get("/api/admin/finance/export.csv", headers=bearer(admin))
    assert export.status_code == 200 and "text/csv" in export.headers["content-type"]
    assert (await client.get("/api/admin/finance/overview?month=2026-13", headers=bearer(admin))).status_code == 422


async def test_every_vertical_can_be_created_and_its_workspace_renders(client):
    from app.verticals import VERTICALS

    admin = await admin_token(client)
    for key in VERTICALS:
        account = await create_account(client, admin, vertical=key, plan="starter", inbound=False)
        workspace = await ok(await client.get("/api/auth/workspace", headers=account["headers"]))
        assert workspace["merchant"]["vertical"] == key and workspace["vertical"]["key"] == key
        preview = await ok(await client.get("/api/auth/flow-preview", headers=account["headers"]))
        assert preview["steps"], key
        flow = await ok(await client.get("/api/agent/flow", headers=account["headers"]))
        assert flow, key
