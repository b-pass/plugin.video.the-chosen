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

def getem(data, *keys):
    # walk nested dicts/lists, returning {} if anything along the way is missing or null
    for k in keys:
        if isinstance(k, int) and isinstance(data, list):
            data = data[k] if -len(data) <= k < len(data) else None
        elif isinstance(data, dict):
            data = data.get(k)
        else:
            data = None
        if data is None:
            return {}
    return data

def save_tokens(tokens):
    token = f"Bearer {tokens['idToken']}"
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

        if resp_obj.get('isNewUser', False):
            xbmcgui.Dialog().ok("First Login", "Log in via a web browser to set up your account.")
            return False

        if not resp_obj.get('ageVerified', True):
            xbmcgui.Dialog().ok("Login Failed", "Your account does not have a Date of Birth listed. Log in via a web browser and set your birthdate.")
            return False

        if not resp.ok or not resp_obj.get('ok', True):
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
        tokens = json.loads(addon.getSetting('tokens') or '{}')
    except ValueError:
        tokens = {}
    if not tokens.get('refreshToken'):
        log('No refresh token')
        clear_tokens()
        return False

    status = 0
    try:
        resp = session.post(apiurl + 'auth/refresh', headers=apiheaders, json={"refreshToken" : tokens['refreshToken']}, timeout=TIMEOUT)
        resp.raise_for_status()

        # keep the old refreshToken if the response doesn't include a new one
        tokens.update(resp.json())
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
    info.setTvShowTitle('The Chosen')
    info.setMediaType('season')
    if season:
        info.setSeason(season)
    return item

def list_main():
    data = api_query('menu-list')

    items = []
    def add_page(slug, title):
        if slug and title and slug != 'home':
            items.append((plugin_url(action='page', page=slug), folder_item(title), True))

    for n in getem(data, 'data', 'menus'):
        itemtype = n.get('type', 'page')
        if itemtype == 'menu': # "Seasons" is a menu
            for sub in n.get('children') or []:
                if sub.get('type', 'page') == 'page':
                    add_page(sub.get('href'), sub.get('name'))
        elif itemtype == 'page':
            add_page(n.get('href'), n.get('name'))
        # store is type "external"

    logged_in = 'Authorization' in apiheaders
    if not logged_in:
        items.append((plugin_url(action='login'), xbmcgui.ListItem("Log in", offscreen=True), False))

    # don't cache the "Log in" item, or it would linger after logging in
    end_directory(items, FOLDER_SORTS, cache=DO_CACHE and logged_in)

def list_page(page):
    data = api_query(f'pages/by/{page}')

    items = []
    for section in getem(data, 'data', 'sections'):
        playlist = section.get('playlist') or section
        if not playlist.get('items'):
            continue

        slug = playlist.get('slug') or section.get('href')
        title = section.get('displayTitle') or playlist.get('title')
        if not slug or not title:
            continue

        # only for the folder: extras playlists like "season-1-inside-season-1" match
        # too, so episodes get their season from the API instead
        m = re.search(r'season-(\d+)$', slug)
        item = folder_item(title, int(m.group(1)) if m else 0)
        items.append((plugin_url(action='playlist', playlist=slug), item, True))

    end_directory(items, FOLDER_SORTS, cache=True)

def list_playlist(playlist):
    data = api_query(f'playlists/{playlist}')

    items = []
    for entry in getem(data, 'data', 'items'):
        (itemid, item) = content_item(entry, episode=len(items)+1)
        if item is None:
            continue
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
    ), content='episode', cache=False)

def content_item(entry, episode):
    # returns (itemid, item); itemid is None for locked videos, item is None to skip the entry
    ep = entry.get('video') or entry.get('livestream')
    if not ep:
        return (None, None)

    locked = ep.get('isLocked', False)
    itemid = None if locked else ep.get('videoID')
    if not locked and not itemid:
        return (None, None)

    title = ep.get('title') or ''
    if locked:
        title = ('(Locked) ' if 'Authorization' in apiheaders else '(Need Login) ') + title

    # the old app showed "(Upcoming)" from a "state" field; the new API has "starts_at" instead, but it's always null so far

    item = xbmcgui.ListItem(title, offscreen=True)
    info = item.getVideoInfoTag()
    info.setTvShowTitle('The Chosen')
    info.setTitle(title)
    info.setPlot(ep.get('description') or '')

    art = {k: v for k, v in (ep.get('thumbs') or {}).items() if v}
    if 'landscape' in art:
        art.setdefault('thumb', art['landscape'])
    if 'portrait' in art:
        art.setdefault('poster', art['portrait'])
    item.setArt(art)

    dur = ep.get('duration')
    if dur:
        info.setDuration(int(dur))

    # extras have no season; only real episodes get season/episode numbers
    season = ep.get('seasonNumber')
    if season:
        info.setSeason(int(season))
        info.setEpisode(episode)
        info.setMediaType('episode')
    else:
        info.setMediaType('video')
    info.setSortEpisode(episode)

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
    stream = getem(video, 'details', 'video', 0)
    url = stream.get('url') if isinstance(stream, dict) else stream

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
