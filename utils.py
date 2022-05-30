import asyncio
import webbrowser

from dataclasses import dataclass, asdict
from glob import glob
from itertools import count
from json import dump as json_dump, load as json_load
from os import environ
from pathlib import Path
from socket import gethostname
from typing import Awaitable

from aiohttp import web
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
from spotipy.cache_handler import CacheFileHandler
from loguru import logger
from mutagen import File as SongLookupFile

from server import Server

SPOTIFY_SCOPE = (
    "user-modify-playback-state,user-read-currently-playing"
    "user-read-playback-state,user-library-read"
)

# Path related Constants
DIRECTORY_PATH = Path(Path.home(), "PolyPop/UIX/Spotify")
LOCAL_ARTWORK_PATH = Path(DIRECTORY_PATH, "artwork.jpg")
CREDENTIALS_PATH = Path(DIRECTORY_PATH, ".creds")
SPOTIFY_CACHE_DIR = Path(DIRECTORY_PATH, ".cache")
COVER_IMAGE_APIC_NAMES = ["APIC:", "data", "cov"]

# PolyPop to Spotify conversion
REPEAT_STATES = {"Song": "track", "Enabled": "context", "Disabled": "off"}

# URL constants
HOST, PORT = "localhost", 38045
LOCALHOST_URL = Path("http://{HOST}:{PORT}")


async def exec_every_x_seconds(every: int, func: Awaitable) -> None:
    """Calls a function every x seconds

    Args:
        every (int): the number of seconds to wait in-between calls
        func (Callable): function to call
    """
    while True:
        await func
        await asyncio.sleep(every)


@dataclass(
    repr=False,
)
class CredentialsManager:
    """Slightly shadow's Spotipy's auth manager due to it having issues
    handling cache and token refreshing

    Returns:
        _type_: _description_
    """

    __slots__ = "client_id", "client_secret", "token", "refresh_token"

    client_id: str | None
    client_secret: str | None

    @classmethod
    def load(cls) -> None:
        if CREDENTIALS_PATH.exists():
            with open(CREDENTIALS_PATH) as creds_file:
                get_val = json_load(creds_file).get
            self = cls(
                client_id=get_val("client_id"),
                client_secret=get_val("client_secret"),
            )

    @staticmethod
    def request_credentials() -> None:
        # Open the browser to the credentials setup page
        webbrowser.open(Path(LOCALHOST_URL, "/startup").as_uri())

    def save(self) -> None:
        with open(CREDENTIALS_PATH, "w") as creds_file:
            json_dump(asdict(self), creds_file)

    def auth_manager(self):
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=Path(LOCALHOST_URL, "/oauth_callback").as_uri(),
            scope=SPOTIFY_SCOPE,
            cache_handler=CacheFileHandler(SPOTIFY_CACHE_DIR),
        )

    def logout(self) -> None:
        SPOTIFY_CACHE_DIR.unlink(True)


