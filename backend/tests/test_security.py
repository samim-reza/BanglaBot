"""Passwords, tokens, boot guard, TOTP and secrets at rest — pure functions, no database."""

from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import crypto
from app.core.config import get_settings
from app.core.security import (
    TYP_ADMIN,
    TYP_MEDIA_STREAM,
    TYP_SESSION,
    PasswordPolicyError,
    hash_password,
    issue_merchant_token,
    needs_rehash,
    sign_media_stream_token,
    sign_token,
    validate_new_password,
    verify_media_stream_token,
    verify_password,
    verify_token,
)
from app.core.security import boot_guard, tokens, totp
from app.core.security.passwords import legacy_pbkdf2_hash
from tests.security_fakes import make_merchant

STRONG = "correct-horse-battery-staple"


# ------------------------------------------------------------------ passwords
def test_argon2id_hash_verifies_and_is_current():
    stored = hash_password("s3cret-passphrase")
    assert stored.startswith("$argon2id$") and "m=19456,t=3,p=1" in stored
    assert verify_password("s3cret-passphrase", stored)
    assert not verify_password("wrong", stored)
    assert not needs_rehash(stored)


def test_legacy_pbkdf2_still_verifies_and_asks_for_a_rehash():
    legacy = legacy_pbkdf2_hash("old-password", iterations=1000)
    assert legacy.startswith("pbkdf2_sha256$1000$")
    assert verify_password("old-password", legacy)
    assert not verify_password("other", legacy)
    assert needs_rehash(legacy)


def test_garbage_hashes_never_verify():
    for stored in ("", "plain", "pbkdf2_sha256$x$y$z", "$argon2id$broken", None):
        assert not verify_password("anything", stored)


def test_password_policy():
    validate_new_password(STRONG, username="demo", email="owner@example.com")
    for bad, kwargs in (
        ("short1", {}),
        ("demo-account", {"username": "demo-account"}),
        ("Owner@Example.com", {"email": "owner@example.com"}),
        ("password123", {}),
        ("aaaaaaaaaaaa", {}),
        ("x" * 201, {}),
    ):
        with pytest.raises(PasswordPolicyError):
            validate_new_password(bad, **kwargs)


# ------------------------------------------------------------------ tokens
def test_tokens_carry_typ_iat_jti_and_enforce_typ():
    token = sign_token({"sub": "m1"}, ttl_seconds=60)
    claims = verify_token(token, typ=TYP_SESSION)
    assert claims["typ"] == TYP_SESSION and claims["iat"] <= time.time() and len(claims["jti"]) >= 8
    assert "=" not in token.split(".")[0]
    with pytest.raises(HTTPException):
        verify_token(token, typ=TYP_ADMIN)
    media = sign_media_stream_token(order_id="o1", call_log_id="c1")
    with pytest.raises(HTTPException):
        verify_token(media, typ=(TYP_SESSION, TYP_ADMIN))


def test_expired_and_tampered_tokens_are_rejected():
    expired = sign_token({"sub": "m1", "exp": int(time.time()) - 5}, ttl_seconds=None)
    with pytest.raises(HTTPException) as info:
        verify_token(expired)
    assert info.value.detail == "Token expired"
    body, sig = sign_token({"sub": "m1"}).split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"sub": "admin", "typ": "admin"}).encode()).decode().rstrip("=")
    for bad in (f"{forged}.{sig}", f"{body}.{'0' * 64}", "not-a-token", f"{body}.é"):
        with pytest.raises(HTTPException):
            verify_token(bad)


