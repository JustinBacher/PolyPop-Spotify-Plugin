import sys

from json import loads as json_loads
from pathlib import Path
from typing import Callable, cast

import aiohttp

from aiohttp import WSMsgType, web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from server import Server
from utils import DIRECTORY_PATH, HOST, PORT

STATIC_PATH = Path(DIRECTORY_PATH, "backend/templates/dist/static")

logger.add(Path(DIRECTORY_PATH, "debug.log"), rotation="1 day", retention="5 days")
routes = web.RouteTableDef()
routes.static("/static/", STATIC_PATH)
jinja_env = Environment(
    loader=FileSystemLoader(Path(DIRECTORY_PATH, "backend/templates/dist")),
    autoescape=select_autoescape(),
)


@routes.get("/credential_callback")
async def oauth_callback(request: web.Request) -> web.Response:
    """Called after the user has given their Spotify Client ID and Secret

    Args:
        request (web.Request)

    Returns:
        web.Response
    """
    query = request.url.query

    if not {"client_id", "client_secret"}.issubset(query):
        # If somehow the user didn't supply the Client ID and Secret then error out
        return web.Response(body="Missing Credentials")

    app = cast(Server, request.app)
    payload = await app.context.create_spotify()
    spotify = app.context.spotify

    if payload is None or spotify is None:
        return web.Response(body="Authorization Error")

    return web.Response(
        body=jinja_env.get_template("logged_in.html").render(
            username=spotify.me().get("display_name", "UNKNOWN")
        ),
        content_type="text/html",
    )


async def websocket_handler(app: Server, request: web.Request) -> None:
    """Handles messages from websocket connections

    Args:
        app (Server)
        request (web.Request)
    """
    websocket = web.WebSocketResponse()

    await websocket.prepare(request)

    async for payload in websocket:
        match payload.type:
            case WSMsgType.TEXT:
                try:
                    data = json_loads(payload.data)
                    logger.debug(f"Action: {payload}")

                    if not isinstance(data, (list, tuple)):
                        raise ValueError

                except ValueError:
                    logger.debug(f"failed to load message from websocket. Contents: {payload}")
                    continue

                try:
                    await handle_actions(app, data)

                except ConnectionResetError:
                    logger.info("Websocket Reset")
                    app.clients.remove(websocket)

            case aiohttp.WSMsgType.ERROR:
                logger.warning(f"ws connection closed with exception {websocket.exception()}")
                app.clients.remove(websocket)

    logger.warning(f"Client {request.url} connection closed")


async def handle_actions(app: Server, payload: list | tuple) -> None:
    """Performs the actions sent to the websocket service

    Args:
        app (Server)
        data (dict)
    """
    match payload:

        case ["login", *_]:
            response = app.context.request_credentials_from_user()

        case ["logout", *_]:
            response = app.context.logout()

        case ["play", data]:
            response = await app.context.play(data)

        case ["refresh_devices", *_]:
            response = await app.context.refresh_devices()

        case ["refresh_playlists", *_]:
            response = await app.context.refresh_playlists()

        case ["pause", *_]:
            if app.context.spotify is None:
                return

            response = app.context.spotify.pause_playback()

        case ["next", *_]:
            if app.context.spotify is None:
                return

            response = app.context.spotify.next_track()

        case ["previous", *_]:
            if app.context.spotify is None:
                return

            response = app.context.spotify.previous_track()

        case ["get_devices", *_]:
            response = app.context.get_devices()

        case ["update", data]:
            response = app.context.update_settings(data)

        case ["quit", *_]:
            for client in app.clients:
                await client.close()
            sys.exit()

        case _:
            response = None

    if response is not None:
        if len(response) == 1:
            await app.broadcast(response[0])
            return

        await app.broadcast(response[0], **response[1])

@web.middleware
async def error_middleware(request: web.Request, handler: Callable) -> web.Response:
    """Handles Routing errors and serves custom error pages.

    Args:
        request (web.Request): The request made by the user
        handler (Callable): The function provided by the original router

    Returns:
        web.Response: Either the intended response or a custom error response in lue of vanity
    """
    try:
        return await handler(request)

    except web.HTTPException as error:
        match error.status:
            case 404:
                return web.Response(text="Custom 404 message", status=404)

            case status:
                return web.Response(
                    text=(
                        "Oops, we encountered an error. Please check your URL."
                    ),
                    status=status
                )

        logger.exception(error)

async def cleanup_context(app: Server) -> None:
    """Runs before program shutdown to gracefully close any active connections

    Args:
        app (Server): Used for Application Context
    """
    app.context.close()

def main() -> None:  # pylint: disable=missing-function-docstring
    app = Server(middlewares=[error_middleware])
    app.add_routes(routes)
    app.on_cleanup.append(cleanup_context)  # type: ignore

    try:
        web.run_app(app, host=HOST, port=PORT)
    except Exception as error: # pylint: disable=broad-except
        logger.exception(error)
        sys.exit(1)

if __name__ == "__main__":
    main()
