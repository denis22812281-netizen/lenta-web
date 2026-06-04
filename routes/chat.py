from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import templates, get_current_user, require_login
from services.online import ONLINE_USERS, ONLINE_TIMEOUT
from services.cloud_storage import upload_photo, media_url

router = APIRouter()


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
    return templates.TemplateResponse("chat.html", {
        "request": request, "user": user,
        "managers": managers, "partner": partner,
        "my_name": my_name, "unread_by": unread_by, "online_set": online_set,
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


@router.post("/api/chat/send")
async def chat_send(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return {"error": "Не авторизован"}
    data = await request.json()
    text = data.get("text", "").strip()
    if not text:
        return {"error": "Пустое сообщение"}
    msg = models.ChatMessage(
        sender_name=user.get("display_name", ""),
        receiver_name=data.get("partner", ""),
        text=text,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "time": msg.created_at.strftime("%H:%M")}


@router.post("/api/chat/send-photo")
async def chat_send_photo(request: Request, db: Session = Depends(get_db),
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
    stored = upload_photo(await file.read(), "chat", fname)  # noqa: chat photos are small
    msg = models.ChatMessage(
        sender_name=user.get("display_name", ""),
        receiver_name=partner, text=text or "",
        photo_path=stored,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "time": msg.created_at.strftime("%H:%M"), "photo": msg.photo_path}


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
