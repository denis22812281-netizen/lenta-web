from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.presence_manager import presence_manager

router = APIRouter()


@router.websocket("/ws/presence")
async def presence_ws(websocket: WebSocket, page: str = ""):
    """WebSocket: рассылает список зрителей текущей страницы."""
    session = dict(websocket.scope.get("session", {}))
    user = session.get("user")
    if not user:
        await websocket.close(code=4001)
        return

    name = user.get("display_name", "")
    photo = user.get("photo", "")
    page_key = page or "/"

    await presence_manager.connect(websocket, page_key, name, photo)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        await presence_manager.disconnect(websocket, page_key)
