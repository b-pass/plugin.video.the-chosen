#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import re
import json
from urllib.parse import parse_qsl, urlencode

import requests
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

PLUGIN_BASE = ''
HANDLE = -1
DO_CACHE = True # set to False while debugging so Kodi doesn't reuse cached listings
TIMEOUT = 30 # seconds, for every API request
SHOW_TITLE = 'The Chosen' # everything this addon lists belongs to this show

addon = xbmcaddon.Addon()

apiurl = "https://api.watch.thechosen.tv/v1/"
# yes, weirdly the OTP calls are "v2" (not "v1" like everything else)
otpurl = "https://api.watch.thechosen.tv/v2/auth/"
language = str(xbmc.getLanguage(xbmc.ISO_639_1)).lower() or 'en'
apiheaders = {
    'User-Agent':'Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
    'Accept':'application/json, text/plain, */*',
    'Referer': 'https://watch.thechosen.tv/',
    'Origin': 'https://watch.thechosen.tv',
    'X-language' : language,
    'Accept-Language' : language,
}

def log(txt, level=xbmc.LOGINFO):
    xbmc.log('the-chosen : ' + txt, level=level)

def notify(msg):
    xbmcgui.Dialog().notification(addon.getAddonInfo('name'), msg, xbmcgui.NOTIFICATION_ERROR)

def plugin_url(**params):
    # parameter order matters: Kodi keys watched/resume state on the exact play URL
    return f'{PLUGIN_BASE}?{urlencode(params)}'

def kodi_version():
    try:
        return int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
    except ValueError:
        return 0

_ANY = object()

def getem(data, *keys, default=_ANY):
    # Walk nested dicts/lists from the API. If anything along the way is missing or null,
    # return default ({} if none is given, which is safe to iterate or .items()). With a
    # default, a result of another type is converted if it's a number <-> string mixup,
    # or else also gives the default, so a server-side change can't raise here or later.
    for k in keys:
        if isinstance(k, int) and isinstance(data, list):
            data = data[k] if -len(data) <= k < len(data) else None
        elif isinstance(data, dict):
            data = data.get(k)
        else:
            data = None
        if data is None:
            return {} if default is _ANY else default

    if default is _ANY or isinstance(data, type(default)):
        return data
    try:
        if isinstance(default, int) and not isinstance(default, bool) and isinstance(data, (str, float)):
            return int(data)
        if isinstance(default, str) and isinstance(data, (int, float)) and not isinstance(data, bool):
            return str(data)
    except ValueError:
        pass
    return default

def save_tokens(tokens):
    id_token = getem(tokens, 'idToken', default='')
    if not id_token:
        raise ValueError('no idToken in response')
    token = f"Bearer {id_token}"
    apiheaders['Authorization'] = token
    addon.setSetting('authorization', token)
    addon.setSetting('tokens', json.dumps(tokens))

def clear_tokens():
    apiheaders.pop('Authorization', None)
    addon.setSetting('authorization', '')
    addon.setSetting('tokens', '')

def login(session:requests.Session, username):
    clear_tokens()
    if not username:
        return False

    resp = None
    try:
        resp = session.post(otpurl + 'request-otp', headers=apiheaders, json={"email" : username, "locale" : language}, timeout=TIMEOUT)
        resp.raise_for_status()
        resp_obj = resp.json()

        if getem(resp_obj, 'isNewUser', default=False):
            xbmcgui.Dialog().ok("First Login", "Log in via a web browser to set up your account.")
            return False

        if not getem(resp_obj, 'ageVerified', default=True):
            xbmcgui.Dialog().ok("Login Failed", "Your account does not have a Date of Birth listed. Log in via a web browser and set your birthdate.")
            return False

        if not resp.ok or not getem(resp_obj, 'ok', default=True):
            log(f"request-otp failed: {json.dumps(resp_obj)}", level=xbmc.LOGWARNING)
            xbmcgui.Dialog().ok("Login Failed", f"Login attempt failed to send OTP code\n{resp.status_code} {resp.reason}")
            return False

        code = xbmcgui.Dialog().numeric(0, "Enter One Time code from email")
        if not code:
            return False

        resp = session.post(otpurl + 'verify-otp', headers=apiheaders, json={"email" : username, "code" : code.zfill(6)}, timeout=TIMEOUT)
        save_tokens(resp.json())
        log('Login OK')
        return True
    except (requests.RequestException, ValueError, KeyError) as e:
        log(f"Login exception: {e}", level=xbmc.LOGWARNING)

    status = f"\n{resp.status_code} {resp.reason}" if resp is not None else ""
    xbmcgui.Dialog().ok("Login Failed", "Login attempt failed to produce an authentication token." + status)
    return False

