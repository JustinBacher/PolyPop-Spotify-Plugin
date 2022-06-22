"""Contains constants and the context class for the PolyPop Service"""

import asyncio
import io
import webbrowser

from dataclasses import dataclass, asdict
from glob import glob
from itertools import count
from json import dump as json_dump, load as json_load, JSONDecodeError
from os import environ
from pathlib import Path
from socket import gethostname
from typing import Awaitable, NoReturn

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
from loguru import logger
from mutagen import File as SongLookupFile
from yarl import URL

SPOTIFY_SCOPE = (
    "user-modify-playback-state,user-read-currently-playing"
    "user-read-playback-state,user-library-read"
)

# Path related Constants
DIRECTORY_PATH = Path.home().joinpath("PolyPop/UIX/PolyPop-Spotify-Plugin")
LOCAL_ARTWORK_PATH = DIRECTORY_PATH.joinpath("artwork.jpg")
CREDENTIALS_PATH = DIRECTORY_PATH.joinpath(".creds")
SPOTIFY_CACHE_DIR = DIRECTORY_PATH.joinpath(".cache")
COVER_IMAGE_APIC_NAMES = ["APIC:", "data", "cov"]

# PolyPop to Spotify conversion
REPEAT_STATES = {"Song": "track", "Enabled": "context", "Disabled": "off"}

# URL constants
HOST, PORT = "localhost", 38045
LOCALHOST_URL = URL(f"http://{HOST}:{PORT}")


async def exec_every_x_seconds(every: int, func: Awaitable) -> asyncio.Task:
    """Calls a function every x seconds

    Args:
        every (int): the number of seconds to wait in-between calls
        func (Callable): function to call
    """

    async def tasker():
        while True:
            await func
            await asyncio.sleep(every)

    return asyncio.create_task(tasker())


@dataclass(
    repr=False,
)
class CredentialsManager:
    """Slightly shadow's Spotipy's auth manager due to it having issues
    handling cache and token refreshing

    Returns:
        _type_: _description_
    """

    __slots__ = "client_id", "client_secret"

    client_id: str | None
    client_secret: str | None

    @classmethod
    def load_from_file(cls) -> "CredentialsManager":
        """Loads the users credentials from `SPOTIFY_CACHE_PATH`

        Raises:
            FileNotFoundError: cache file either doesn't exist, doesn't have
                               client_id or client_secret, or isn't proper json

        Returns:
            CredentialsManager
        """

        def handle_corrupt_data(data: io.TextIOBase) -> NoReturn:
            CREDENTIALS_PATH.unlink()
            raise FileNotFoundError(
                f"Credentials file corrupt. File has been deleted.\nOld Contents:\n{data}"
            )

        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(f'No Credentials File at "{CREDENTIALS_PATH}"')

        with open(CREDENTIALS_PATH, encoding="utf-8") as credentials_file:
            try:
                credentials_data = json_load(credentials_file)
            except JSONDecodeError:
                credentials_file.seek(0)
                handle_corrupt_data(credentials_file)

        if {"client_id", "client_secret"} > credentials_data:
            handle_corrupt_data(credentials_file)

        return cls(
            client_id=credentials_data["client_id"], client_secret=credentials_data["client_secret"]
        )

    def save_to_file(self) -> None:
        """Saves credentials to file"""
        with open(CREDENTIALS_PATH, "w", encoding="utf-8") as creds_file:
            json_dump(asdict(self), creds_file)

    def auth_manager(self) -> SpotifyOAuth:
        """Generates an Oauth model

        Returns:
            SpotifyOAuth:
        """
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=LOCALHOST_URL.with_path("/oauth_callback"),
            scope=SPOTIFY_SCOPE,
            cache_handler=CacheFileHandler(SPOTIFY_CACHE_DIR),
        )

    def logout(self) -> None:
        """Clears the credentials and deletes the cached version of them

        Returns:
            None
        """
        try:
            del self.client_id
            del self.client_secret

        finally:
            SPOTIFY_CACHE_DIR.unlink()


