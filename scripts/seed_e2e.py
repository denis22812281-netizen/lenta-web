"""Seed a test user for E2E CI runs.

Usage:
    DATABASE_URL=sqlite:///./e2e_test.db python scripts/seed_e2e.py
"""
import os
import sys

# Must be set before any app imports
os.environ.setdefault("DATABASE_URL", "sqlite:///./e2e_test.db")
os.environ.setdefault("SECRET_KEY", "e2e-ci-test-secret-key")
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from utils.passwords import hash_password  # noqa: E402

Base.metadata.create_all(bind=engine)

PHONE = os.getenv("PLAYWRIGHT_PHONE", "+79997303914")
PASSWORD = os.getenv("PLAYWRIGHT_PASSWORD", "test1234")

db = SessionLocal()
try:
    if not db.query(models.PhoneWhitelist).filter_by(phone=PHONE).first():
        db.add(models.PhoneWhitelist(phone=PHONE, display_name="Месмер Денис", is_admin=True))
        db.commit()

    if not db.query(models.User).filter_by(phone=PHONE).first():
        db.add(models.User(
            phone=PHONE,
            username=PHONE,
            password_hash=hash_password(PASSWORD),
            display_name="Месмер Денис",
            is_admin=True,
        ))
        db.commit()
    print(f"[seed_e2e] OK — user {PHONE} ready")
finally:
    db.close()
