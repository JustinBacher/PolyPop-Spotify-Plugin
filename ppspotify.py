import asyncio
import socket
import webbrowser

from collections import namedtuple
from dataclasses import asdict, dataclass
from glob import glob
from itertools import count
from os import environ
from json import dumps as json_dumps, loads as json_loads
from pathlib import Path
from typing import Awaitable, Callable, cast

from aiofiles import open as aio_open
from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from mutagen import File
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
from spotipy.exceptions import SpotifyException
from spotipy.cache_handler import CacheFileHandler


REPEAT_STATES = {"Song": "track", "Enabled": "context", "Disabled": "off"}
DIRECTORY_PATH = Path(Path.home(), "PolyPop/UIX/Spotify")
SPOTIFY_CACHE_DIR = Path(DIRECTORY_PATH, ".cache")
LOCAL_ARTWORK_PATH = Path(DIRECTORY_PATH, "artwork.jpg")
CREDS_PATH = Path(DIRECTORY_PATH, ".creds")
STATIC_PATH = Path(DIRECTORY_PATH, "backend/templates/dist/static")
SCOPE = (
    "user-modify-playback-state,user-read-currently-playing"
    "user-read-playback-state,user-library-read"
)
COVER_IMAGE_APIC_NAMES = ["APIC:", "data", "cov"]
HOST, PORT = "localhost", 38045
LOCAL_URL = Path("http://{HOST}:{PORT}")

logger.add(Path(DIRECTORY_PATH, "debug.log"), rotation="1 day", retention="5 days")
routes = web.RouteTableDef()
routes.static("/static/", STATIC_PATH)
jinja_env = Environment(
    loader=FileSystemLoader(Path(DIRECTORY_PATH, "backend/templates/dist")),
    autoescape=select_autoescape(),
)


@dataclass(slots=True, repr=False)
class Credentials:
    client_id: str
    client_secret: str
    token: str | None = None
    refresh_token: str | None = None

    @classmethod
    async def load(cls) -> "Credentials":
        async with aio_open(CREDS_PATH) as creds_file:
            return cls(**json_loads(await creds_file.read()))

    async def save(self) -> None:
        async with aio_open(CREDS_PATH, "w") as creds_file:
            await creds_file.write(json_dumps(asdict(self)))


@dataclass(slots=True, repr=False)
class SpotifyContext:
    spotify: Spotify

    # Dict of available devices: {name: id}
    devices: dict[str, str]

    # Current activity
    device: str
    shuffle_state: str
    repeat_state: str
    is_playing: bool
    playlists: dict[str, str]
    track: dict | None = None

    # The folder to look for local file album covers
    local_media_folder: str | None = None


async def exec_every_x_seconds(every: int, func: Awaitable) -> None:
    """Calls a function every x seconds

    Args:
        every (int): the number of seconds to wait in-between calls
        func (Callable): function to call
    """
    while True:
        await asyncio.sleep(every)
        await func


# -------------------------------------------------------------------------------------
#                                   Spotify Setup
# -------------------------------------------------------------------------------------


async def request_spotify_setup():
    # delete the cache if it exists
    SPOTIFY_CACHE_DIR.unlink(True)

    # Open the browser to the credentials setup page
    webbrowser.open(Path(LOCAL_URL, "/startup").as_uri())


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


async def create_spotify(
    app: web.Application, creds: Credentials | None = None
) -> Spotify | None:
    """Creates the Spotify Connection

    Args:
        app (web.Application): _description_
        creds (dict[str, str] | None, optional): _description_. Defaults to None.

    Returns:
        Spotify | None: Returns Spotify if successful, otherwise None
    """
    if creds is None:
        if not CREDS_PATH.exists():
            return

        creds = await Credentials.load()

    auth_manager = SpotifyOAuth(
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        redirect_uri=Path(LOCAL_URL, "/oauth_callback").as_uri(),
        scope=SCOPE,
        cache_handler=CacheFileHandler(SPOTIFY_CACHE_DIR),
    )

    try:
        spotify = Spotify(client_credentials_manager=auth_manager)
    except SpotifyOauthError:
        await request_spotify_setup()
        return

    me = spotify.me()
    current_playback = spotify.current_playback() or {}
    profile_image = me.get("images")
    current_context = SpotifyContext(
        spotify=spotify,
        devices=get_devices(spotify),
        device=current_playback.get("device", ""),
        track=current_playback.get("item", {}),
        shuffle_state=current_playback.get("shuffle_state"),
        repeat_state=current_playback.get("repeat_state"),
        is_playing=current_playback.get("is_playing"),
        playlists=get_all_playlists(spotify),
    )
    app["spotify_context"] = current_context
    await broadcast(
        app,
        "spotify_connect",
        name=me.get("display_name"),
        user_image_url="" if not profile_image else profile_image[0].get("url"),
        devices=current_context.devices,
        current_device=current_context.device,
        is_playing=current_context.is_playing,
        playlists=current_context.playlists,
        shuffle_state=current_shuffle,
        repeat_state=current_repeat,
    )

    asyncio.create_task(exec_every_x_seconds(1, check_now_playing(spotify)))
    asyncio.create_task(exec_every_x_seconds(5, check_sp_settings(spotify)))


