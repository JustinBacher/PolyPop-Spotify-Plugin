"""Module that serves as the backend service for PolyPop Spotify Plugin

Created by Jab/Jabbey92 for the Polypop Community to be able to
control spotify from within PolyPop itself

Todo:
    Get it working again

"""


from json import loads as json_loads  # Importing like this so there's one less lookup per request
import sys
from turtle import back
from typing import Callable, cast
from urllib import request

from aiohttp import WSMsgType, web
from aiohttp import WebSocketError, WSServerHandshakeError
from aiohttp import web_exceptions
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from spotipy import Spotify

from .utils.server import Server
from .utils.utils import DIRECTORY_PATH, HOST, PORT


# Create Logger
logger.add(DIRECTORY_PATH.joinpath("debug.log"), rotation="1 day", retention="5 days")

# Setup Routes and static file service
routes = web.RouteTableDef()
routes.static(prefix="/static", path=DIRECTORY_PATH.joinpath("static"))

# Create template renderer
jinja_env = Environment(
    loader=FileSystemLoader(DIRECTORY_PATH.joinpath("templates")),
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
    print(query)

    if not {"client-id", "client-secret"}.issubset(query):
        # If somehow the user didn't supply the Client ID and Secret then error out
        return web.Response(body="Missing Credentials")

    app = cast(Server, request.app)
    payload = await app.context.create_spotify(
        app, client_id=query["client-id"], client_secret=query["client-secret"]
    )

    spotify = cast(Spotify, app.context.spotify)

    if payload is None or spotify is None:
        return web.Response(body="Authorization Error")

    await app.broadcast(*payload)

    return web.Response(
        body=jinja_env.get_template("logged_in.html").render(
            username=spotify.me().get("display_name", "UNKNOWN")
        ),
        content_type="text/html",
    )


@routes.get("/ws")
async def websocket_handler(request: web.Request) -> web.Response:
    """Handles messages from websocket connections

    Args:
        app (Server)
        request (web.Request)
    """
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)
    app = cast(Server, request.app)
    app.clients.add(websocket)
    logger.info(f"Websocket connection established.")

    payload = await app.context.create_spotify(app)

    if payload is not None:
        await app.broadcast(*payload)

    async for payload in websocket:
        match payload.type:
            case WSMsgType.TEXT:
                logger.debug(f"Action: {payload}")
                try:
                    data = json_loads(payload.data)
                    if not isinstance(data, (list, tuple)):
                        raise ValueError
                except ValueError:
                    logger.warning(f"Failed to load message from websocket. Contents: {payload}")
                    continue

                logger.info(f"Data sent from websocket connection: {data}")

                try:
                    await handle_actions(app, data)
                except WSServerHandshakeError:
                    logger.warning("Error during websocket handshake")
                except ConnectionResetError:
                    logger.warning("Websocket connection reset")
                except WebSocketError as error:
                    logger.exception(error)
                finally:
                    app.clients.remove(websocket)

            case WSMsgType.ERROR:
                logger.warning(f"ws connection closed with exception {websocket.exception()}")
                app.clients.remove(websocket)

    logger.warning(f"Client {request.url} connection closed")
    return web.Response(body="Websocket Closed")


@routes.get("/")
async def homepage(request: web.Request) -> web.Response:
    return web.Response(body="PolyPop Spotify Plugin running")


@routes.get("/startup")
async def startup(request: web.Request) -> web.Response:  # pylint: disable=unused-argument
    """Renders the page for requesting the users credentials

    Args:
        request (web.Request): Request from the user

    Returns:
        web.Response: Rendered page
    """
    return web.Response(
        body=jinja_env.get_template("setup.html").render(),
        content_type="text/html",
    )


async def handle_actions(app: Server, payload: list | tuple) -> None:
    """Performs the actions sent to the websocket service

    Args:
        app (Server): Currently running server. Should not change
        data (dict): The data sent from the websocket service.
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
            logger.debug("Websocket received unknown information: {_}")
            return

    if response is not None:
        await app.broadcast(*response)


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
            case web_exceptions.HTTPNotFound:
                return web.Response(text="Custom 404 message", status=404)

            case _status:
                logger.exception(error)
                return web.Response(
                    text=("Oops, we encountered an error. Please check your URL."),
                    status=_status,
                )


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

    except SystemExit:
        logger.info("Server Shutdown Gracefully")

    except Exception as error:  # pylint: disable=broad-except
        logger.exception(error)
        sys.exit(1)
    finally:
        app.close()


if __name__ == "__main__":
    main()
