import os
import socket
import asyncio
import webbrowser
import spotipy
import ws
from glob import glob
from itertools import count
import PySimpleGUI as GUI # noqa
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from collections import namedtuple
from operator import itemgetter
from loguru import logger
from mutagen import File


REPEAT_STATES = {'Song': 'track', 'Enabled': 'context', 'Disabled': 'off'}
DIRECTORY_PATH = os.path.expandvars("C:/Users/%username%/PolyPop/UIX/Sources/Spotify/{}").format
SPOTIFY_CACHE_DIR = DIRECTORY_PATH('.cache')
LOCAL_ARTWORK_PATH = DIRECTORY_PATH("artwork.jpg")
SCOPE = "user-read-playback-state,user-library-read,user-modify-playback-state,user-read-currently-playing"
sp: Spotify
tasks, queue = ([],)*2
devices = {}
current_device, current_track, current_shuffle, current_repeat, current_volume, current_playing_state = (None,) * 6
credentials = namedtuple("Credentials", ['client_id', 'client_secret'])(None, None)
Song = namedtuple('Song', ['requester', 'track'])
queue_limit = 10
server = ws.ServerSocket()
local_media_folder = ""

logger.add(DIRECTORY_PATH("debug.log"), rotation="1 day", retention="5 days")


def volume_format(v):
    return float('%.2f' % v)


#########################################################################
# GUI SETUP
#########################################################################

GUI.theme('Dark')
GUI.SetOptions(font='helvetica 16', scrollbar_color='gray')


def create_layout():
    return [[
        GUI.Column([
            [GUI.Text('Welcome to the PolyPop Spotify Plugin!',
                      font='helvetica 20 bold')],
            [GUI.Text('Created by Jab!', font='helvetica 20 bold')],
            [GUI.Image(DIRECTORY_PATH('poly to sp.png'))],
            [GUI.Text('Please follow the steps below to setup the Spotify Plugin:',
                      font='helvetica 18 bold underline')],
            [GUI.Text('', font='helvetica 20 bold')],
            [GUI.Text('1: Goto https://developer.spotify.com/dashboard/login and login')],
            [GUI.Text('(click the image below to redirect to the Developer Site)',
                      font='helvetica 12 bold underline')],
            [GUI.Button('Login',
                        image_filename=DIRECTORY_PATH('Log In.png'),
                        font="helvetica 2")],
            [GUI.Text('2: Click Create App')],
            [GUI.Image(DIRECTORY_PATH('Create App.png'))],
            [GUI.Text('3: Fill In the App Name, Description, and Check the "I Agree" box. Then Click "Create"')],
            [GUI.Image(DIRECTORY_PATH('App Info.png'))],
            [GUI.Text('4: Click on "Edit Settings"')],
            [GUI.Image(DIRECTORY_PATH('Edit Settings.png'))],
            [GUI.Text('5: Paste "http://localhost:38042" into the "Redirect URIs and click Add')],
            [GUI.Text('(click the image below to copy the URL to your clipboard)',
                      font='helvetica 12 bold underline')],
            [GUI.Button("Redirect",
                        image_filename=DIRECTORY_PATH('Redirect URI.png'),
                        font='helvetica 2')],
            [GUI.Text('6: Click save at the bottom of that screen')],
            [GUI.Text('7: Copy the Client ID and Client Secret to the below Fields and Click Done!')],
            [GUI.Image(DIRECTORY_PATH('Client Info.png'))],
            [GUI.Text('(reveal the client secret by clicking the green text)',
                      font='helvetica 12 italic')],
            [GUI.Text('', font='helvetica 30 italic')],
            [GUI.Text('Client ID', font='helvetica 18 bold')],
            [GUI.InputText()],
            [GUI.Text('Client Secret', font='helvetica 18 bold')],
            [GUI.InputText()],
            [GUI.Button('Ok'), GUI.Button('Cancel')],
            [GUI.Text('', font='helvetica 40 italic')]],
            scrollable=True, element_justification='center', vertical_scroll_only=True, expand_x=True)
        ]
    ]


window_name = 'Spotify Setup'


async def request_spotify_setup():
    if os.path.exists(SPOTIFY_CACHE_DIR):
        os.remove(SPOTIFY_CACHE_DIR)

    while True:
        window = GUI.Window(
            window_name,
            create_layout(),
            resizable=True,
            force_toplevel=True,
            icon=DIRECTORY_PATH('icon.ico'),
            finalize=True
        )
        window.close_destroys_window = True
        while True:
            event, values = window.read()

            if event in {GUI.WIN_CLOSED, 'Cancel'}:
                return
            if event == "Login":
                webbrowser.open_new('https://developer.spotify.com/dashboard/login')
                continue
            if event == "Redirect":
                GUI.clipboard_set(f"http://localhost:38042")
                continue
            break
        client_id, client_secret = map(str.strip, values.values())
        window.close()
        missing = "Client ID " if not client_id else ""
        if not client_secret:
            missing += ("and " if client_id else "") + "Client Secret"

        if not missing:
            await connect_to_spotify(client_id, client_secret)
            return True
        else:
            GUI.popup_ok(f"Missing {missing}", title=f"Missing {missing}")


