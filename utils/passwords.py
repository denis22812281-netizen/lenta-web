import base64
import hashlib
import os


def hash_password(password: str) -> str:
    """PBKDF2-SHA256, 16-byte random salt. Format: base64(salt+key)."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 260_000)
    return base64.b64encode(salt + key).decode()


def verify_password(plain: str, stored: str) -> bool:
    """Verify PBKDF2 hash. Transparently accepts legacy SHA256 hashes (64 hex chars)."""
    if not stored:
        return False
    if _is_legacy_hash(stored):
        return hashlib.sha256(plain.encode('utf-8')).hexdigest() == stored
    try:
        raw = base64.b64decode(stored.encode())
        salt, key = raw[:16], raw[16:]
        check = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt, 260_000)
        return key == check
    except Exception:
        return False


def _is_legacy_hash(stored: str) -> bool:
    return bool(stored) and len(stored) == 64 and all(
        c in '0123456789abcdefABCDEF' for c in stored)
