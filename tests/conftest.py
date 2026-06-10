"""
Конфигурация pytest.
Использует SQLite — не нужен Railway/PostgreSQL.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "")
os.environ["TESTING"] = "1"  # отключает CSRF-проверку в тестах

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models  # noqa: F401 — must import so Base.metadata knows all tables
from deps import limiter as _limiter
_limiter.enabled = False  # отключаем rate-limit глобально для тестов

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
    engine.dispose()
    import pathlib, time
    for _ in range(5):
        try:
            pathlib.Path("test_lenta.db").unlink(missing_ok=True)
            break
        except PermissionError:
            time.sleep(0.5)


@pytest.fixture
def client():
    from main import app
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides[get_db] = override_get_db  # keep override active


@pytest.fixture(scope="session")
def _session_app():
    """Единый app+client на всю сессию — для auth_client."""
    from main import app
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def auth_client(_session_app, setup_test_db):
    """Клиент с авторизованной сессией (Месмер Денис, admin). Создаётся один раз."""
    import models, utils.passwords as pw

    db = TestingSessionLocal()
    phone = "+79997303914"
    if not db.query(models.PhoneWhitelist).filter_by(phone=phone).first():
        db.add(models.PhoneWhitelist(phone=phone, display_name="Месмер Денис", is_admin=True))
        db.commit()
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

    _session_app.post("/login/check-phone", data={"phone": phone})
    _session_app.post("/login/enter", data={"phone": phone, "password": "test1234"})
    return _session_app