async def refresh_spotify(
    app: web.Application, spotify: Spotify, auth_token: str | None = None
) -> Spotify:
    """Recreates/refreshes the Spotify Client

    Args:
        spotify (Spotify)
        auth_token (str | None, optional): Defaults to None.

    Returns:
        Spotify | None: New Spotify Client
    """
    auth_manager = cast(SpotifyOAuth, spotify.auth_manager)  # To appease PyLance
    auth_token = auth_token or auth_manager.cache_handler.get_cached_token()
    if auth_manager.is_token_expired(auth_token):
        _spotify = await create_spotify(app)
        if _spotify is not None:
            return spotify

    raise RuntimeError("Error while refreshing Spotify Client")


# -------------------------------------------------------------------------------------
#                                   Spotify Methods
# -------------------------------------------------------------------------------------


def get_all_playlists(spotify: Spotify) -> dict:
    playlists = {}
    for i in count(step=50):
        pl = spotify.current_user_playlists(offset=i)
        playlists.update({p.get("name"): p.get("uri") for p in pl.get("items")})
        if pl.get("next") is None:
            break

    if not playlists:
        return {0: "No Playlists"}
    return playlists


async def broadcast(app: web.Application, action: str, **data):
    for client in app["clients"]:
        if data:
            msg = {"action": action, "data": data}
            await client.broadcast(data=msg)
        else:
            await client.broadcast(data={"action": action})


def get_devices(spotify: Spotify) -> dict:
    global devices
    devices = {d.get("name"): d.get("id") for d in spotify.devices().get("devices")}
    return devices


async def play(app: web.Application, data: dict, retries: int = 0) -> None:
    spotify = app["spotify"]
    device_id = (
        devices.get(data.get("device_name")) or app["spotify_context"].current_device
    )
    playlist_uri = data.get("playlist_uri")
    song_uri = data.get("track_uri")

    logger.debug(device_id)

    if current_playing_state and not playlist_uri:
        return

    try:
        if playlist_uri:
            spotify.start_playback(device_id=device_id, context_uri=playlist_uri)
        elif song_uri:
            spotify.start_playback(device_id=device_id, uris=[song_uri])
        else:
            spotify.start_playback(device_id=device_id)
    except SpotifyException as e:
        if retries == 0:
            data["device_name"] = socket.gethostname()
            return await play(app, data, 1)
        elif retries == 1:
            data["device_name"] = environ["COMPUTERNAME"]
            return await play(app, data, 2)
        else:
            await broadcast(app, "error", command="play", msg=e.msg, reason=e.reason)
    except Exception as e:
        logger.exception(e)


def pause(spotify: Spotify) -> None:
    try:
        spotify.pause_playback()
    except SpotifyException as e:
        logger.exception(e)


def next_track(spotify: Spotify) -> None:
    spotify.next_track()


def previous_track(spotify: Spotify) -> None:
    try:
        spotify.previous_track()
    except SpotifyException as e:
        logger.exception(e)


def shuffle(spotify: Spotify, data: dict) -> None:
    spotify.shuffle(data.get("state", False))


def repeat(spotify: Spotify, data: dict) -> None:
    spotify.repeat(REPEAT_STATES[data.get("state", "Disabled")])


def volume(spotify: Spotify, data: dict) -> None:
    spotify.volume(data["volume"])


async def refresh_devices(app: web.application) -> None:
    await broadcast(app, "devices", devices=list(get_devices(app["spotify"])))


