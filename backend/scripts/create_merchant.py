"""Create (or reset the password of) an account login.

    python -m scripts.create_merchant --username clinic2 --password secret \
        --business "Second Clinic" --vertical clinic --region US [--owner "Owner"] [--phone ...] [--support ...] [--language en]
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.regions import REGIONS, region_defaults
from app.core.security import hash_password
from app.db.bootstrap import create_schema
from app.db.session import AsyncSessionLocal, engine
from app.models import Merchant
from app.verticals import VERTICALS


async def upsert(args: argparse.Namespace) -> str:
    await create_schema()
    async with AsyncSessionLocal() as session:
        merchant = await session.scalar(select(Merchant).where(Merchant.username == args.username))
        if merchant is None:
            merchant = Merchant(
                business_name=args.business or args.username,
                username=args.username,
                password_hash=hash_password(args.password),
                owner_name=args.owner or "",
                phone=args.phone or "",
                support_phone=args.support or "",
                email=args.email or "",
                language=args.language,
                supported_languages=[args.language] + [c for c in ("bn", "en") if c != args.language],
                vertical=args.vertical,
                vertical_config={},
                **region_defaults(args.region),
            )
            session.add(merchant)
            action = "created"
        else:
            merchant.password_hash = hash_password(args.password)
            if args.business:
                merchant.business_name = args.business
            action = "password updated"
        await session.commit()
        await session.refresh(merchant)
        merchant_id = merchant.id
    await engine.dispose()
    return f"{action}: {args.username} (id {merchant_id})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--business", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--support", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--language", default="en", choices=("bn", "en"))
    parser.add_argument("--vertical", default="ecommerce", choices=sorted(VERTICALS))
    parser.add_argument("--region", default="INTL", choices=sorted(REGIONS))
    print(asyncio.run(upsert(parser.parse_args())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
