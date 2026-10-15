"""Admin users, roles and TOTP sign-in — routes run on ``FakeDB``, never a database."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import require_admin
from app.core import memo
from app.core.ratelimit import backends
from app.core.security import hash_password, issue_admin_token, issue_merchant_token, totp, verify_token
from app.core.security.passwords import legacy_pbkdf2_hash
from app.db.session import get_db
from app.main import app
from app.models import AdminUser
from app.services import admin_auth_service
from app.services import admin_user_service as admins
from app.services import audit_service
from tests.security_fakes import FakeDB, FakeSessionFactory, db_override, make_merchant

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    backends.memory.reset()
    memo.clear()
    factory = FakeSessionFactory()
    monkeypatch.setattr(audit_service, "session_factory", factory)
    yield factory
    backends.memory.reset()
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _users_exist(monkeypatch, exist: bool = True, by_name: AdminUser | None = None):
    async def has(db):
        return exist

    async def lookup(db, username):
        return by_name if by_name is not None and by_name.username == username.strip() else None

    monkeypatch.setattr(admins, "has_admin_users", has)
    monkeypatch.setattr(admins, "get_by_username", lookup)


def _user(**overrides) -> AdminUser:
    values = dict(id="a1", username="ops", password_hash=hash_password(PASSWORD), role="superadmin", totp_secret=None,
                  totp_enabled=False, totp_last_step=0, token_version=0, active=True)
    values.update(overrides)
    return AdminUser(**values)


def _bearer(user: AdminUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_admin_token(sub=user.id, username=user.username, role=user.role, ver=user.token_version)}"}


ENV_BEARER = {"Authorization": f"Bearer {issue_admin_token(sub='env:admin', username='admin', role='superadmin', env=True)}"}


# ------------------------------------------------------------------ the role dependency
def test_require_admin_works_bare_and_with_roles(monkeypatch):
    mini = FastAPI()

    @mini.get("/any")
    async def any_admin(admin=Depends(require_admin)):
        return {"id": admin.id, "role": admin.role}

    @mini.get("/finance")
    async def finance(admin=Depends(require_admin("finance", "superadmin"))):
        return {"id": admin.id}

    support = _user(id="s1", username="help", role="support")
    mini.dependency_overrides[get_db] = db_override(FakeDB(support))
    test = TestClient(mini)
    assert test.get("/any").status_code == 401
    assert test.get("/any", headers=_bearer(support)).json() == {"id": "s1", "role": "support"}
    assert test.get("/finance", headers=_bearer(support)).status_code == 403
    merchant_token = {"Authorization": f"Bearer {issue_merchant_token(make_merchant())}"}
    assert test.get("/any", headers=merchant_token).status_code == 403
    with pytest.raises(ValueError):
        require_admin("root")


async def test_resolve_revoked_env_and_legacy_tokens(monkeypatch):
    user = _user(token_version=3)
    db = FakeDB(user)
    _users_exist(monkeypatch, True, by_name=user)
    current = verify_token(_bearer(user)["Authorization"][7:])
    assert (await admin_auth_service.resolve(db, current)).role == "superadmin"
    user.token_version = 4  # password changed / signed out everywhere
    with pytest.raises(HTTPException) as info:
        await admin_auth_service.resolve(db, current)
    assert info.value.status_code == 401
    env_claims = verify_token(ENV_BEARER["Authorization"][7:])
    with pytest.raises(HTTPException):
        await admin_auth_service.resolve(db, env_claims)  # env sessions end once admin users exist
    legacy = {"typ": "admin", "legacy": True, "sub": "ops", "role": "admin"}
    user.token_version = 0
    assert (await admin_auth_service.resolve(db, legacy)).id == "a1"
    _users_exist(monkeypatch, False)
    assert (await admin_auth_service.resolve(db, env_claims)).via_env is True


# ------------------------------------------------------------------ sign-in
def test_env_login_only_while_there_are_no_admin_users(client, monkeypatch, _isolated):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_username", "admin")
    monkeypatch.setattr(get_settings(), "admin_password", PASSWORD)
    app.dependency_overrides[get_db] = db_override(FakeDB())
    _users_exist(monkeypatch, False)
    ok = client.post("/api/admin/login", json={"username": "admin", "password": PASSWORD})
    claims = verify_token(ok.json()["token"])
    assert claims["typ"] == "admin" and claims["env"] is True and claims["role"] == "superadmin"
    assert claims["exp"] - claims["iat"] == 12 * 3600
    assert client.post("/api/admin/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert [event.action for event in _isolated.added] == ["admin.login", "admin.login_failed"]
    _users_exist(monkeypatch, True)
    assert client.post("/api/admin/login", json={"username": "admin", "password": PASSWORD}).status_code == 401


def test_admin_login_with_totp_and_rehash(client, monkeypatch, _isolated):
    secret = totp.generate_secret()
    from app.core.crypto import encrypt_secret

    user = _user(password_hash=legacy_pbkdf2_hash(PASSWORD, iterations=1000), totp_secret=encrypt_secret(secret), totp_enabled=True)
    db = FakeDB(user)
    app.dependency_overrides[get_db] = db_override(db)
    _users_exist(monkeypatch, True, by_name=user)
    asked = client.post("/api/admin/login", json={"username": "ops", "password": PASSWORD})
    assert asked.status_code == 401 and asked.headers["x-2fa-required"] == "totp"
    assert client.post("/api/admin/login", json={"username": "ops", "password": PASSWORD, "code": "000000"}).status_code == 401
    code = totp.totp(secret)
    ok = client.post("/api/admin/login", json={"username": "ops", "password": PASSWORD, "code": code})
    assert ok.status_code == 200 and verify_token(ok.json()["token"])["sub"] == "a1"
    assert user.password_hash.startswith("$argon2id$") and user.last_login_at is not None
    replay = client.post("/api/admin/login", json={"username": "ops", "password": PASSWORD, "code": code})
    assert replay.status_code in (401, 429)  # a code works once


def test_admin_login_lockout(client, monkeypatch):
    user = _user()
    app.dependency_overrides[get_db] = db_override(FakeDB(user))
    _users_exist(monkeypatch, True, by_name=user)
    codes = [client.post("/api/admin/login", json={"username": "ops", "password": "bad-password"}).status_code for _ in range(4)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429


# ------------------------------------------------------------------ managing admins
def test_superadmin_creates_admins_and_others_cannot(client, monkeypatch, _isolated):
    support = _user(id="s1", username="help", role="support")
    db = FakeDB(support)
    app.dependency_overrides[get_db] = db_override(db)
    _users_exist(monkeypatch, False)
    weak = client.post("/api/admin/users", json={"username": "fin", "password": "short", "role": "finance"}, headers=ENV_BEARER)
    assert weak.status_code == 422
    created = client.post("/api/admin/users", json={"username": "fin", "password": PASSWORD, "role": "finance"}, headers=ENV_BEARER)
    assert created.status_code == 201 and created.json()["role"] == "finance" and "password_hash" not in created.json()
    assert _isolated.added[-1].action == "admin_user.created"
    _users_exist(monkeypatch, True)
    assert client.post("/api/admin/users", json={"username": "x1", "password": PASSWORD}, headers=_bearer(support)).status_code == 403
    assert client.get("/api/admin/users", headers=_bearer(support)).status_code == 403


def test_last_superadmin_is_protected(client, monkeypatch):
    boss = _user()
    db = FakeDB(boss, scalars=[0, 0])
    app.dependency_overrides[get_db] = db_override(db)
    _users_exist(monkeypatch, True)
    demote = client.patch("/api/admin/users/a1", json={"role": "support"}, headers=_bearer(boss))
    assert demote.status_code == 409
    assert client.delete("/api/admin/users/a1", headers=_bearer(boss)).status_code == 409  # self


def test_totp_setup_then_enable(client, monkeypatch):
    user = _user(role="finance")
    db = FakeDB(user)
    app.dependency_overrides[get_db] = db_override(db)
    _users_exist(monkeypatch, True)
    setup = client.post("/api/admin/users/me/totp/setup", headers=_bearer(user)).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and user.totp_secret.startswith("enc:")
    assert client.post("/api/admin/users/me/totp/enable", json={"code": "123456"}, headers=_bearer(user)).status_code == 400
    enabled = client.post("/api/admin/users/me/totp/enable", json={"code": totp.totp(setup["secret"])}, headers=_bearer(user))
    assert enabled.status_code == 200 and enabled.json()["totp_enabled"] is True
    assert client.post("/api/admin/users/me/totp/setup", headers=_bearer(user)).status_code == 409


def test_my_password_change_revokes_sessions(client, monkeypatch):
    user = _user(role="support")
    db = FakeDB(user)
    app.dependency_overrides[get_db] = db_override(db)
    _users_exist(monkeypatch, True)
    old = _bearer(user)
    response = client.post("/api/admin/users/me/password", json={"current_password": PASSWORD, "new_password": "another-long-passphrase"}, headers=old)
    assert response.status_code == 200 and user.token_version == 1
    assert client.get("/api/admin/users/me", headers=old).status_code == 401
    assert client.get("/api/admin/users/me", headers={"Authorization": f"Bearer {response.json()['token']}"}).status_code == 200


# ------------------------------------------------------------------ impersonation
def test_impersonation_is_role_limited_short_and_audited(client, monkeypatch, _isolated):
    merchant = make_merchant(token_version=5)
    support, finance = _user(id="s1", username="help", role="support"), _user(id="f1", username="money", role="finance")
    app.dependency_overrides[get_db] = db_override(FakeDB(merchant, support, finance))
    _users_exist(monkeypatch, True)
    assert client.post("/api/admin/merchants/m1/impersonate", headers=_bearer(finance)).status_code == 403
    response = client.post("/api/admin/merchants/m1/impersonate", headers=_bearer(support))
    claims = verify_token(response.json()["token"])
    assert claims["imp"] == "s1" and claims["ver"] == 5 and claims["exp"] - claims["iat"] == 2 * 3600
    assert _isolated.added[-1].action == "admin.impersonate" and _isolated.added[-1].merchant_id == "m1"


# ------------------------------------------------------------------ boot seeding
class _SeedSession(FakeSessionFactory):
    def __init__(self, existing: str | None) -> None:
        super().__init__()
        self.existing = existing

    async def scalar(self, stmt):
        return self.existing


async def test_seed_first_superadmin_only_into_an_empty_table(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_username", "founder")
    monkeypatch.setattr(get_settings(), "admin_password", PASSWORD)
    empty = _SeedSession(None)
    assert await admins.seed_from_env(empty) is True
    seeded = empty.added[0]
    assert seeded.username == "founder" and seeded.role == "superadmin" and seeded.password_hash.startswith("$argon2id$")
    taken = _SeedSession("a1")
    assert await admins.seed_from_env(taken) is False and taken.added == []
    assert await admins.seed_from_env(FakeSessionFactory(fail=True)) is False  # never breaks boot
