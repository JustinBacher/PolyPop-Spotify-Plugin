import asyncio
import webbrowser

from json import loads as json_loads
from pathlib import Path
from typing import Callable, cast

import aiohttp

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from spotipy import Spotify
from spotipy.exceptions import SpotifyException

from server import Server
from utils import (
    CREDENTIALS_PATH,
    DIRECTORY_PATH,
    HOST,
    PORT,
    LOCAL_ARTWORK_PATH,
    Server,
    CredentialsManager,
    SpotifyContext,
)

STATIC_PATH = Path(DIRECTORY_PATH, "backend/templates/dist/static")


logger.add(Path(DIRECTORY_PATH, "debug.log"), rotation="1 day", retention="5 days")
routes = web.RouteTableDef()
routes.static("/static/", STATIC_PATH)
jinja_env = Environment(
    loader=FileSystemLoader(Path(DIRECTORY_PATH, "backend/templates/dist")),
    autoescape=select_autoescape(),
)


# -------------------------------------------------------------------------------------
#                                   Spotify Methods
# -------------------------------------------------------------------------------------


@routes.get("/credential_callback")
async def oauth_callback(request: web.Request) -> web.Response:
    """Called after the user has given their Spotify Client ID and Secret

    Args:
        request (web.Request)

    Returns:
        web.Response
    """
    app = cast(Server, request.app)
    query = request.url.query
    # If somehow the user didn't supply the Client ID and Secret then error out
    if not {"client_id", "client_secret"}.issubset(query):
        return web.Response(body="Missing Credentials")

    creds = CredentialsManager.load()

    spotify = await SpotifyContext.create_spotify(app)
    if spotify is None:
        return web.Response(body="Authorization Error")

    return web.Response(
        body=jinja_env.get_template("logged_in.html").render(
            username=spotify.me().get("display_name", "UNKNOWN")
        ),
        content_type="text/html",
    )


async def websocket_handler(
    app: Server, spotify: Spotify, request: web.Request
) -> None:
    """Handles messages from websocket connections

    Args:
        app (Server)
        spotify (Spotify)
        request (web.Request)
    """
    ws = web.WebSocketResponse()

    await ws.prepare(request)

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json_loads(msg.data)
            action = data["action"]

            if action == "close":
                await ws.close()
            else:
                logger.debug(f"Action: {action}")
                try:
                    await handle_actions(app, data)
                except ConnectionResetError:
                    logger.info("Websocket Reset")
                    app["config"]["polyclients"].remove(ws)

        elif msg.type == aiohttp.WSMsgType.ERROR:
            logger.warning(f"ws connection closed with exception {ws.exception()}")
            app.clients.remove(ws)

    logger.warning(f"Client {request.url} connection closed")


async def handle_actions(app: Server, data: dict) -> None:
    match data:
        case "login":
            app.context.login()

        case "volume", vol:
            app.context.volume(data[vol])
            return

        case "logout":
            app.context.credentials_manager.logout()
        case "play", data:
            await app.context.play(data)
        case "refresh_devices":
            await app.context.refresh_devices()
        case "refresh_playlists":
            await app.context.refresh_playlists()
        case "quit":
            for client in app.clients:
                try:
                    await client.close()
                finally:
                    quit()


@web.middleware
async def error_middleware(request: web.Request, handler: Callable) -> web.Response:
    try:
        response = await handler(request)
        # this is needed to handle ``return web.HTTPNotFound()`` case
        if response.status == 404:
            return web.Response(text="First custom 404 message", status=404)
        return response
    except web.HTTPException as ex:
        # this is needed to handle ``raise web.HTTPNotFound()`` case
        if ex.status == 404:
            return web.Response(text="Second custom 404 message", status=404)
        raise
    # this is needed to handle non-HTTPException
    except Exception as e:
        logger.exception(e)
        return web.Response(text="Oops, something went wrong", status=500)


async def setup_context(app: Server) -> None:
    """Runs just before the Applpication is instantiated,
    so we can setup any context variables

    Args:
        app (Server): Used for Application Context
    """
    app["spotify_context"] = await app.context.create_spotify(app)
    # Connected WebSocket Clients (Should be one and it should be PolyPop)
    app["clients"] = set[web.WebSocketResponse]()
    # Background Fetching for current Spotify state
    app["tasks"] = list[asyncio.Task]()


async def cleanup_context(app: Server) -> None:
    """Runs before program shutdown to gracefully close any active connections

    Args:
        app (Server): Used for Application Context
    """

    # Shutdown Spotify
    await app["spotify"].close()
    # close any clients
    for client in app["clients"]:
        await client.close()
    # Stop any running tasks
    for task in app["tasks"]:
        task.cancel()


def main() -> None:
    """Main Program... duh"""
    app = Server(middlewares=[error_middleware])
    app.add_routes(routes)
    app.on_startup.append(setup_context)
    app.on_cleanup.append(cleanup_context)

    while True:
        # Using try here so we can attempt to keep the program running in
        # the background no matter what
        try:
            web.run_app(app, host=HOST, port=PORT)
        except Exception as e:  # noqa: Kepp it movin... Nothing to see here!
            logger.exception(e)

    logger.info("Server closed gracefully")


if __name__ == "__main__":
    main()