async def connect_to_spotify(client_id, client_secret):
    global sp, current_shuffle, current_repeat, current_volume, current_playing_state, current_device,\
        credentials, devices
    if credentials.client_id != client_id and credentials.client_secret != client_secret:
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://localhost:38042",
            scope=SCOPE,
            cache_path=SPOTIFY_CACHE_DIR)

        try:
            sp = spotipy.Spotify(oauth_manager=auth_manager)
        except spotipy.oauth2.SpotifyOauthError:
            GUI.popup_error(f"Authentication Failed. Please re-enter client info.", title=f"Authentication Error")
            await request_spotify_setup()
            return

    me = sp.me()
    current_playback = sp.current_playback() or {}
    curr_device = current_playback.get('device', {})
    now_playing_info = sp.currently_playing()
    current_shuffle = current_playback.get('shuffle_state')
    current_repeat = current_playback.get('repeat_state')
    current_volume = volume_format(curr_device.get('volume_percent', 0) / 1)
    current_device = curr_device.get('id')
    profile_image = me.get('images')
    await send(
        "spotify_connect",
        name=me.get('display_name'),
        user_image_url="" if not profile_image else profile_image[0].get('url'),
        devices=list(get_devices()),
        current_device=curr_device.get('name'),
        client_id=client_id,
        client_secret=client_secret,
        is_playing=bool(now_playing_info),
        playlists=get_all_playlists(),
        shuffle_state=current_shuffle,
        repeat_state=current_repeat,
        volume=current_volume)

    tasks.append(asyncio.create_task(exec_every_x_seconds(1, check_now_playing)))
    tasks.append(asyncio.create_task(exec_every_x_seconds(5, check_sp_settings)))

    
def get_all_playlists():
    playlists = {}
    for i in count(step=50):
        pl = sp.current_user_playlists(offset=i)
        playlists.update({p.get('name'): p.get('uri') for p in pl.get('items')})
        if pl.get('next') is None:
            break

    if not playlists:
        return {0: 'No Playlists'}
    return playlists


async def send(action, **data):
    for client in server.clients:
        if data:
            msg = {'action': action, 'data': data}
            await client.send(data=msg)
        else:
            await client.send(data={'action': action})


def clear_tasks():
    global tasks
    for task in tasks:
        task.cancel()
    tasks = []


def get_devices():
    global devices
    devices = {d.get('name'): d.get('id') for d in sp.devices().get('devices')}
    return devices


async def play(data, retries=0):
    device_id = devices.get(data.get('device_name')) or current_device
    playlist_uri = data.get('playlist_uri')
    song_uri = data.get('track_uri')

    logger.debug(device_id)

    if current_playing_state and not playlist_uri:
        return

    try:
        if playlist_uri:
            sp.start_playback(device_id=device_id, context_uri=playlist_uri)
        elif song_uri:
            sp.start_playback(device_id=device_id, uris=[song_uri])
        else:
            sp.start_playback(device_id=device_id)
    except SpotifyException as e:
        if retries == 0:
            data['device_name'] = socket.gethostname()
            return await play(data, 1)
        elif retries == 1:
            data['device_name'] = os.environ['COMPUTERNAME']
            return await play(data, 2)
        else:
            await send('error', command='play', msg=e.msg, reason=e.reason)
    except Exception as e:
        logger.exception(e)


def pause():
    try:
        sp.pause_playback()
    except spotipy.SpotifyException:
        pass


def next_track():
    sp.next_track()


def previous_track():
    try:
        sp.previous_track()
    except spotipy.SpotifyException:
        pass


def shuffle(data):
    sp.shuffle(data.get('state', False))


def repeat(data):
    sp.repeat(REPEAT_STATES[data.get('state', 'Disabled')])


_vol = 'volume'


def volume(data):
    sp.volume(data[_vol])


async def refresh_devices():
    await send('devices', devices=list(get_devices()))


async def refresh_playlists():
    await send('playlists', playlists=get_all_playlists())


async def exec_every_x_seconds(timeout, func):
    while True:
        await asyncio.sleep(timeout)
        await func()


async def check_sp_settings():
    global sp, current_shuffle, current_repeat, current_volume
    info = sp.current_playback().get
    ret = {}
    new_shuffle = info('shuffle_state')
    new_repeat = info('repeat_state')

    if current_shuffle != new_shuffle:
        ret['shuffle_state'] = new_shuffle
        current_shuffle = new_shuffle
    if current_repeat != new_repeat:
        ret['repeat_state'] = new_repeat
        current_repeat = new_repeat

    if ret:
        await send('update', **ret)


async def check_volume():
    global sp
    global current_volume
    info = sp.current_playback()
    
    new_volume = volume_format(info.get('device', {}).get('volume_percent', 1))
    if current_volume != new_volume:
        current_volume = new_volume
        await send('update', volume=new_volume)


