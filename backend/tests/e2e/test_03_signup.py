"""Self-serve signup (the /get-started API): quote → signup → dummy checkout → pay →
admin approval (or auto-activation) → email verification → the owner signs in."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from tests.e2e.api import admin_token, bearer, client_ip, fetch, ok, owner_token, unique
from tests.e2e.fixtures import settle_background

PASSWORD = "Signup-Pass-e2e-6624!"


def _form(email: str, **extra) -> dict:  # noqa: ANN003
    return {
        "tier": "starter", "interval": "month", "addons": {"sms": 1}, "business_name": "Bright Smiles Salon", "owner_name": "Sam Doe",
        "email": email, "phone": "+1 415 555 0199", "password": PASSWORD, "region": "US", "vertical": "salon", **extra,
    }


def _pay_token(checkout_url: str) -> str:
    path = urlsplit(checkout_url).path
    assert path.startswith("/pay/"), checkout_url
    return path.removeprefix("/pay/")


async def test_paid_signup_waits_for_approval_then_the_owner_signs_in(client):
    from app.models import Merchant, Payment, Subscription

    catalog = await ok(await client.get("/api/public/catalog?vertical=salon"))
    assert "starter" in {tier["key"] for tier in catalog["plans"]} and "salon" in {v["key"] for v in catalog["verticals"]}
    quote = await ok(await client.post("/api/public/signup/quote", json={"tier": "starter", "interval": "month", "addons": {"sms": 1}, "vertical": "salon"}))
    assert float(quote["total"]) == 59.0, quote

    email = f"{unique('owner-')}@example.test"
    created = await ok(await client.post("/api/public/signup", json=_form(email), headers=client_ip()), 201)
    assert created["status"] == "pending_payment" and created["checkout_url"].startswith("http://portal.test/pay/")
    reference = created["reference"]
    merchant = (await fetch(Merchant, email=email))[0]
    assert merchant.active is False and merchant.plan == "starter" and merchant.addons.get("sms") == 1
    # Not live before payment + approval.
    login = await client.post("/api/auth/login", json={"username": email, "password": PASSWORD}, headers=client_ip())
    assert login.status_code in (401, 403)
    # A duplicate email is refused.
    assert (await client.post("/api/public/signup", json=_form(email), headers=client_ip())).status_code == 409

    token = _pay_token(created["checkout_url"])
    page = await ok(await client.get(f"/api/public/pay/{token}"))
    assert page["amount"] == "59.00" and page["status"] == "pending" and page["can_complete"] is True
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert (await client.get(f"/api/public/pay/{tampered}")).status_code == 404
    paid = await ok(await client.post(f"/api/public/pay/{token}/complete"))
    assert paid["status"] == "paid" and paid["return_url"].endswith(f"?reference={reference}")
    again = await ok(await client.post(f"/api/public/pay/{token}/complete"))  # idempotent
    assert again["status"] == "paid"
    await settle_background()

    status = await ok(await client.get(f"/api/public/signup/status?reference={reference}"))
    assert status == {"status": "awaiting_approval", "email_verified": False, "paid": True}
    sub = (await fetch(Subscription, id=reference))[0]
    assert sub.status == "active" and sub.merchant_id == merchant.id
    assert [p.status for p in await fetch(Payment, subscription_id=reference)] == ["paid"]

    admin = await admin_token(client)
    waiting = await ok(await client.get("/api/admin/signups?status=awaiting_approval", headers=bearer(admin)))
    row = next(item for item in waiting["items"] if item["merchant_id"] == merchant.id)
    assert row["verify_url"].startswith("http://portal.test/signup/verify?token=")
    approved = await ok(await client.post(f"/api/admin/signups/{merchant.id}/approve", json={"note": "looks real"}, headers=bearer(admin)))
    assert approved["status"] == "approved" and approved["account_active"] is True

    verify_token = parse_qs(urlsplit(row["verify_url"]).query)["token"][0]
    verified = await ok(await client.post("/api/public/signup/verify-email", json={"token": verify_token}))
    assert verified["verified"] is True
    assert (await client.post("/api/public/signup/verify-email", json={"token": verify_token + "x"})).status_code == 400

    owner = await owner_token(client, email, PASSWORD)
    plan = await ok(await client.get("/api/plan", headers=bearer(owner)))
    assert "starter" in str(plan)
    history = await ok(await client.get("/api/plan/subscriptions", headers=bearer(owner)))
    assert history["items"] and history["items"][0]["status"] == "active"


async def test_auto_activation_turns_a_paid_signup_live_without_the_admin(client):
    from app.models import Merchant

    admin = await admin_token(client)
    await ok(await client.put("/api/admin/plans/settings", json={"auto_activate": True, "require_verified_email": False}, headers=bearer(admin)))
    try:
        email = f"{unique('auto-')}@example.test"
        created = await ok(await client.post("/api/public/signup", json=_form(email, tier="chat", addons={}, vertical="clinic"), headers=client_ip()), 201)
        await ok(await client.post(f"/api/public/pay/{_pay_token(created['checkout_url'])}/complete"))
        await settle_background()
        status = await ok(await client.get(f"/api/public/signup/status?reference={created['reference']}"))
        assert status["status"] == "approved"
        assert (await fetch(Merchant, email=email))[0].active is True
        assert await owner_token(client, email, PASSWORD)
    finally:
        await ok(await client.put("/api/admin/plans/settings", json={"auto_activate": False, "require_verified_email": False}, headers=bearer(admin)))


async def test_honeypot_and_weak_password_create_nothing(client):
    from app.models import Merchant

    email = f"{unique('bot-')}@example.test"
    decoy = await ok(await client.post("/api/public/signup", json=_form(email, website="http://spam.example"), headers=client_ip()), 201)
    assert decoy["checkout_url"] == "" and not await fetch(Merchant, email=email)
    weak = await client.post("/api/public/signup", json=_form(email, password="password1"), headers=client_ip())
    assert weak.status_code == 422 and not await fetch(Merchant, email=email)


async def test_admin_can_reject_a_signup_and_the_account_stays_off(client):
    from app.models import Merchant, Subscription

    email = f"{unique('reject-')}@example.test"
    created = await ok(await client.post("/api/public/signup", json=_form(email), headers=client_ip()), 201)
    merchant = (await fetch(Merchant, email=email))[0]
    admin = await admin_token(client)
    rejected = await ok(await client.post(f"/api/admin/signups/{merchant.id}/reject", json={"note": "fraud"}, headers=bearer(admin)))
    assert rejected["status"] == "rejected"
    assert (await fetch(Subscription, id=created["reference"]))[0].status == "cancelled"
    # Paying a cancelled signup's old link must not switch the account on.
    await client.post(f"/api/public/pay/{_pay_token(created['checkout_url'])}/complete")
    await settle_background()
    assert (await fetch(Merchant, email=email))[0].active is False