def test_secret_rotation_keeps_old_tokens_valid_until_the_previous_secret_is_dropped(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_token_secret", "A" * 40)
    monkeypatch.setattr(settings, "admin_token_secret_previous", None)
    old = sign_token({"sub": "m1"})
    monkeypatch.setattr(settings, "admin_token_secret", "B" * 40)
    monkeypatch.setattr(settings, "admin_token_secret_previous", "A" * 40)
    assert verify_token(old)["sub"] == "m1"
    new = sign_token({"sub": "m2"})
    monkeypatch.setattr(settings, "admin_token_secret_previous", None)
    assert verify_token(new)["sub"] == "m2"
    with pytest.raises(HTTPException):
        verify_token(old)


def test_legacy_tokens_without_typ_only_pass_as_bearer_sessions():
    claims = {"sub": "admin", "role": "admin", "exp": int(time.time()) + 60}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()  # old tokens kept padding
    legacy = f"{body}.{tokens._signature(body, tokens.signing_secrets()[0])}"
    with pytest.raises(HTTPException):
        verify_token(legacy)
    upgraded = verify_token(legacy, typ=(TYP_SESSION, TYP_ADMIN), legacy_ok=True)
    assert upgraded["typ"] == TYP_ADMIN and upgraded["legacy"] is True


def test_merchant_session_carries_token_version_and_impersonation_is_short():
    merchant = SimpleNamespace(id="m1", username="demo", token_version=4)
    claims = verify_token(issue_merchant_token(merchant), typ=TYP_SESSION)
    assert claims["ver"] == 4 and claims["role"] == "merchant"
    assert claims["exp"] - claims["iat"] == get_settings().merchant_session_ttl_hours * 3600
    imp = verify_token(issue_merchant_token(merchant, impersonated_by="admin-1"))
    assert imp["imp"] == "admin-1" and imp["exp"] - imp["iat"] == 2 * 3600


def test_media_stream_token_is_bound_to_its_call():
    token = sign_media_stream_token(order_id="o1", call_log_id="c1")
    assert verify_token(token)["typ"] == TYP_MEDIA_STREAM
    verify_media_stream_token(token, order_id="o1", call_log_id="c1")
    with pytest.raises(HTTPException):
        verify_media_stream_token(token, order_id="o1", call_log_id="c2")
    with pytest.raises(HTTPException):
        verify_media_stream_token(sign_token({"order_id": "o1", "call_log_id": "c1"}), order_id="o1", call_log_id="c1")


# ------------------------------------------------------------------ boot guard
def _settings(**overrides):
    values = dict(
        environment="production", admin_token_secret="s" * 48, admin_username="founder",
        admin_password=STRONG, encryption_secret="e" * 48, telnyx_webhook_secret=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_boot_guard_refuses_production_defaults():
    with pytest.raises(boot_guard.InsecureConfiguration) as info:
        boot_guard.enforce(_settings(admin_token_secret="change-me-admin-token-secret", admin_password="admin@1234", encryption_secret=None))
    message = str(info.value)
    assert "ADMIN_TOKEN_SECRET" in message and "ADMIN_PASSWORD" in message and "ENCRYPTION_SECRET" in message
    assert "admin@1234" not in message and "change-me-admin-token-secret" not in message  # never echoes values
    for weak in (dict(admin_token_secret="short"), dict(admin_password="founder"), dict(telnyx_webhook_secret="tiny")):
        with pytest.raises(boot_guard.InsecureConfiguration):
            boot_guard.enforce(_settings(**weak))


def test_boot_guard_passes_strong_production_and_only_warns_in_development():
    assert boot_guard.enforce(_settings()) == []
    problems = boot_guard.enforce(_settings(environment="development", admin_password="admin@1234", encryption_secret=None))
    assert len(problems) == 2


# ------------------------------------------------------------------ TOTP (RFC 6238 Appendix B)
RFC_SECRETS = {
    "sha1": b"12345678901234567890",
    "sha256": b"12345678901234567890123456789012",
    "sha512": b"1234567890" * 6 + b"1234",
}
RFC_VECTORS = [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


@pytest.mark.parametrize("at,sha1,sha256,sha512", RFC_VECTORS)
def test_totp_rfc6238_vectors(at, sha1, sha256, sha512):
    for algorithm, expected in (("sha1", sha1), ("sha256", sha256), ("sha512", sha512)):
        secret = base64.b32encode(RFC_SECRETS[algorithm]).decode()
        assert totp.totp(secret, at=at, digits=8, algorithm=algorithm) == expected


def test_totp_verify_window_and_replay_guard():
    secret = totp.generate_secret()
    now = 1_800_000_000.0
    code = totp.totp(secret, at=now)
    step = totp.verify_totp(secret, code, at=now)
    assert step == totp.time_step(now)
    assert totp.verify_totp(secret, code, at=now + 30) == step  # one step of drift
    assert totp.verify_totp(secret, code, at=now + 95) is None  # too old
    assert totp.verify_totp(secret, code, at=now, last_step=step) is None  # already used
    assert totp.verify_totp(secret, "12345", at=now) is None
    uri = totp.provisioning_uri(secret, account="ops@x", issuer="Callisa Admin")
    assert uri.startswith("otpauth://totp/Callisa%20Admin%3Aops%40x?") and f"secret={secret}" in uri


# ------------------------------------------------------------------ secrets at rest
def test_enc_prefixed_secrets_round_trip_and_accept_legacy_plaintext():
    stored = crypto.encrypt_secret("whsec-123")
    assert stored.startswith("enc:") and "whsec" not in stored
    assert crypto.decrypt_secret(stored) == "whsec-123"
    assert crypto.decrypt_secret("legacy-plain") == "legacy-plain"
    assert crypto.encrypt_secret("") == "" and crypto.decrypt_secret("") == ""
    assert crypto.decrypt_secret("enc:garbage") == ""


def test_setting_encryption_secret_still_decrypts_data_from_the_token_secret_fallback(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "encryption_secret", None)
    before = crypto.encrypt("refresh-token")
    old_hash = crypto.lookup_hash("feed", purpose="calendar-feed")
    monkeypatch.setattr(settings, "encryption_secret", "n" * 40)
    assert crypto.decrypt(before) == "refresh-token"
    assert crypto.lookup_hashes("feed", purpose="calendar-feed")[0] != old_hash
    assert old_hash in crypto.lookup_hashes("feed", purpose="calendar-feed")


def test_merchant_secret_columns_are_encrypted_and_upgraded():
    merchant = make_merchant(webhook_secret="abc123", calendar_token="feedtoken")
    assert merchant.webhook_secret == "abc123" and merchant.webhook_secret_stored.startswith("enc:")
    assert merchant.calendar_token == "feedtoken" and merchant.calendar_token_legacy == ""
    assert merchant.calendar_token_hash == crypto.lookup_hash("feedtoken", purpose="calendar-feed")
    legacy = make_merchant()
    legacy.webhook_secret_stored, legacy.calendar_token_legacy = "plain-secret", "old-feed"
    assert legacy.webhook_secret == "plain-secret" and legacy.calendar_token == "old-feed"
    assert legacy.upgrade_stored_secrets() is True
    assert legacy.webhook_secret_stored.startswith("enc:") and legacy.webhook_secret == "plain-secret"
    assert legacy.calendar_token_legacy == "" and legacy.calendar_token == "old-feed"
    assert legacy.upgrade_stored_secrets() is False
