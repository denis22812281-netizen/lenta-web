"""WebAuthn — вход по Face ID / Touch ID / fingerprint."""
import base64
import json
import os

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user, require_login, limiter

router = APIRouter()

RP_NAME = "Лента PM"

def _rp_id(request: Request) -> str:
    """rpID должен совпадать с доменом. localhost в dev, домен Railway в prod."""
    env = os.getenv("APP_DOMAIN", "")
    if env:
        return env
    host = request.headers.get("host", "localhost").split(":")[0]
    return host


def _origin(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    scheme = forwarded_proto or request.url.scheme
    host = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "localhost")
    return f"{scheme}://{host}"


# ─── Страница настройки ───────────────────────────────────────────────────────

@router.get("/webauthn/setup", response_class=HTMLResponse)
async def webauthn_setup(request: Request, db: Session = Depends(get_db),
                         user: dict = Depends(require_login)):
    creds = db.query(models.WebAuthnCredential).filter(
        models.WebAuthnCredential.user_id == user["id"]).all()
    return templates.TemplateResponse("webauthn_setup.html", {
        "request": request, "user": user, "credentials": creds,
    })


# ─── Регистрация: шаг 1 — получить параметры ─────────────────────────────────

@router.get("/webauthn/register/begin")
async def register_begin(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    try:
        from webauthn import generate_registration_options
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            UserVerificationRequirement,
            ResidentKeyRequirement,
        )
        from webauthn.helpers import options_to_json

        db_user = db.query(models.User).filter(models.User.id == user["id"]).first()
        existing = db.query(models.WebAuthnCredential).filter(
            models.WebAuthnCredential.user_id == user["id"]).all()

        from webauthn.helpers import base64url_to_bytes as _b64u
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
        exclude_creds = [
            PublicKeyCredentialDescriptor(id=_b64u(c.credential_id))
            for c in existing
        ]

        options = generate_registration_options(
            rp_id=_rp_id(request),
            rp_name=RP_NAME,
            user_id=str(user["id"]).encode(),
            user_name=db_user.phone,
            user_display_name=db_user.display_name or db_user.phone,
            exclude_credentials=exclude_creds,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )

        # Сохраняем challenge в сессии для проверки на шаге 2
        request.session["webauthn_reg_challenge"] = base64.b64encode(
            options.challenge).decode()

        return JSONResponse(json.loads(options_to_json(options)))

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Регистрация: шаг 2 — подтвердить ────────────────────────────────────────

@router.post("/webauthn/register/complete")
async def register_complete(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    challenge_b64 = request.session.pop("webauthn_reg_challenge", None)
    if not challenge_b64:
        return JSONResponse({"error": "Challenge истёк"}, status_code=400)

    try:
        from webauthn import verify_registration_response
        from webauthn.helpers import base64url_to_bytes
        from webauthn.helpers.structs import (
            RegistrationCredential, AuthenticatorAttestationResponse)

        body = await request.json()
        device_name = body.pop("device_name", "")

        resp = body.get("response", {})
        credential = RegistrationCredential(
            id=body["id"],
            raw_id=base64url_to_bytes(body["rawId"]),
            response=AuthenticatorAttestationResponse(
                client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
                attestation_object=base64url_to_bytes(resp["attestationObject"]),
                transports=resp.get("transports"),
            ),
        )
        challenge = base64.b64decode(challenge_b64)

        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
        )

        cred_id_b64 = base64.urlsafe_b64encode(
            verification.credential_id).decode().rstrip("=")
        pub_key_b64 = base64.b64encode(
            verification.credential_public_key).decode()

        # Проверяем что такого credential ещё нет
        if db.query(models.WebAuthnCredential).filter(
                models.WebAuthnCredential.credential_id == cred_id_b64).first():
            return JSONResponse({"error": "Уже зарегистрировано"}, status_code=409)

        db.add(models.WebAuthnCredential(
            user_id=user["id"],
            credential_id=cred_id_b64,
            public_key=pub_key_b64,
            sign_count=verification.sign_count,
            device_name=device_name or _guess_device(request),
        ))
        db.commit()
        return JSONResponse({"ok": True})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ─── Аутентификация: шаг 1 — получить параметры ──────────────────────────────

