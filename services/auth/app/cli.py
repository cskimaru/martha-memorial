"""Administrative commands.

    python -m app.cli create-owner --email you@example.com --name "Anita"

The password is read from the OWNER_PASSWORD environment variable or prompted.
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from memorial_common.db import Database

from .config import get_settings
from .models import User
from .passwords import hash_password


async def create_owner(email: str, name: str, password: str) -> int:
    settings = get_settings()
    if len(password) < settings.min_password_length:
        print(f"Password must be at least {settings.min_password_length} characters.", file=sys.stderr)
        return 2
    db = Database(settings.database_url)
    async with db.sessionmaker() as s:
        existing = (await s.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if existing:
            existing.roles = ",".join(sorted(set(existing.role_list) | {"owner"}))
            existing.is_active = True
            print(f"{email} already existed; owner role granted.")
        else:
            s.add(User(email=email.lower(), display_name=name, password_hash=hash_password(password), roles="owner"))
            print(f"Owner account created for {email}.")
        await s.commit()
    await db.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-owner")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    args = parser.parse_args()
    if args.cmd == "create-owner":
        pw = os.environ.get("OWNER_PASSWORD") or getpass.getpass("Password: ")
        return asyncio.run(create_owner(args.email, args.name, pw))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