def refresh(session):
    try:
        tokens = getem(json.loads(addon.getSetting('tokens') or '{}'), default={})
    except ValueError:
        tokens = {}
    refresh_token = getem(tokens, 'refreshToken', default='')
    if not refresh_token:
        log('No refresh token')
        clear_tokens()
        return False

    status = 0
    try:
        resp = session.post(apiurl + 'auth/refresh', headers=apiheaders, json={"refreshToken" : refresh_token}, timeout=TIMEOUT)
        resp.raise_for_status()

        # keep the old refreshToken if the response doesn't include a new one
        tokens.update(getem(resp.json(), default={}))
        save_tokens(tokens)
        log('Refresh OK')
        return True
    except (requests.RequestException, ValueError, KeyError) as e:
        log(f'Refresh Failed: {e}', level=xbmc.LOGWARNING)
        status = getattr(getattr(e, 'response', None), 'status_code', 0) or 0

    if 400 <= status < 500:
        # the server rejected our refresh token, so it's no good anymore
        clear_tokens()
    else:
        # probably transient (network, 5xx); keep the tokens for next time
        apiheaders.pop('Authorization', None)
    return False

def api_query(slug):
    session = requests.Session()

    if 'Authorization' not in apiheaders:
        bearer = addon.getSetting('authorization')
        if bearer:
            apiheaders['Authorization'] = bearer

    resp = session.get(apiurl + slug, headers=apiheaders, timeout=TIMEOUT)
    if resp.status_code == 401 and 'Authorization' in apiheaders:
        if not refresh(session):
            xbmcgui.Dialog().ok("Auth Fail", "Authentication refresh failed. You may need to log in again.\n\nWill retry unauthenticated...")

        resp = session.get(apiurl + slug, headers=apiheaders, timeout=TIMEOUT)

    resp.raise_for_status()
    return resp.json()

def end_directory(items, sort_methods, content=None, cache=True):
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    if content:
        xbmcplugin.setContent(HANDLE, content)
    for method in sort_methods:
        xbmcplugin.addSortMethod(HANDLE, method)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache)

FOLDER_SORTS = (
    xbmcplugin.SORT_METHOD_UNSORTED,
    xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE,
    xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE,
)

def folder_item(title, season=0):
    item = xbmcgui.ListItem(label=title, offscreen=True)
    info = item.getVideoInfoTag()
    info.setTitle(title)
    info.setTvShowTitle(SHOW_TITLE)
    if season:
        info.setSeason(season)
        info.setMediaType('season')
    return item

def entry_video(entry):
    return getem(entry, 'video', default={}) or getem(entry, 'livestream', default={})

def is_episode(video):
    # aftershows and roundtables also have season/episode numbers (of the episode they
    # discuss), and specials are "episode"s without a season, so they aren't episodes
    return getem(video, 'video_category', default='') == 'episode' and getem(video, 'seasonNumber', default=0) > 0

def list_main():
    data = api_query('menu-list')

    items = []
    def add_page(slug, title):
        if slug and title and slug != 'home':
            m = re.fullmatch(r'season-(\d+)', slug)
            item = folder_item(title.strip(), int(m.group(1)) if m else 0)
            items.append((plugin_url(action='page', page=slug), item, True))

    for n in getem(data, 'data', 'menus', default=[]):
        itemtype = getem(n, 'type', default='page')
        if itemtype == 'menu': # "Seasons" is a menu
            for sub in getem(n, 'children', default=[]):
                if getem(sub, 'type', default='page') == 'page':
                    add_page(getem(sub, 'href', default=''), getem(sub, 'name', default=''))
        elif itemtype == 'page':
            add_page(getem(n, 'href', default=''), getem(n, 'name', default=''))
        # store is type "external"

    logged_in = 'Authorization' in apiheaders
    if not logged_in:
        items.append((plugin_url(action='login'), folder_item("Log in"), False))

    # don't cache the "Log in" item, or it would linger after logging in
    end_directory(items, FOLDER_SORTS, cache=DO_CACHE and logged_in)

def list_page(page):
    data = api_query(f'pages/by/{page}')

    items = []
    for section in getem(data, 'data', 'sections', default=[]):
        playlist = getem(section, 'playlist', default={}) or getem(section, default={})
        entries = getem(playlist, 'items', default=[])
        if not entries:
            continue

        slug = getem(playlist, 'slug', default='') or getem(section, 'href', default='')
        title = (getem(section, 'displayTitle', default='') or getem(playlist, 'title', default='')).strip()
        if not slug or not title:
            continue

        # a playlist of one season's episodes is that season; slugs are no help here,
        # since "season-1-inside-season-1" is extras and some seasons' pages have no episodes
        seasons = {getem(v, 'seasonNumber', default=0) for v in map(entry_video, entries) if is_episode(v)}
        item = folder_item(title, seasons.pop() if len(seasons) == 1 else 0)
        items.append((plugin_url(action='playlist', playlist=slug), item, True))

    end_directory(items, FOLDER_SORTS, cache=True)

