import asyncio
import socket
import webbrowser

from glob import glob
from itertools import count
from json import loads as json_loads
from os import environ
from pathlib import Path
from typing import Callable

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from mutagen import File
from spotipy import Spotify
from spotipy.exceptions import SpotifyException

from utils import DIRECTORY_PATH, HOST, PORT, SpotifyContext

REPEAT_STATES = {"Song": "track", "Enabled": "context", "Disabled": "off"}
LOCAL_ARTWORK_PATH = Path(DIRECTORY_PATH, "artwork.jpg")
STATIC_PATH = Path(DIRECTORY_PATH, "backend/templates/dist/static")
COVER_IMAGE_APIC_NAMES = ["APIC:", "data", "cov"]


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


def update_settings(
    app: web.Application, context: SpotifyContext, data: dict
) -> None:
    new_shuffle = data.get("shuffle_state")
    new_repeat = data.get("repeat_state")
    if new_shuffle:
        shuffle(context.spotify, {"state": new_shuffle})
        context.shuffle_state = new_shuffle
    if new_repeat:
        repeat(context.spotify, {"state": new_repeat})
        context.repeat_state = new_repeat


@routes.get("/credential_callback")
async def oauth_callback(request: web.Request) -> web.Response:
    """Called after the user has given their Spotify Client ID and Secret

    Args:
        request (web.Request)

    Returns:
        web.Response
    """
    app = request.app
    query = request.url.query
    # If somehow the user didn't supply the Client ID and Secret then error out
    if not {"client_id", "client_secret"}.issubset(query):
        return web.Response(body="Missing Credentials")

    creds = Credentials(
        client_id=query["client_id"],
        client_secret=query["client_id"],
    )

    spotify = await create_spotify(app, creds)
    if spotify is None:
        return web.Response(body="Authorization Error")

    return web.Response(
        body=jinja_env.get_template("logged_in.html").render(
            username=spotify.me().get("display_name", "UNKNOWN")
        ),
        content_type="text/html",
    )


track_funcs_no_data = {"pause": pause, "next": next_track, "previous": previous_track}

track_funcs_with_data = {
    "shuffle_state": shuffle,
    "repeat_state": repeat,
    "update": update_settings,
    "volume": volume,
    "local_folder": set_local_media_folder,
}


async def websocket_handler(
    app: web.Application, spotify: Spotify, request: web.Request
) -> None:
    """Handles messages from websocket connections

    Args:
        app (web.Application)
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
                    await handle_actions(
                        app, action, SimpleNamespace(**data.get("data", {}))
                    )
                except ConnectionResetError:
                    logger.info("Websocket Reset")
                    app["config"]["polyclients"].remove(ws)

        elif msg.type == aiohttp.WSMsgType.ERROR:
            logger.warning(f"ws connection closed with exception {ws.exception()}")
            app["config"]["poly_clients"].remove(ws)

    logger.warning(f"Client {request.url} connection closed")
        action = message.data.action

    if not action:
        return

    try:
        data = message.data.data
    except AttributeError:
        data = {}

    if action == "login":
        local_media_folder = data.get("local_folder")
        if data.get("client_id") and data.get("client_secret"):
            await on_connected(message.author, data)
        else:
            await request_spotify_credentials()

    if not sp:
        return

    if action == "volume":
        spotify.volume(data[_vol])
        return

    try:
        if func := track_funcs_with_data.get(action):
            func(data)
            return
        if func := track_funcs_no_data.get(action):
            func()
            return
    except SpotifyException as e:
        await broadcast(app, "error", command="play", msg=e.msg, reason=e.reason)
        logger.exception(e)

    if action == "logout":
        if os.path.exists(SPOTIFY_CACHE_DIR):
            os.remove(SPOTIFY_CACHE_DIR)
    elif action == "play":
        await play(app, spotify, current_conte0xt, data)
    elif action == "refresh_devices":
        await refresh_devices()
    elif action == "refresh_playlists":
        await refresh_playlists()
    elif action == "quit":
        for client in server.clients:
            await server.close(client)
            quit()


async def handle_actions(
    app: web.Application, action: str, data: SimpleNamespace
) -> None:
    bot = app["config"]["polybot"]

    match action:
        case "send_message":
            await send_message(bot, data.message)
        case "login_broadcaster":
            try:
                token = _config.broadcaster_token
                logger.info(f"Already have token: {token}")
                await setup_bot(app, token)
            except (AttributeError, KeyError) as e:
                logger.exception(e)
                logger.debug("Requesting login")
                await request_oauth()

        case "logout_broadcaster":
            await bot.close()
            app["config"]["polybot"] = None
            await broadcast(app, "broadcaster_logged_out")
        case "modify_stream":
            logger.debug(f"modify_stream({_config.broadcaster_token}, {data.__dict__})")
            await bot.broadcaster.modify_stream(
                _config.broadcaster_token, **data.__dict__
            )


async def request_oauth(endpoint: str = "broadcaster") -> None:
    url = authorize_url.with_query(
        client_id=creds.CLIENT_ID,
        redirect_uri=redirect_uri.with_path(f"{endpoint}_oauth_callback").human_repr(),
        scope=scopes,
        response_type="code",
        force_verify="true",
        state=uuid.uuid4().hex,
    )
    webbrowser.open(url.human_repr(), new=2)


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


async def setup_context(app: web.Application) -> None:
    """Runs just before the Applpication is instantiated,
    so we can setup any context variables

    Args:
        app (web.Application): Used for Application Context
    """
    app["spotify_context"] = await create_spotify()
    # Connected WebSocket Clients (Should be one and it should be PolyPop)
    app["clients"] = set[web.WebSocketResponse]()
    # Background Fetching for current Spotify state
    app["tasks"] = list[asyncio.Task]()


async def cleanup_context(app: web.Application) -> None:
    """Runs before program shutdown to gracefully close any active connections

    Args:
        app (web.Application): Used for Application Context
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
    app = web.Application(middlewares=[error_middleware])
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