cover_image_APIC_names = ['data', 'cov']


def get_local_artwork(name):
    if not local_media_folder:
        return None

    logger.debug(f"{name=}")
    logger.debug(f"File Name: {local_media_folder}*{name}.*")
    file_names = glob(f"{local_media_folder}*{name}.*", recursive=True)

    logger.debug(f"{file_names=}")

    if not file_names:
        return

    logger.debug(f"{file_names[0]=}")
    song_file = File(file_names[0])
    logger.debug(f"{song_file.tags=}")
    if 'APIC:' not in song_file.tags:
        return

    logger.debug(f"{LOCAL_ARTWORK_PATH}")
    artwork = song_file.tags['APIC:'].data
    with open(LOCAL_ARTWORK_PATH, 'wb') as img:
        img.write(artwork)

    return LOCAL_ARTWORK_PATH


async def check_now_playing():
    global current_track, current_playing_state
    track = sp.currently_playing()
    track_id = track.get('item', {}).get('id')
    is_playing = track.get('is_playing')

    if is_playing != current_playing_state:
        old_playing_state = current_playing_state
        current_playing_state = is_playing
        if old_playing_state is None:
            current_track = track_id
            return
        if not is_playing:
            await send('playing_stopped')
            return

        if track['item']["is_local"]:
            if local_artwork := get_local_artwork(track['item']['uri'].split(':')[-2]):
                track['item']['album']['images'] = [{'url': local_artwork.replace('/', '\\')}]
        logger.debug('start')
        logger.debug(track)
        await send('started_playing', **track)

    if current_track == track_id:
        return

    current_track = track_id

    if track['item']["is_local"]:
        if local_artwork := get_local_artwork(track['item']['uri'].split(':')[-2]):
            track['item']['album']['images'] = [{'url': local_artwork.replace('/', '\\')}]
    await send('song_changed', **track)


def update_settings(data):
    global current_shuffle, current_repeat, current_volume
    new_shuffle = data.get('shuffle_state')
    new_repeat = data.get('repeat_state')
    if new_shuffle:
        shuffle({'state': new_shuffle})
        current_shuffle = new_shuffle
    if new_repeat:
        repeat({'state': new_repeat})
        current_repeat = new_repeat


get_client_details = itemgetter('client_id', 'client_secret')
async def on_connected(websocket, data): # noqa
    try:
        await connect_to_spotify(*get_client_details(data))
    except Exception as e: # noqa
        logger.exception(e)


def set_local_media_folder(data):
    global local_media_folder
    local_media_folder = data['location']


"""
------------------------------------------------------------------------------------------------------------------------
                                                  Server Connection
------------------------------------------------------------------------------------------------------------------------
"""


track_funcs_no_data = {
    'pause': pause,
    'next': next_track,
    'previous': previous_track
}

track_funcs_with_data = {
    'shuffle_state': shuffle,
    'repeat_state': repeat,
    'update': update_settings,
    'volume': volume,
    'local_folder': set_local_media_folder
}


@server.on('ready')
async def on_ready():
    logger.info(f"Server is ready listening at ws://{server.address}:{server.port}")


@server.on('connect')
async def on_connect(client, path): # noqa - `path` unused
    logger.info(f"Client at {client.remote_address} connected.")


@server.on('message')
async def on_message(message):
    global local_media_folder
    action = message.data.action

    if not action:
        return

    try:
        data = message.data.data
    except AttributeError:
        data = {}

    if action == 'login':
        local_media_folder = data.get('local_folder')
        if data.get('client_id') and data.get('client_secret'):
            await on_connected(message.author, data)
        else:
            await request_spotify_setup()

    if not sp:
        return

    if action == 'volume':
        sp.volume(data[_vol])
        return

    try:
        if func := track_funcs_with_data.get(action):
            func(data)
            return
        if func := track_funcs_no_data.get(action):
            func()
            return
    except SpotifyException as e:
        await send('error', command='play', msg=e.msg, reason=e.reason)
        logger.exception(e)

    if action == 'logout':
        if os.path.exists(SPOTIFY_CACHE_DIR):
            os.remove(SPOTIFY_CACHE_DIR)
    elif action == 'play':
        await play(data)
    elif action == 'refresh_devices':
        await refresh_devices()
    elif action == 'refresh_playlists':
        await refresh_playlists()
    elif action == 'quit':
        for client in server.clients:
            await server.close(client)
            quit()


@server.on('disconnect')
async def on_disconnect(client, code, reason):
    logger.info(f"Client at {client.remote_address} disconnected with code: ", code, "and reason: ", reason)
    logger.info(server.disconnected_clients)


@server.on("close")
async def on_close(client, code, reason):
    logger.info(f"Client at {client.remote_address} closed connection with code: {code} and reason: {reason}")


def main():
    server.listen("localhost", 38041)


if __name__ == "__main__":
    main()
