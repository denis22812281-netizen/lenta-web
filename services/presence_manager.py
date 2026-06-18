import asyncio
from fastapi import WebSocket


class PresenceManager:
    """Отслеживает кто сейчас смотрит ту же страницу — рассылает список зрителей."""

    def __init__(self):
        # page_key → [{"ws": ws, "name": str, "photo": str}]
        self._pages: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, page: str, name: str, photo: str) -> None:
        await ws.accept()
        async with self._lock:
            self._pages.setdefault(page, [])
            self._pages[page].append({"ws": ws, "name": name, "photo": photo})
        await self._broadcast(page)

    async def disconnect(self, ws: WebSocket, page: str) -> None:
        async with self._lock:
            self._pages[page] = [
                v for v in self._pages.get(page, []) if v["ws"] is not ws
            ]
        await self._broadcast(page)

    async def _broadcast(self, page: str) -> None:
        viewers = [
            {"name": v["name"], "photo": v["photo"]}
            for v in self._pages.get(page, [])
        ]
        dead: list[dict] = []
        for item in list(self._pages.get(page, [])):
            try:
                await item["ws"].send_json({"viewers": viewers})
            except Exception:
                dead.append(item)
        if dead:
            async with self._lock:
                self._pages[page] = [
                    v for v in self._pages.get(page, []) if v not in dead
                ]

    def page_count(self, page: str) -> int:
        return len(self._pages.get(page, []))


presence_manager = PresenceManager()
