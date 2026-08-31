"""Create named accounts for a customer to test with.

    uv run python -m scripts.make_accounts "Exodus & Co" exodusco.co.zw

Passwords are generated here and printed once. They are stored only as a
hash, so this output is the single copy — there is no way to read them back
out afterwards, only to reset them by running this again.

Existing accounts are left alone rather than silently given a new password:
somebody may already be using one.
"""

import secrets
import string
import sys

from sqlalchemy import select

import app.modules  # noqa: F401
from app.common.enums import UserRole
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.users.models import User

# One of each role, so whoever is evaluating can see that permissions actually
# do something rather than taking it on trust from a single admin login.
PEOPLE = [
    ("admin", UserRole.admin, "System Administrator"),
    ("pm", UserRole.project_manager, "Project Manager"),
    ("site", UserRole.site_manager, "Site Manager"),
    ("procurement", UserRole.procurement_officer, "Procurement Officer"),
    ("viewer", UserRole.viewer, "Read Only"),
]

# No ambiguous characters: these get read off a screen and typed on a phone,
# and l/1/I/O/0 cost more support time than they save entropy.
ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "lI1O0"
)


def generate() -> str:
    return "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3)
    )


def main() -> None:
    company = sys.argv[1] if len(sys.argv) > 1 else "Customer"
    domain = sys.argv[2] if len(sys.argv) > 2 else "example.com"

    db = SessionLocal()
    created, existing = [], []
    try:
        for handle, role, title in PEOPLE:
            email = f"{handle}@{domain}"
            if db.scalar(select(User).where(User.email == email)):
                existing.append(email)
                continue
            password = generate()
            db.add(
                User(
                    email=email,
                    full_name=f"{company} {title}",
                    hashed_password=hash_password(password),
                    role=role,
                    is_active=True,
                )
            )
            created.append((email, password, role.value))
        db.commit()
    finally:
        db.close()

    if created:
        print(f"\n{company} — sign in at the app URL\n")
        width = max(len(email) for email, _, _ in created)
        for email, password, role in created:
            print(f"  {email:<{width}}  {password}   ({role.replace('_', ' ')})")
        print("\nShown once. Only the hash is stored, so keep this or run again to reset.")
    if existing:
        print("\nAlready present, left untouched: " + ", ".join(existing))


if __name__ == "__main__":
    main()
