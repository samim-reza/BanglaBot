"""Drop every application table and rebuild the schema (DESTRUCTIVE).

    python -m scripts.reset_database --yes [--seed]

Refuses to run without ``--yes``. ``--seed`` creates the demo merchant
(``demo`` / ``demo123``) with two sample orders afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.db.base import Base
from app.db.bootstrap import REGISTERED_MODELS, apply_schema_patches, seed_demo_merchant
from app.db.session import AsyncSessionLocal, engine

assert REGISTERED_MODELS  # tables are registered on Base.metadata by importing the models


async def reset(seed: bool) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TYPE IF EXISTS banglabot_order_status"))
        await conn.run_sync(Base.metadata.create_all)
        await apply_schema_patches(conn)
    if seed:
        async with AsyncSessionLocal() as session:
            await seed_demo_merchant(session)
    await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="really drop every table")
    parser.add_argument("--seed", action="store_true", help="seed the demo merchant afterwards")
    args = parser.parse_args()
    if not args.yes:
        print("Refusing to drop tables without --yes", file=sys.stderr)
        return 2
    asyncio.run(reset(seed=args.seed))
    print("database reset" + (" + demo data seeded" if args.seed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
