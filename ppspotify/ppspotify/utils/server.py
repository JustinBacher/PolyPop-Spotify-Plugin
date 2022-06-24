"""Custom wrapper for `aiohttp.web.Application"""

import asyncio

from operator import methodcaller
from typing import Any

from aiohttp.web import Application, WebSocketResponse

from .utils import SpotifyContext


class Server(Application):
    """Custom wrapper for `aiohttp.web.Application"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients: set[WebSocketResponse] = set()
        self.context: SpotifyContext = SpotifyContext()
        self.tasks: list[asyncio.Task] = []

    async def broadcast(self, action: str, data: dict | None = None) -> None:
        """Sends a message to all connected clients.
        There should only be one client connected and it should be PolyPop,
        but just in case PolyPop retries connection and this client keeps an
        old connection alive for no reason we will broadcast it out to all connections

        Args:
            app (web.Application)
            action (str): The action to perform in PolyPop
            data (dict, optional): Data related to the action
        """
        for client in self.clients:
            if data:
                await client.send_json({"action": action, "data": data})
            else:
                await client.send_json({"action": action})

    def close(self):
        """Cleans up Server"""
        for task in self.tasks:
            task.cancel()

        self.context.close()
