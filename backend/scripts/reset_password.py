"""
Reset a user's password directly against the database.

An admin recovery tool, not an API endpoint - it deliberately requires shell
access to the server. There is no self-service password reset in the app, which
is noted as a known limitation in the README.

    python -m scripts.reset_password you@example.com newPassword123
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import connect_to_mongo, close_mongo_connection  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User, utcnow  # noqa: E402


async def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.reset_password <email> <new_password>")
        return 1

    email, new_password = sys.argv[1].lower().strip(), sys.argv[2]

    if len(new_password) < 8 or not any(c.isdigit() for c in new_password):
        print("Password must be at least 8 characters and contain a digit.")
        return 1

    await connect_to_mongo()
    try:
        user = await User.find_one(User.email == email)
        if user is None:
            print(f"No account found for '{email}'. Registered accounts:")
            for existing in await User.find_all().to_list():
                print(f"  {existing.email}  ({existing.role.value})")
            return 1

        user.password_hash = hash_password(new_password)
        user.updated_at = utcnow()
        await user.save()
        print(f"Password reset for {user.email} ({user.role.value}).")
        return 0
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