@router.post("/webauthn/auth/begin")
@limiter.limit("5/minute")
async def auth_begin(request: Request, db: Session = Depends(get_db)):
    try:
        body  = await request.json()
        phone = body.get("phone", "")

        from utils.phone import normalize_phone
        normalized = normalize_phone(phone)
        db_user = db.query(models.User).filter(models.User.phone == normalized).first()
        if not db_user:
            return JSONResponse({"error": "Пользователь не найден"}, status_code=404)

        creds = db.query(models.WebAuthnCredential).filter(
            models.WebAuthnCredential.user_id == db_user.id).all()
        if not creds:
            return JSONResponse({"error": "Биометрия не настроена"}, status_code=404)

        from webauthn import generate_authentication_options
        from webauthn.helpers import base64url_to_bytes as _b64u, options_to_json
        from webauthn.helpers.structs import (
            PublicKeyCredentialDescriptor,
            UserVerificationRequirement,
        )

        allow_creds = [
            PublicKeyCredentialDescriptor(id=_b64u(c.credential_id))
            for c in creds
        ]

        options = generate_authentication_options(
            rp_id=_rp_id(request),
            allow_credentials=allow_creds,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        request.session["webauthn_auth_challenge"] = base64.b64encode(
            options.challenge).decode()
        request.session["webauthn_auth_phone"] = normalized

        return JSONResponse(json.loads(options_to_json(options)))

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Аутентификация: шаг 2 — проверить подпись ───────────────────────────────

@router.post("/webauthn/auth/complete")
@limiter.limit("5/minute")
async def auth_complete(request: Request, db: Session = Depends(get_db)):
    challenge_b64 = request.session.pop("webauthn_auth_challenge", None)
    phone         = request.session.pop("webauthn_auth_phone", None)
    if not challenge_b64 or not phone:
        return JSONResponse({"error": "Challenge истёк"}, status_code=400)

    try:
        from webauthn import verify_authentication_response
        from webauthn.helpers import base64url_to_bytes
        from webauthn.helpers.structs import (
            AuthenticationCredential, AuthenticatorAssertionResponse)

        body = await request.json()
        resp = body.get("response", {})
        uh   = resp.get("userHandle")
        credential = AuthenticationCredential(
            id=body["id"],
            raw_id=base64url_to_bytes(body["rawId"]),
            response=AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
                authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
                signature=base64url_to_bytes(resp["signature"]),
                user_handle=base64url_to_bytes(uh) if uh else None,
            ),
        )
        challenge = base64.b64decode(challenge_b64)

        raw_cred_id = base64.urlsafe_b64encode(
            credential.raw_id).decode().rstrip("=")

        db_cred = db.query(models.WebAuthnCredential).filter(
            models.WebAuthnCredential.credential_id == raw_cred_id).first()
        if not db_cred:
            return JSONResponse({"error": "Ключ не найден"}, status_code=404)

        pub_key = base64.b64decode(db_cred.public_key)

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
            credential_public_key=pub_key,
            credential_current_sign_count=db_cred.sign_count,
        )

        # Обновляем счётчик (защита от replay-атак)
        db_cred.sign_count = verification.new_sign_count
        db.commit()

        # Логиним пользователя (завершает и обычный вход, и 2FA)
        db_user = db_cred.user
        request.session.pop("pending_2fa", None)
        request.session["user"] = {
            "id": db_user.id,
            "username": db_user.username,
            "display_name": db_user.display_name,
            "is_admin": db_user.is_admin,
            "phone": db_user.phone,
        }
        return JSONResponse({"ok": True})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ─── Удалить credential ───────────────────────────────────────────────────────

@router.post("/webauthn/credentials/{cred_id}/delete")
async def delete_credential(cred_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    cred = db.query(models.WebAuthnCredential).filter(
        models.WebAuthnCredential.id == cred_id,
        models.WebAuthnCredential.user_id == user["id"],
    ).first()
    if cred:
        db.delete(cred)
        db.commit()
    return JSONResponse({"ok": True})


# ─── Проверить наличие биометрии для телефона ─────────────────────────────────

@router.post("/webauthn/check")
async def check_webauthn(request: Request, db: Session = Depends(get_db)):
    """Возвращает True если у пользователя с этим телефоном есть WebAuthn-ключи."""
    try:
        body  = await request.json()
        phone = body.get("phone", "")
        from utils.phone import normalize_phone
        normalized = normalize_phone(phone)
        db_user = db.query(models.User).filter(models.User.phone == normalized).first()
        if not db_user:
            return JSONResponse({"has_webauthn": False})
        count = db.query(models.WebAuthnCredential).filter(
            models.WebAuthnCredential.user_id == db_user.id).count()
        return JSONResponse({"has_webauthn": count > 0})
    except Exception:
        return JSONResponse({"has_webauthn": False})


def _guess_device(request: Request) -> str:
    ua = request.headers.get("user-agent", "").lower()
    if "iphone" in ua:    return "iPhone"
    if "ipad" in ua:      return "iPad"
    if "mac" in ua:       return "Mac"
    if "android" in ua:   return "Android"
    if "windows" in ua:   return "Windows"
    return "Устройство"