@dataclass
class SpotifyContext:
    """Contains the active spotify connection and it's
    current states and settings"""

    __app: Server
    spotify: Spotify
    credentials_manager: CredentialsManager
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
    def login() -> None:
        """Deletes the cache file and opens the login web page"""
        CREDENTIALS_PATH.unlink()
        webbrowser.open(Path(LOCALHOST_URL, "/startup").as_uri())

    @classmethod
    async def create_spotify(cls, app: Server) -> Spotify | None:
        """Creates the Spotify Connection

        Args:
            app (web.Application): _description_
            creds (dict[str, str] | None, optional): _description_. Defaults to None.

        Returns:
            Spotify | None: Returns Spotify if successful, otherwise None
        """
        self = cls(app)

        if CREDENTIALS_PATH.exists():
            self.credentials_manager
        spotify = Spotify(
            client_credentials_manager=self.credentials_manager.auth_manager
        )
        self.spotify = spotify
        me = self.spotify.me()
        current_playback = self.spotify.current_playback() or {}
        profile_image = me.get("images")
        self.devices = self.get_devices()
        self.current_device = current_playback.get("device")
        self.current_track = current_playback.get("item")
        self.shuffle_state = current_playback.get("shuffle_state")
        self.repeat_state = current_playback.get("repeat_state")
        self.is_playing = current_playback.get("is_playing")
        self.playlists = self.get_all_playlists()

        await app.broadcast(
            "spotify_connect",
            name=me.get("display_name"),
            user_image_url="" if profile_image == {} else profile_image[0].get("url"),
            devices=self.devices,
            current_device=self.current_device,
            is_playing=self.is_playing,
            playlists=self.playlists,
            shuffle_state=self.shuffle_state,
            repeat_state=self.repeat_state,
        )

        asyncio.create_task(exec_every_x_seconds(1, self.check_now_playing()))
        asyncio.create_task(exec_every_x_seconds(5, self.check_spotify_settings()))
        asyncio.create_task(exec_every_x_seconds(1800, self.refresh_spotify()))

    async def refresh_spotify(self) -> None:
        self.spotify.auth_manager.get_access_token()  # type: ignore | Spotipy didn't do type hinting

    def update_settings(self, data: dict) -> None:
        new_shuffle = data.get("shuffle_state")
        new_repeat = data.get("repeat_state")
        if new_shuffle:
            self.shuffle({"state": new_shuffle})
            self.shuffle_state = new_shuffle
        if new_repeat:
            self.repeat({"state": new_repeat})
            self.repeat_state = new_repeat

    def get_all_playlists(self) -> dict:
        """Gets all of the current users playlists

        Args:
            spotify (Spotify)

        Returns:
            dict: {playlist name: playlist uri}
        """
        playlists = {}
        for i in count(step=50):
            pl = self.spotify.current_user_playlists(offset=i)
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
        devices = {
            d.get("name"): d.get("id") for d in self.spotify.devices().get("devices")
        }
        return devices

    async def play(
        self,
        data: dict,
        retries: int = 0,
    ) -> None:
        """Starts Playing a song or Playlist. If failure then it retries
        by downgrading to a more do-able play event

        Args:
            app (web.Application)
            spotify (Spotify)
            self (SpotifyContext)
            data (dict)
            retries (int, optional): Number of times to try downgrading Play event. Defaults to 0.
        """
        device_id = (
            devices.get(data.get("device_name", None), False) or self.current_device
        )
        playlist_uri = data.get("playlist_uri")
        song_uri = data.get("track_uri")
        logger.debug(device_id)

        if self.is_playing and playlist_uri is not None:
            return

        try:
            if playlist_uri:
                self.spotify.start_playback(
                    device_id=device_id, context_uri=playlist_uri
                )
            elif song_uri:
                self.spotify.start_playback(device_id=device_id, uris=[song_uri])
            else:
                self.spotify.start_playback(device_id=device_id)
        except SpotifyException as e:
            if retries == 0:
                data["device_name"] = gethostname()
                return await self.play(data, 1)
            elif retries == 1:
                data["device_name"] = environ["COMPUTERNAME"]
                return await self.play(data, 2)
            else:
                await self.__app.broadcast(
                    "error", command="play", msg=e.msg, reason=e.reason
                )
        except Exception as e:
            logger.exception(e)

    def pause(self) -> None:
        try:
            self.spotify.pause_playback()
        except SpotifyException as e:
            logger.exception(e)

    def next_track(self) -> None:
        self.spotify.next_track()

    def previous_track(self) -> None:
        try:
            self.previous_track()
        except SpotifyException as e:
            logger.exception(e)

    def shuffle(self, data: dict) -> None:
        self.spotify.shuffle(data.get("state", False))

    def repeat(self, data: dict) -> None:
        self.spotify.repeat(REPEAT_STATES[data.get("state", "Disabled")])

    def volume(self, data: dict) -> None:
        self.spotify.volume(data["volume"])

    async def refresh_devices(self) -> None:
        """Sends current available devices to client"""
        await self.__app.broadcast("devices", devices=list(self.get_devices()))

    async def refresh_playlists(self) -> None:
        """Sends current available playlists to client"""
        await self.__app.broadcast("playlists", playlists=self.get_all_playlists())

    async def check_spotify_settings(self) -> None:
        """Checks for current spotify settings.
        If something changesthen broadcasts the changes"""
        info = self.spotify.current_playback().get
        new_shuffle = info("shuffle_state")
        new_repeat = info("repeat_state")
        ret = {}

        if self.shuffle_state != new_shuffle:
            ret["shuffle_state"] = new_shuffle
            self.shuffle_state = new_shuffle
        if self.repeat_state != new_repeat:
            ret["repeat_state"] = new_repeat
            self.repeat_state = new_repeat

        if ret:
            await self.__app.broadcast("update", **ret)

    def get_local_artwork(self, name: str) -> Path | None:
        """Looks in the local directory recursively to find a matching
        filename to `name` and if so, tries to extract the album cover
        and save it to file and returns the path to the saved image,
        otherwise returns `None`

        Args:
            name (str): The file name to search for

        Returns:
            str | None: The path to the album cover file or None if not found
        """
        if self.local_media_folder is None:
            return None

        artwork = None
        logger.debug(f"{name=}")
        logger.debug(f"File Name: {self.local_media_folder}*{name}.*")
        file_names = glob(f"{self.local_media_folder}*{name}.*", recursive=True)

        logger.debug(f"{file_names=}")

        if not file_names:
            return

        logger.debug(f"{file_names[0]=}")
        song_file = SongLookupFile(file_names[0])
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
            self (SpotifyContext): _description_
        """
        track = self.spotify.currently_playing()
        track_id = track.get("item", {}).get("id")
        is_playing = track.get("is_playing", False)

        if self.is_playing is None:
            self.track = track_id
            return

        if is_playing != self.is_playing:
            self.is_playing = is_playing

            if is_playing is None:
                await self.__app.broadcast("playing_stopped")
                return

            if track["item"]["is_local"] and (
                local_artwork := self.get_local_artwork(
                    track["item"]["uri"].split(":")[-2]
                )
            ):
                track["item"]["album"]["images"] = [{"url": f"file/{local_artwork}"}]
            logger.debug(track)
            await self.__app.broadcast("started_playing", **track)

        if self.current_track == track_id:
            return

        current_track = track_id

        if track["item"]["is_local"]:
            if local_artwork := self.get_local_artwork(
                track["item"]["uri"].split(":")[-2]
            ):
                track["item"]["album"]["images"] = [
                    {"url": local_artwork.as_uri().replace("/", "\\")}
                ]
        await self.__app.broadcast("song_changed", **track)
