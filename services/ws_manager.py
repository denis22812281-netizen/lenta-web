import asyncio
from typing import Any

from fastapi import WebSocket


class ChatManager:
    def __init__(self):
        # room_key → [(ws, user_name)]
        self._rooms: dict[str, list[tuple[WebSocket, str]]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def room_key(name_a: str, name_b: str) -> str:
        """Ключ комнаты: general или упорядоченная пара имён."""
        if not name_b:
            return "general"
        return ":".join(sorted([name_a, name_b]))

    async def connect(self, ws: WebSocket, user_name: str, partner: str) -> None:
        await ws.accept()
        key = self.room_key(user_name, partner)
        async with self._lock:
            self._rooms.setdefault(key, []).append((ws, user_name))

    async def disconnect(self, ws: WebSocket, user_name: str, partner: str) -> None:
        key = self.room_key(user_name, partner)
        async with self._lock:
            self._rooms[key] = [
                (w, n) for w, n in self._rooms.get(key, []) if w is not ws
            ]

    async def broadcast(self, payload: dict[str, Any], sender: str, partner: str) -> None:
        """Отправить сообщение всем в комнате. Мёртвые соединения удаляются."""
        key = self.room_key(sender, partner)
        dead: list[tuple[WebSocket, str]] = []
        for ws, name in list(self._rooms.get(key, [])):
            try:
                await ws.send_json({**payload, "mine": name == sender})
            except Exception:
                dead.append((ws, name))
        if dead:
            async with self._lock:
                self._rooms[key] = [
                    (w, n) for w, n in self._rooms.get(key, [])
                    if (w, n) not in dead
                ]

    def connection_count(self) -> int:
        return sum(len(v) for v in self._rooms.values())


ws_manager = ChatManager()
