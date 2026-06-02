"""
Конфигурация pytest.
Использует SQLite in-memory — не нужен Railway/PostgreSQL.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db

TEST_DB_URL = "sqlite:///./test_lenta.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    import pathlib
    pathlib.Path("test_lenta.db").unlink(missing_ok=True)


@pytest.fixture
def client():
    from main import app
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client):
    """Клиент с авторизованной сессией (Месмер Денис, admin)."""
    from tests.conftest import TestingSessionLocal
    import models, utils.passwords as pw

    db = TestingSessionLocal()
    # Добавляем телефон в whitelist
    phone = "+79997303914"
    if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
        db.add(models.PhoneWhitelist(phone=phone, display_name="Месмер Денис", is_admin=True))
        db.commit()
    # Создаём пользователя
    user = db.query(models.User).filter_by(phone=phone).first()
    if not user:
        user = models.User(
            phone=phone, username=phone,
            password_hash=pw.hash_password("test1234"),
            display_name="Месмер Денис", is_admin=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()

    # Логинимся
    client.post("/login/check-phone", data={"phone": phone})
    client.post("/login/enter", data={"phone": phone, "password": "test1234"})
    return client
