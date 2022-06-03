"""Custom wrapper for `aiohttp.web.Application"""

import asyncio

from operator import methodcaller

from aiohttp.web import Application, WebSocketResponse

from .utils import SpotifyContext


class Server(Application):
    """Custom wrapper for `aiohttp.web.Application"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = set[WebSocketResponse]()
        self.context = SpotifyContext()
        self.tasks = list[asyncio.Task]()

    async def broadcast(self, payload: str | tuple) -> None:
        """Sends a message to all connected clients.
        There should only be one client connected and it should be PolyPop,
        but just in case PolyPop retries connection and this client keeps an
        old connection alive for no reason we will broadcast it out to all connections

        Args:
            app (web.Application)
            action (str): The action to perform in PolyPop
            data (dict, optional): Data related to the action
        """
        to_send = methodcaller(
            "send_str" if isinstance(payload, str) else "send_json",
            payload
        )
        for client in self.clients:
            await to_send(client)
