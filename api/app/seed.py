"""
One-time bootstrap for the first super admin, since every other account is
normally created through an invite that only an existing admin can send.

Run inside the api container:
    docker compose exec api python -m app.seed
"""

from .config import settings
from .database import SessionLocal, init_db
from .models import Role, User
from .security import hash_password


def main() -> None:
    if not settings.seed_super_admin_email or not settings.seed_super_admin_password:
        raise SystemExit("Set SEED_SUPER_ADMIN_EMAIL and SEED_SUPER_ADMIN_PASSWORD in .env first.")

    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.seed_super_admin_email).one_or_none()
        if existing:
            print(f"{settings.seed_super_admin_email} already exists - nothing to do.")
            return

        user = User(
            email=settings.seed_super_admin_email,
            display_name="Super Admin",
            role=Role.super_admin,
            password_hash=hash_password(settings.seed_super_admin_password),
        )
        db.add(user)
        db.commit()
        print(f"Created super admin: {settings.seed_super_admin_email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
