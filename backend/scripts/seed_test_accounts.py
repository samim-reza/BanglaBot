"""Create the platform admin and one demo account per business type, for hands-on testing.

    venv/bin/python -m scripts.seed_test_accounts

1. Applies the schema (the same idempotent ``bootstrap`` the app runs at boot: new
   tables and ``ADD COLUMN IF NOT EXISTS`` patches — additive only).
2. Seeds the first superadmin with a STRONG generated password (only while the
   admin_users table is empty; the weak dev ``ADMIN_PASSWORD`` is never used).
3. Creates ``demo_<type>`` accounts (clinic, dental, vet, restaurant, salon,
   real estate, home service, ecommerce, custom) with their catalog (doctors,
   menu, stylists …) and a few sample records. Existing accounts are never touched;
   re-running skips accounts that already exist. No phone number is assigned —
   move the Telnyx number between accounts in the admin panel.

Credentials are printed once and written to ``backend/.test-accounts.txt`` (gitignored).
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parents[1] / ".test-accounts.txt"
ADMIN_USERNAME = "platform_admin"
PLAN = "pro"


def _password(prefix: str) -> str:
    return f"{prefix}-{secrets.token_urlsafe(9)}"


async def main() -> int:
    admin_password = _password("Admin")
    # The superadmin seed reads these settings; set them before anything loads the settings.
    os.environ["ADMIN_USERNAME"] = ADMIN_USERNAME
    os.environ["ADMIN_PASSWORD"] = admin_password

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.bootstrap import bootstrap
    from app.db.session import AsyncSessionLocal, engine
    from app.models import AdminUser, CatalogItem, Merchant, Order
    from scripts.simulate import SEEDS, MemorySession

    await bootstrap()
    lines = ["BanglaBot test accounts", ""]
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(AdminUser).where(AdminUser.username == ADMIN_USERNAME))
        if admin is not None:
            # This script's own test admin: (re)set its password so the printed one always works.
            admin.password_hash = hash_password(admin_password)
            admin.token_version = int(admin.token_version or 0) + 1
            admin.active = True
            await db.flush()
            lines.append(f"ADMIN  {ADMIN_USERNAME} / {admin_password}  (superadmin) -> /admin")
        else:
            lines.append("ADMIN  an admin user already existed before this script — sign in with that one")
        lines.append("")
        for key, seed in SEEDS.items():
            username = f"demo_{key}"
            if await db.scalar(select(Merchant.id).where(Merchant.username == username)) is not None:
                lines.append(f"{key:13s} {username} — already exists (password unchanged)")
                continue
            memory = MemorySession()
            await seed(memory)  # type: ignore[arg-type]
            await memory.flush()
            merchant = next((obj for obj in memory.objects if isinstance(obj, Merchant)), None)
            if merchant is None:
                lines.append(f"{key:13s} — seed produced no account, skipped")
                continue
            password = _password("Demo")
            merchant.username = username
            merchant.password_hash = hash_password(password)
            merchant.inbound_number = ""
            merchant.plan = PLAN
            merchant.business_name = f"{merchant.business_name} (demo)"
            merchant.widget_key = secrets.token_urlsafe(18)
            # The account first: catalog items and records reference it (no ORM relationships to order the inserts).
            db.add(merchant)
            await db.flush()
            rest: list[Any] = [obj for obj in memory.objects if isinstance(obj, (CatalogItem, Order))]
            db.add_all(rest)
            await db.flush()
            lines.append(f"{key:13s} {username} / {password}   ({merchant.business_name})")
        await db.commit()
    await engine.dispose()
    text = "\n".join(lines) + "\n\nOwner portal: /login · Admin panel: /admin · Move the Telnyx number: Admin → Accounts → <account> → Inbound number.\n"
    OUTPUT.write_text(text)
    print(text)
    print(f"(saved to {OUTPUT})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