def list_playlist(playlist):
    data = api_query(f'playlists/{playlist}')

    items = []
    has_episodes = False
    for entry in getem(data, 'data', 'items', default=[]):
        (itemid, item) = content_item(entry, position=len(items)+1)
        if item is None:
            continue
        has_episodes = has_episodes or item.getVideoInfoTag().getMediaType() == 'episode'
        if itemid:
            item.setProperty('IsPlayable', 'true')
            items.append((plugin_url(action='play', playlist=playlist, itemid=itemid), item, False))
        else:
            items.append((plugin_url(action='force_login'), item, False))

    end_directory(items, (
        xbmcplugin.SORT_METHOD_EPISODE,
        xbmcplugin.SORT_METHOD_VIDEO_RUNTIME,
        xbmcplugin.SORT_METHOD_UNSORTED,
        xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE,
    ), content='episodes' if has_episodes else 'videos', cache=False)

def content_item(entry, position):
    # returns (itemid, item); itemid is None for locked videos, item is None to skip the entry
    ep = entry_video(entry)
    if not ep:
        return (None, None)

    locked = getem(ep, 'isLocked', default=False)
    itemid = None if locked else getem(ep, 'videoID', default='')
    if not locked and not itemid:
        return (None, None)

    episode = is_episode(ep)
    # episode titles are like "Season 1 Episode 1: I Have Called You By Name", which
    # repeats the season/episode numbers, so use the bare display_title for those.
    # Aftershows' display_titles are sometimes just "Aftershow", so others use title.
    title = ((episode and getem(ep, 'display_title', default='')) or getem(ep, 'title', default='')).strip()
    if locked:
        title = ('(Locked) ' if 'Authorization' in apiheaders else '(Need Login) ') + title

    # the old app showed "(Upcoming)" from a "state" field; the new API has "starts_at" instead, but it's always null so far

    item = xbmcgui.ListItem(title, offscreen=True)
    info = item.getVideoInfoTag()
    info.setTvShowTitle(SHOW_TITLE)
    info.setTitle(title)
    info.setPlot(getem(ep, 'description', default=''))

    art = {k: v for k, v in getem(ep, 'thumbs', default={}).items() if isinstance(v, str) and v}
    if 'landscape' in art:
        art.setdefault('thumb', art['landscape'])
    if 'portrait' in art:
        art.setdefault('poster', art['portrait'])
    item.setArt(art)

    dur = getem(ep, 'duration', default=0)
    if dur > 0:
        info.setDuration(dur)

    # only real episodes get season/episode numbers, so e.g. an aftershow isn't taken
    # for the episode it discusses (by Trakt, or "next episode" in skins)
    if episode:
        info.setSeason(getem(ep, 'seasonNumber', default=0))
        info.setEpisode(getem(ep, 'episodeNumber', default=0) or position)
        info.setMediaType('episode')
    else:
        info.setMediaType('video')
    # keep the API's order when sorting by episode
    info.setSortEpisode(position)

    return (itemid, item)

def force_login():
    username = addon.getSetting('username')
    if not username:
        addon.openSettings()
        # a fresh instance, so we see what the user just entered
        username = xbmcaddon.Addon().getSetting('username')

    if login(requests.Session(), username):
        # reload the listing so the "Log in" item goes away and locked items unlock
        xbmc.executebuiltin('Container.Refresh')

def play_video(itemid):
    video = api_query(f'videos/{itemid}')
    # each stream is {"url": ..., "type": "hls"}, or maybe a bare URL string
    stream = getem(video, 'details', 'video', 0)
    url = getem(stream, 'url', default='') or getem(stream, default='')

    if not url:
        # locked videos come back with empty details
        log(f'No stream URL for {itemid}', level=xbmc.LOGWARNING)
        notify("This video is locked or unavailable")
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem(offscreen=True))
        return

    import inputstreamhelper
    if not inputstreamhelper.Helper('hls').check_inputstream():
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem(offscreen=True))
        return

    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setContentLookup(False)
    item.setProperty('inputstream', 'inputstream.adaptive')
    if kodi_version() < 21:
        # deprecated in Kodi 21 and removed in 22, where ISA detects HLS from the mime type
        item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

if __name__ == '__main__':
    PLUGIN_BASE = sys.argv[0]
    HANDLE = int(sys.argv[1])
    args = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}

    action = args.get('action')
    try:
        if not action:
            list_main()
        elif action == 'page':
            list_page(args['page'])
        elif action == 'playlist':
            list_playlist(args['playlist'])
        elif action == 'play':
            play_video(args['itemid'])
        elif action == 'login' or action == 'force_login':
            force_login()
        else:
            log(f'Unknown action in params: {args}', level=xbmc.LOGERROR)
    except (requests.RequestException, ValueError) as e:
        log(f'Request failed: {e}', level=xbmc.LOGERROR)
        notify("Couldn't load from The Chosen, try again later")
        if action == 'play':
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem(offscreen=True))
        elif action in (None, 'page', 'playlist'):
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
