from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class PhoneWhitelist(Base):
    __tablename__ = "phone_whitelist"
    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100), default="")
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(100))
    is_admin = Column(Boolean, default=False)
    session_version = Column(Integer, default=1)
    last_seen = Column(DateTime, nullable=True)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WebAuthnCredential(Base):
    """Биометрические ключи пользователя (Face ID / Touch ID)."""
    __tablename__ = "webauthn_credentials"
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_id = Column(Text, unique=True, nullable=False)
    public_key    = Column(Text, nullable=False)
    sign_count    = Column(Integer, default=0)
    device_name   = Column(String(150), default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")