async def refresh_playlists(app: web.Application) -> None:
    await broadcast(app, "playlists", playlists=get_all_playlists(app["spotify"]))


async def check_sp_settings(spotify):
    global sp, current_shuffle, current_repeat, current_volume
    info = spotify.current_playback().get
    ret = {}
    new_shuffle = info("shuffle_state")
    new_repeat = info("repeat_state")

    if current_shuffle != new_shuffle:
        ret["shuffle_state"] = new_shuffle
        current_shuffle = new_shuffle
    if current_repeat != new_repeat:
        ret["repeat_state"] = new_repeat
        current_repeat = new_repeat

    if ret:
        await broadcast("update", **ret)


async def check_volume():
    global sp
    global current_volume
    info = spotify.current_playback()

    new_volume = volume_format(info.get("device", {}).get("volume_percent", 1))
    if current_volume != new_volume:
        current_volume = new_volume
        await broadcast("update", volume=new_volume)


def get_local_artwork(name):
    if local_media_folder is None:
        return None

    artwork = None
    logger.debug(f"{name=}")
    logger.debug(f"File Name: {local_media_folder}*{name}.*")
    file_names = glob(f"{local_media_folder}*{name}.*", recursive=True)

    logger.debug(f"{file_names=}")

    if not file_names:
        return

    logger.debug(f"{file_names[0]=}")
    song_file = File(file_names[0])
    logger.debug(f"{song_file.tags=}")

    for apic_name in COVER_IMAGE_APIC_NAMES:
        if apic_name not in song_file.tags:
            continue
        logger.debug(f"{LOCAL_ARTWORK_PATH}")
        artwork = song_file.tags[name].data

    if artwork is None:
        return

    with open(LOCAL_ARTWORK_PATH, "wb") as img:
        img.write(artwork)

    return LOCAL_ARTWORK_PATH


async def check_now_playing(spotify):
    global current_track, current_playing_state, sp
    track = spotify.currently_playing()
    track_id = track.get("item", {}).get("id")
    is_playing = track.get("is_playing")

    if is_playing != current_playing_state:
        old_playing_state = current_playing_state
        current_playing_state = is_playing
        if old_playing_state is None:
            current_track = track_id
            return
        if not is_playing:
            await broadcast("playing_stopped")
            return

        if track["item"]["is_local"]:
            if local_artwork := get_local_artwork(track["item"]["uri"].split(":")[-2]):
                track["item"]["album"]["images"] = [
                    {"url": local_artwork.replace("/", "\\")}
                ]
        logger.debug("start")
        logger.debug(track)
        await broadcast("started_playing", **track)

    if current_track == track_id:
        return

    current_track = track_id

    if track["item"]["is_local"]:
        if local_artwork := get_local_artwork(track["item"]["uri"].split(":")[-2]):
            track["item"]["album"]["images"] = [
                {"url": local_artwork.replace("/", "\\")}
            ]
    await broadcast("song_changed", **track)


def update_settings(data):
    global current_shuffle, current_repeat
    new_shuffle = data.get("shuffle_state")
    new_repeat = data.get("repeat_state")
    if new_shuffle:
        shuffle({"state": new_shuffle})
        current_shuffle = new_shuffle
    if new_repeat:
        repeat({"state": new_repeat})
        current_repeat = new_repeat


async def on_connected(websocket, data):  # noqa
    try:
        await create_spotify()
    except Exception as e:  # noqa
        logger.exception(e)


def set_local_media_folder(data):
    global local_media_folder
    local_media_folder = data["location"]


"""
------------------------------------------------------------------------------------------------------------------------
                                                  Server Connection
------------------------------------------------------------------------------------------------------------------------
"""


track_funcs_no_data = {"pause": pause, "next": next_track, "previous": previous_track}

track_funcs_with_data = {
    "shuffle_state": shuffle,
    "repeat_state": repeat,
    "update": update_settings,
    "volume": volume,
    "local_folder": set_local_media_folder,
}


async def websocket_handler(
    request: web.Request, app: web.Application | None = None
) -> None:
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
            await request_spotify_setup()

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
        await broadcast("error", command="play", msg=e.msg, reason=e.reason)
        logger.exception(e)

    if action == "logout":
        if os.path.exists(SPOTIFY_CACHE_DIR):
            os.remove(SPOTIFY_CACHE_DIR)
    elif action == "play":
        await play(data)
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
