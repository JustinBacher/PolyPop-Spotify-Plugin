import asyncio
from dataclasses import dataclass, asdict
from typing import Awaitable, Callable, cast
from json import dump as json_dump, load as json_load
from pathlib import Path
import webbrowser

from aiohttp import web
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
from spotipy.cache_handler import CacheFileHandler
from loguru import logger

from ppspotify import LOCAL_ARTWORK_PATH

HOST, PORT = "localhost", 38045
LOCAL_URL = Path("http://{HOST}:{PORT}")
DIRECTORY_PATH = Path(Path.home(), "PolyPop/UIX/Spotify")
CREDENTIALS_PATH = Path(DIRECTORY_PATH, ".creds")
SPOTIFY_CACHE_DIR = Path(DIRECTORY_PATH, ".cache")
SCOPE = (
    "user-modify-playback-state,user-read-currently-playing"
    "user-read-playback-state,user-library-read"
)


async def exec_every_x_seconds(every: int, func: Awaitable) -> None:
    """Calls a function every x seconds

    Args:
        every (int): the number of seconds to wait in-between calls
        func (Callable): function to call
    """
    while True:
        await asyncio.sleep(every)
        await func


class Server(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = set[web.WebSocketResponse]()

    async def broadcast(self, action: str, **data) -> None:
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


@dataclass(slots=True, repr=False)
class Credentials:
    client_id: str
    client_secret: str
    token: str | None = None
    refresh_token: str | None = None

    @classmethod
    def load(cls) -> "Credentials":
        if CREDENTIALS_PATH.exists():
            with open(CREDENTIALS_PATH) as creds_file:
                return cls(**json_load(creds_file))
        raise FileNotFoundError("No credentials file found")

    def save(self) -> None:
        with open(CREDENTIALS_PATH, "w") as creds_file:
            json_dump(asdict(self), creds_file)


class SpotifyContext:
    """Contains the active spotify connection and it's current states and settings"""

    __app: web.Application
    spotify: Spotify | None
    credentials: Credentials | None
    shuffle_state: bool | None
    repeat_state: bool | None
    is_playing: bool | None
    playlists: dict | None
    devices: dict | None
    current_device: str | None
    current_track: dict | None
    __local_media_folder: str | None

    def __init__(self, app: Server) -> None:
        """Don't create using `__init__`, use `SpotifyContext.create_spotify`"""
        self.__app = app

    @property
    def local_media_folder(self) -> str | None:
        return self.__local_media_folder

    @local_media_folder.setter
    def local_media_folder(self, value: str) -> None:
        """Sets the local media folder and persists it for future lookup

        Args:
            value (str): The path to the directory to search for song files with artwork
        """
        with open(LOCAL_ARTWORK_PATH, "w") as artwork_file:
            json_dump(value, artwork_file)

        self.__local_media_folder = value

    @staticmethod
    def ensure_spotify_connection(function: Callable):
        def inner(self, *args, **kwargs):
            if self.spotify is None:
                raise RuntimeError("Spotify not connected")
            function(*args, **kwargs)

        return inner

    @classmethod
    async def create_spotify(cls, app: Server) -> Spotify | None:
        """Creates the Spotify Connection

        Args:
            app (web.Application): _description_
            creds (dict[str, str] | None, optional): _description_. Defaults to None.

        Returns:
            Spotify | None: Returns Spotify if successful, otherwise None
        """
        try:
            creds = Credentials.load()
        except FileNotFoundError:
            return None

        auth_manager = SpotifyOAuth(
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            redirect_uri=Path(LOCAL_URL, "/oauth_callback").as_uri(),
            scope=SCOPE,
            cache_handler=CacheFileHandler(SPOTIFY_CACHE_DIR),
        )

        context = SpotifyContext(app)

        spotify = Spotify(client_credentials_manager=auth_manager)
        me = spotify.me()
        current_playback = spotify.current_playback() or {}
        profile_image = me.get("images")
        context.spotify = spotify
        context.devices = context.get_devices(spotify)
        context.current_device = current_playback.get("device")
        context.current_track = current_playback.get("item")
        context.shuffle_state = current_playback.get("shuffle_state")
        context.repeat_state = current_playback.get("repeat_state")
        context.is_playing = current_playback.get("is_playing")
        context.playlists = get_all_playlists(spotify)

        await app.broadcast(
            "spotify_connect",
            name=me.get("display_name"),
            user_image_url="" if profile_image == {} else profile_image[0].get("url"),
            devices=context.devices,
            current_device=context.current_device,
            is_playing=context.is_playing,
            playlists=context.playlists,
            shuffle_state=context.shuffle_state,
            repeat_state=context.repeat_state,
        )

        asyncio.create_task(exec_every_x_seconds(1, context.check_now_playing()))
        asyncio.create_task(exec_every_x_seconds(5, context.check_spotify_settings()))

    async def refresh_spotify(self) -> Spotify:
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

    @staticmethod
    def request_spotify_credentials() -> None:
        # delete the cache if it exists
        SPOTIFY_CACHE_DIR.unlink(True)

        # Open the browser to the credentials setup page
        webbrowser.open(Path(LOCAL_URL, "/startup").as_uri())

    def get_all_playlists(spotify: Spotify) -> dict:
        """Gets all of the current users playlists

        Args:
            spotify (Spotify)

        Returns:
            dict: {playlist name: playlist uri}
        """
        playlists = {}
        for i in count(step=50):
            pl = spotify.current_user_playlists(offset=i)
            playlists.update({p.get("name"): p.get("uri") for p in pl.get("items")})
            if pl.get("next") is None:
                break

        if not playlists:
            return {0: "No Playlists"}
        return playlists

    def get_devices(self) -> dict:
        """Get all the users currently available devices

        Args:
            spotify (Spotify)

        Returns:
            dict: {device name: device id, ...}
        """
        global devices
        devices = {d.get("name"): d.get("id") for d in spotify.devices().get("devices")}
        return devices

    async def play(
        app: web.Application,
        spotify: Spotify,
        current_context: SpotifyContext,
        data: dict,
        retries: int = 0,
    ) -> None:
        """Starts Playing a song or Playlist. If failure then it retries
        by downgrading to a more do-able play event

        Args:
            app (web.Application)
            spotify (Spotify)
            current_context (SpotifyContext)
            data (dict)
            retries (int, optional): Number of times to try downgrading Play event. Defaults to 0.
        """
        device_id = (
            devices.get(data.get("device_name", None), False) or current_context.device
        )
        playlist_uri = data.get("playlist_uri")
        song_uri = data.get("track_uri")
        logger.debug(device_id)

        if current_context.is_playing and playlist_uri is not None:
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
                return await play(app, spotify, current_context, data, 1)
            elif retries == 1:
                data["device_name"] = environ["COMPUTERNAME"]
                return await play(app, spotify, current_context, data, 2)
            else:
                await broadcast(
                    app, "error", command="play", msg=e.msg, reason=e.reason
                )
        except Exception as e:
            logger.exception(e)

    def pause(spotify: Spotify) -> None:
        try:
            spotify.pause_playback()
        except SpotifyException as e:
            logger.exception(e)

    @ensure_spotify_connection
    def next_track(self) -> None:
        self.spotify.next_track()

    def previous_track(spotify: Spotify) -> None:
        try:
            spotify.previous_track()
        except SpotifyException as e:
            logger.exception(e)

    def shuffle(self, data: dict) -> None:
        self.spotify.shuffle(data.get("state", False))

    def repeat(spotify: Spotify, data: dict) -> None:
        spotify.repeat(REPEAT_STATES[data.get("state", "Disabled")])

    def volume(spotify: Spotify, data: dict) -> None:
        spotify.volume(data["volume"])

    async def refresh_devices(app: web.Application, spotify: Spotify) -> None:
        """Sends current available devices to client"""
        await self.__app.broadcast("devices", devices=list(get_devices(spotify)))

    async def refresh_playlists(self) -> None:
        """Sends current available playlists to client"""
        await self.__app.broadcast("playlists", playlists=get_all_playlists(spotify))

    async def check_spotify_settings(self) -> None:
        """Checks for current spotify settings.
        If something changesthen broadcasts the changes"""
        info = spotify.current_playback().get
        new_shuffle = info("shuffle_state")
        new_repeat = info("repeat_state")
        ret = {}

        if current_context.shuffle_state != new_shuffle:
            ret["shuffle_state"] = new_shuffle
            current_context.shuffle_state = new_shuffle
        if current_context.repeat_state != new_repeat:
            ret["repeat_state"] = new_repeat
            current_context.repeat_state = new_repeat

        if ret:
            await self.__app.broadcast("update", **ret)

    def get_local_artwork(self, name: str) -> str | None:
        """Looks in the local directory recursively to find a matching
        filename to `name` and if so, tries to extract the album cover
        and save it to file and returns the path to the saved image,
        otherwise returns `None`

        Args:
            name (str): The file name to search for

        Returns:
            str | None: The path to the album cover file or None if not found
        """
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

    async def check_now_playing(self) -> None:
        """Checks for current Spotify state and updates PolyPop in case of changes

        Args:
            app (web.Application): _description_
            spotify (Spotify): _description_
            current_context (SpotifyContext): _description_
        """
        track = spotify.currently_playing()
        track_id = track.get("item", {}).get("id")
        is_playing = track.get("is_playing", False)

        if current_context.is_playing is None:
            current_context.track = track_id
            return

        if is_playing != current_context.is_playing:
            current_context.is_playing = is_playing

            if is_playing is None:
                await self.__app.broadcast("playing_stopped")
                return

            if track["item"]["is_local"] and (
                local_artwork := get_local_artwork(track["item"]["uri"].split(":")[-2])
            ):
                track["item"]["album"]["images"] = [{"url": f"file/{local_artwork}"}]
            logger.debug(track)
            await self.__app.broadcast("started_playing", **track)

        if current_track == track_id:
            return

        current_track = track_id

        if track["item"]["is_local"]:
            if local_artwork := get_local_artwork(track["item"]["uri"].split(":")[-2]):
                track["item"]["album"]["images"] = [
                    {"url": local_artwork.replace("/", "\\")}
                ]
        await self.__app.broadcast("song_changed", **track)