class SpotifyContext:
    """Wrapper for the connectionn to Spotify

    Contains the active spotify connection and it's
    current states and settings

    Args:
        spotify (Spotify, optional): The Spotify Connection
        credentials_manager (CredentialsManager, optional)
        shuffle_state (bool, optional): Spotify's last known shuffle state
        repeat_state (bool, optional): Spotify's last known repeat state
        is_playing (bool, optional): Spotify's last known play/pause state
        playlists (dict, optional):
        current_device: str | None = None
        current_track: dict | None = None
        __local_media_folder: str | None = None

    """

    __slots__ = (
        "credentials_manager",
        "spotify",
        "shuffle_state",
        "repeat_state",
        "is_playing",
        "playlists",
        "current_device",
        "current_track",
        "__local_media_folder",
    )

    def __init__(self, credentials_manager: CredentialsManager | None = None) -> None:
        self.credentials_manager = credentials_manager

        # I think this is the best way to basically type hint
        # without setting values. And without making them global
        # to the class itself
        self.spotify: Spotify | None
        self.shuffle_state: bool | None
        self.repeat_state: bool | None
        self.is_playing: bool | None
        self.playlists: dict | None
        self.current_device: str | None
        self.current_track: dict | None
        self.__local_media_folder: str | None

    @property
    def local_media_folder(self) -> str | None:
        """Retrieves the local media folder

        Returns:
            str | None
        """
        return self.__local_media_folder

    @local_media_folder.setter
    def local_media_folder(self, value: str) -> None:
        """Sets the local media folder and persists it for future lookup

        Args:
            value (str): The path to the directory to search for song files with artwork
        """
        with open(LOCAL_ARTWORK_PATH, "w", encoding="utf-8") as artwork_file:
            json_dump(value, artwork_file)

        self.__local_media_folder = value

    @staticmethod
    def request_credentials_from_user(delete_old: bool = True) -> None:
        """opens the browser for user to provide credentials information

        Does not actually set credentials in this function.
        Requested credentials are `client_id` and `client_secret`

        Args:
            delete_old (bool, optional): If True, delete the old credentials.
                Defaults to True.
        """
        if delete_old:
            CREDENTIALS_PATH.unlink(True)

        logger.debug(LOCALHOST_URL)
        logger.debug(LOCALHOST_URL.with_path("/startup"))
        webbrowser.open(LOCALHOST_URL.with_path("/startup").human_repr())

    def logout(self) -> None:
        """alias for CredentialsManager.logout"""
        if self.credentials_manager:
            self.credentials_manager.logout()

    async def create_spotify(
        self, client_id: str | None = None, client_secret: str | None = None
    ) -> tuple | None:
        """Creates the Spotify Connection

        Returns:
            Spotify | None: Returns Spotify if successful, otherwise None
        """
        if client_id is None and client_secret is None:
            try:
                credentials_manager = CredentialsManager.load_from_file()

            except FileNotFoundError as error:
                logger.debug(error.args)
                return

        else:
            credentials_manager = CredentialsManager(
                client_id=client_id, client_secret=client_secret
            )

        self.spotify = spotify = Spotify(
            client_credentials_manager=credentials_manager.auth_manager
        )

        user_profile = spotify.me()
        current_playback = spotify.current_playback() or {}
        profile_image = user_profile.get("images")
        self.current_device = current_playback.get("device")
        self.current_track = current_playback.get("item")
        self.shuffle_state = current_playback.get("shuffle_state")
        self.repeat_state = current_playback.get("repeat_state")
        self.is_playing = current_playback.get("is_playing")

        return (
            self,
            (
                "spotify_connect",
                {
                    "name": user_profile.get("display_name"),
                    "user_image_url": "" if not profile_image else profile_image[0].get("url"),
                    "devices": self.get_devices(),
                    "current_device": self.current_device,
                    "is_playing": self.is_playing,
                    "shuffle_state": self.shuffle_state,
                    "repeat_state": self.repeat_state,
                },
            ),
            [
                await exec_every_x_seconds(1, self.check_now_playing()),
                await exec_every_x_seconds(5, self.check_spotify_settings()),
                await exec_every_x_seconds(1800, self.refresh_spotify()),
            ],
        )

    def close(self):
        """Closes the spotify connection

        If you see the spotipy docs it's done in the __del__ method
        """
        if hasattr(self, "spotify"):
            del self.spotify

    async def refresh_spotify(self) -> None:
        """Gets new access tokens, etc... and saves to cache file"""
        self.spotify.auth_manager.get_access_token()  # type: ignore [Spotipy didn't do type hints]

    def update_settings(self, data: dict) -> None:
        """Catch all for updating general Spotify settings.

        Args:
            data (dict): Should have the new settings and values to set
        """
        if self.spotify is None:
            return

        new_shuffle = data.get("state", False)
        new_repeat = data.get("repeat_state", True)
        if new_shuffle:
            self.spotify.shuffle({"state": new_shuffle})
            self.shuffle_state = new_shuffle
        if new_repeat:
            self.repeat({"state": new_repeat})
            self.repeat_state = new_repeat

    def get_all_playlists(self) -> dict | None:
        """Gets all of the current users playlists

        Args:
            spotify (Spotify)

        Returns:
            dict: {playlist name: playlist uri}
        """
        if self.spotify is None:
            return

        all_playlists = {}
        counter = count(step=50)

        while (
            playlists := self.spotify.current_user_playlists(offset=next(counter))
        ) and playlists.get("next") is None:
            all_playlists.update(
                {playlist["name"]: playlist["uri"] for playlist in playlists["items"]}
            )

        if not playlists:
            return {0: "No Playlists"}
        return playlists

    def get_devices(self) -> dict | None:
        """Get all the users currently available devices

        Args:
            spotify (Spotify)

        Returns:
            dict: In the form of: {device name: device id, ...}
        """
        return (
            None
            if self.spotify is None
            else {device["name"]: device["id"] for device in self.spotify.devices().get("devices")}
        )

    async def play(self, data: dict, retries: int = 0) -> tuple | None:
        """Starts Playing a song or Playlist. If failure then it retries
        by downgrading to a more do-able play event

        Args:
            app (web.Application)
            spotify (Spotify)
            self (SpotifyContext)
            data (dict)
            retries (int, optional): Number of times to try downgrading Play event. Defaults to 0.
        """
        if self.spotify is None:
            return

        devices = self.get_devices()

        if devices is None:
            return

        device_id = devices.get(data.get("device_name"), False) or self.current_device
        playlist_uri = data.get("playlist_uri")
        song_uri = data.get("track_uri")
        logger.debug(device_id)

        if self.is_playing and playlist_uri is not None:
            return

        try:
            if playlist_uri:
                self.spotify.start_playback(device_id=device_id, context_uri=playlist_uri)

            elif song_uri:
                self.spotify.start_playback(device_id=device_id, uris=[song_uri])

            else:
                self.spotify.start_playback(device_id=device_id)

        except SpotifyException as error:
            logger.exception(error)

            match retries:
                case 0:
                    data["device_name"] = gethostname()
                    return await self.play(data, 1)

                case 1:
                    data["device_name"] = environ["COMPUTERNAME"]
                    return await self.play(data, 2)

            return ("error", {"command": "play", "msg": error.msg, "reason": error.reason})

    def repeat(self, data: dict) -> None:
        """Calls `self.spotify.repeat` with the re-munged state

        Args:
            data (dict): The state from PolyPop to be munged back to what spotify expects
        """
        if self.spotify is None:
            return

        self.spotify.repeat(REPEAT_STATES[data.get("state", "Disabled")])

    async def refresh_devices(self) -> tuple | None:
        """Sends current available devices to client"""
        if self.spotify is None:
            return

        return (
            "devices",
            {"devices": [] if (devices := self.get_devices()) is None else list(devices)},
        )

    async def refresh_playlists(self) -> tuple | None:
        """Sends current available playlists to client"""
        if self.spotify is None:
            return

        return "playlists", {"playlists": self.get_all_playlists()}

    async def check_spotify_settings(self) -> tuple | None:
        """Checks for current spotify settings.
        If something changesthen broadcasts the changes"""
        if self.spotify is None:
            return

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
            return "update", ret

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

    async def check_now_playing(self) -> tuple | None:
        """Checks for current Spotify state and updates PolyPop in case of changes"""
        if self.spotify is None:
            return

        track = self.spotify.currently_playing()
        track_id = track.get("item", {}).get("id")
        is_playing = track.get("is_playing", False)

        if self.is_playing is None:
            self.current_track = track_id
            return

        if is_playing != self.is_playing:
            self.is_playing = is_playing

            if is_playing is None:
                return ("playing_stopped",)

            if track["item"]["is_local"] and (
                local_artwork := self.get_local_artwork(track["item"]["uri"].split(":")[-2])
            ):
                track["item"]["album"]["images"] = [{"url": f"file/{local_artwork}"}]
            logger.debug(track)
            return "started_playing", track

        if self.current_track == track_id:
            return

        if track["item"]["is_local"]:
            if local_artwork := self.get_local_artwork(track["item"]["uri"].split(":")[-2]):
                track["item"]["album"]["images"] = [
                    {"url": local_artwork.as_uri().replace("/", "\\")}
                ]
        return "song_changed", track
