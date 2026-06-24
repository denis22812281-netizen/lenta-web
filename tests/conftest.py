"""
Конфигурация pytest.
По умолчанию: SQLite (быстро, без зависимостей).
С TEST_DATABASE_URL=postgresql://... — тесты против реального PostgreSQL.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "")
os.environ["TESTING"] = "1"  # отключает CSRF в тестах

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401 — нужен чтобы Base.metadata знал все таблицы
from database import Base, get_db
from deps import limiter as _limiter

_limiter.enabled = False

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_lenta.db")
_is_sqlite = "sqlite" in TEST_DB_URL

if _is_sqlite:
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)   # чистый старт на каждый прогон
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if _is_sqlite:
        import pathlib
        import time
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
    app.dependency_overrides[get_db] = override_get_db


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
    import models
    import utils.passwords as pw

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
