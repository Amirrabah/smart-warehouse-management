import os
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def create_admin(db, name: str, email: str, password: str) -> bool:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        return False
    db.add(
        User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
        )
    )
    db.commit()
    return True


def main() -> None:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    name = os.environ.get("ADMIN_NAME", "Admin")

    if not email or not password:
        sys.exit("Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables first.")
    if len(password) < 8:
        sys.exit("ADMIN_PASSWORD must be at least 8 characters.")

    with SessionLocal() as db:
        if create_admin(db, name, email, password):
            print(f"Admin created: {email}")
        else:
            print(f"User already exists: {email} (nothing changed)")


if __name__ == "__main__":
    main()