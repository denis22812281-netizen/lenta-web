from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, Form, Depends, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from services.ws_manager import ws_manager
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user, require_login
from services.online import ONLINE_USERS, ONLINE_TIMEOUT
from services.cloud_storage import upload_photo, upload_audio, media_url

router = APIRouter()


def _push_chat(db, sender: str, receiver: str, preview: str):
    """Отправить push о новом сообщении в фоне."""
    from services.push_service import notify_user, notify_all, is_configured
    if not is_configured():
        return
    title = f"💬 {sender}"
    body = preview[:80] if preview else "Новое сообщение"
    url = f"/chat?partner={sender}"
    if receiver:
        notify_user(db, receiver, title, body, url)
    else:
        # Общий чат — всем кроме отправителя
        import models as _m
        subs = db.query(_m.PushSubscription).filter(
            _m.PushSubscription.user_name != sender
        ).all()
        from services.push_service import send_push
        expired = []
        for sub in subs:
            result = send_push(sub, title, body, "/chat")
            if result is None:
                expired.append(sub)
        for sub in expired:
            db.delete(sub)
        if expired:
            db.commit()


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db), partner: str = "",
                    user: dict = Depends(require_login)):
    _order = [
        "Месмер Денис", "Митько Роберт", "Ловчиков Александр",
        "Валеев Борис", "Косило Сергей", "Студеникин Сергей",
        "Хачатурова Жанна", "Шевченко Наталья",
    ]
    managers = db.query(models.Manager).all()
    managers.sort(key=lambda m: (
        0 if m.is_leader else 1,
        _order.index(m.name) if m.name in _order else 99
    ))
    my_name = user.get("display_name", "")
    unread_by: dict = {}
    for m in db.query(models.ChatMessage).filter(
            models.ChatMessage.receiver_name == my_name,
            models.ChatMessage.is_read == False).all():
        unread_by[m.sender_name] = unread_by.get(m.sender_name, 0) + 1
    now = datetime.utcnow()
    online_set = {
        name for name, ts in ONLINE_USERS.items()
        if (now - ts).total_seconds() < ONLINE_TIMEOUT
    }
    in_chat = "partner" in request.query_params
    return templates.TemplateResponse("chat.html", {
        "request": request, "user": user,
        "managers": managers, "partner": partner,
        "my_name": my_name, "unread_by": unread_by, "online_set": online_set,
        "in_chat": in_chat,
    })


@router.get("/api/chat/messages")
async def chat_messages(request: Request, db: Session = Depends(get_db),
                        partner: str = "", since_id: int = 0):
    user = get_current_user(request)
    if not user:
        return {"messages": []}
    my_name = user.get("display_name", "")
    if partner == "":
        q = db.query(models.ChatMessage).filter(
            models.ChatMessage.receiver_name == "",
            models.ChatMessage.id > since_id)
    else:
        q = db.query(models.ChatMessage).filter(
            models.ChatMessage.id > since_id,
            or_(
                and_(models.ChatMessage.sender_name == my_name,
                     models.ChatMessage.receiver_name == partner),
                and_(models.ChatMessage.sender_name == partner,
                     models.ChatMessage.receiver_name == my_name),
            ))
        db.query(models.ChatMessage).filter(
            models.ChatMessage.sender_name == partner,
            models.ChatMessage.receiver_name == my_name,
            models.ChatMessage.is_read == False,
        ).update({"is_read": True})
        db.commit()
    msgs = q.order_by(models.ChatMessage.id).limit(200).all()
    return {"messages": [
        {"id": m.id, "sender": m.sender_name, "text": m.text,
         "photo": media_url(m.photo_path) if m.photo_path else "",
         "time": m.created_at.strftime("%H:%M"),
         "mine": m.sender_name == my_name}
        for m in msgs
    ]}


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket, partner: str = ""):
    """WebSocket: держим соединение открытым, push приходит через ws_manager.broadcast."""
    # Сессия доступна через scope (SessionMiddleware обрабатывает WS)
    session = dict(websocket.scope.get("session", {}))
    user = session.get("user")
    if not user:
        await websocket.close(code=4001)
        return
    my_name = user.get("display_name", "")
    await ws_manager.connect(websocket, my_name, partner)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, my_name, partner)


@router.post("/api/chat/send")
async def chat_send(request: Request, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    data = await request.json()
    text = data.get("text", "").strip()
    if not text:
        return {"error": "Пустое сообщение"}
    sender = user.get("display_name", "")
    receiver = data.get("partner", "")
    msg = models.ChatMessage(sender_name=sender, receiver_name=receiver, text=text)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = {
        "id": msg.id, "sender": sender, "text": text,
        "photo": "", "time": msg.created_at.strftime("%H:%M"),
    }
    await ws_manager.broadcast(payload, sender, receiver)
    background_tasks.add_task(_push_chat, db, sender, receiver, text)
    return {"id": msg.id, "time": msg.created_at.strftime("%H:%M")}


@router.post("/api/chat/send-photo")
async def chat_send_photo(request: Request, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db),
                          file: UploadFile = File(...),
                          partner: str = Form(""), text: str = Form("")):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        ext = '.jpg'
    fname = (f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_"
             f"{user.get('display_name','u').replace(' ','_')}{ext}")
    stored = upload_photo(await file.read(), "chat", fname)
    sender = user.get("display_name", "")
    msg = models.ChatMessage(sender_name=sender, receiver_name=partner,
                             text=text or "", photo_path=stored)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = {
        "id": msg.id, "sender": sender, "text": text or "",
        "photo": stored or "", "time": msg.created_at.strftime("%H:%M"),
    }
    await ws_manager.broadcast(payload, sender, partner)
    background_tasks.add_task(_push_chat, db, sender, partner, text or "📷 Фото")
    return {"id": msg.id, "time": msg.created_at.strftime("%H:%M"), "photo": msg.photo_path}


@router.post("/api/chat/send-voice")
async def chat_send_voice(request: Request, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db),
                          file: UploadFile = File(...),
                          partner: str = Form("")):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    ext = Path(file.filename).suffix.lower() if file.filename else ".webm"
    if ext not in ('.webm', '.ogg', '.mp3', '.wav', '.m4a'):
        ext = '.webm'
    fname = (f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_"
             f"{user.get('display_name','u').replace(' ','_')}{ext}")
    stored = upload_audio(await file.read(), "voice", fname)
    sender = user.get("display_name", "")
    msg = models.ChatMessage(sender_name=sender, receiver_name=partner,
                             text="", photo_path=stored)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = {
        "id": msg.id, "sender": sender, "text": "",
        "photo": stored, "time": msg.created_at.strftime("%H:%M"),
        "is_voice": True,
    }
    await ws_manager.broadcast(payload, sender, partner)
    background_tasks.add_task(_push_chat, db, sender, partner, "🎤 Голосовое сообщение")
    return {"id": msg.id, "time": msg.created_at.strftime("%H:%M"), "photo": stored}


@router.get("/api/chat/unread")
async def chat_unread(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"total": 0}
    my_name = user.get("display_name", "")
    total = db.query(models.ChatMessage).filter(
        models.ChatMessage.receiver_name == my_name,
        models.ChatMessage.is_read == False,
    ).count()
    return {"total": total}
