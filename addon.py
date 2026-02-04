#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import re
import requests
import json
import time
from urllib.parse import parse_qsl, quote_plus

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs

PLUGIN_BASE = ''
DO_CACHE = True # set me to True when not debugging....

addon = xbmcaddon.Addon('plugin.video.the-chosen')

apiurl = "https://api.watch.thechosen.tv/v1/"
apiheaders = {
    'User-Agent':'Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
    'Accept':'application/json, text/plain, */*',
    'Referer': 'https://watch.thechosen.tv/',
    'Origin': 'https://watch.thechosen.tv',
    'Host':'api.watch.thechosen.tv',
    'X-language' : str(xbmc.getLanguage(xbmc.ISO_639_1)).lower(),
    'Accept-Language' : str(xbmc.getLanguage(xbmc.ISO_639_1)).lower(),
}

#cid = addon.getSetting('client-id')
#if not cid:
#    from uuid import uuid4
#    cid = str(uuid4())
#    addon.setSetting('client-id', cid)
#apiheaders['x-client-id'] = cid

def log(txt, *args, level=xbmc.LOGINFO):
    xbmc.log('the-chosen : ' + txt.format(*args), level=level)

def getem(data, *args):
    for a in args:
        if type(a) is int and type(data) is list:
            data = data[a] if a < len(data) else {}
        else:
            data = data.get(a, {})
    return data

def login(session:requests.Session):
    username = addon.getSetting('username')
    #password = addon.getSetting('password')

    addon.setSetting('tokenTime', str(int(time.time())))
    if username:
        addon.setSetting('authorization', '')
        addon.setSetting('tokens', '')

        resp = session.post(apiurl + 'auth/request-otp', headers=apiheaders, json={"email" : username, "locale":apiheaders['X-language']}) 
        
        resp_obj = resp.json()
        
        try:
            if 'isDOBExists' in resp_obj and not resp_obj['isDOBExists']:
                xbmcgui.Dialog().ok("Login Failed", f"Your account does not have a Date of Birth listed. Log in via a web browser and set your birthdate.")
                return False
            
            if 'ok' in resp_obj and not resp_obj['ok']:
                log("ok is false: {}", json.dumps(resp_obj))
                xbmcgui.Dialog().ok("Login Failed", f"Login attempt failed to send OTP code\n{resp.status_code} {resp.reason}")
                return False
            
            code = xbmcgui.Dialog().numeric(0, "Enter One Time code from email")
            if not code:
                return False
            
            resp = session.post(apiurl + 'auth/verify-otp', headers=apiheaders, json={"email" : username, "code":str(code)}) 
            resp_obj = resp.json()

            addon.setSetting('tokens', json.dumps(resp_obj))
            token = f"Bearer {resp_obj['idToken']}"
            addon.setSetting('authorization', token)
            apiheaders['Authorization'] = token
            log('Login OK')
            return True
        except Exception as e:
            log("Login exception: {}", str(e))
            pass
        
        addon.setSetting('authorization', '')
        xbmcgui.Dialog().ok("Login Failed", f"Login attempt failed to produce an authentication token.\n{resp.status_code} {resp.reason}")
    
    return False

def get_auth(session):
    try:
        w = int(addon.getSetting('tokenTime'))
    except:
        w = 0
    
    if w + 86400 < time.time():
        login(session)
    
    try:
        a = addon.getSetting('authorization')
        if a and type(a) is str:
            apiheaders['Authorization'] = a
            return True
    except:
        pass
    return False

def api_query(slug):
    session = requests.Session()
    
    # currently nothing seems to require auth, so dont force through an OTP...
    #get_auth(session)

    resp = session.get(apiurl + slug, headers=apiheaders)
    if resp.status_code >= 400:
        # if the auth failed, just delete the token so the next request will be unauthed
        if resp.status_code == 401 and 'Authorization' in apiheaders:
            del apiheaders['Authorization']
            addon.setSetting('authorization', '')
            
            xbmcgui.Dialog().ok("Auth Fail", f"Authentication failed: {resp.status_code} {resp.reason}\n\nWill retry unauthenticated...")

            resp = session.get(apiurl + slug, headers=apiheaders)
            if resp.status_code < 400:
                return resp.json()
        else:
            xbmcgui.Dialog().ok("API Fail", f"Remote API get {slug} failed: {resp.status_code} {resp.reason}")
        return {}
    else:
        return resp.json()

def list_main():
    data = api_query('menu-list')

    items = []
    def dopage(id, title):
        if not title or not id or id == 'home':
            return
        
        item = xbmcgui.ListItem(label=title)
        info = item.getVideoInfoTag()
        info.setTitle(title)
        info.setTvShowTitle('The Chosen')
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=page&page={id}', item, True))

    for n in getem(data, 'data', 'menus'):
        itemtype = n.get('type', 'page')
        if itemtype == 'menu': # "Seasons" is a menu
            for sub in n.get('children', []):
                subtype = sub.get('type', 'page')
                if subtype == 'page':
                    dopage(sub.get('href', ''), sub.get('name', ''))
        elif itemtype == 'page':
            dopage(n.get('href', ''), n.get('name', ''))
        # store is type "external"

    authItem = xbmcgui.ListItem("Log in")
    items.append((f'{PLUGIN_BASE}?action=login', authItem, False))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=DO_CACHE)

def list_page(page):
    data = api_query(f'pages/by/{page}')

    items = []
    season = 0
    #log("D: {}", str(data))
    for n in getem(data, 'data', 'sections'):
        if n.get('source', '') != 'playlist':
            continue

        title = n.get('displayTitle', '')
        id = n.get('href', '')

        n = n.get('playlist', n)

        if not n.get('items', []):
            continue

        id = n.get('slug', id)
        if not id:
            continue
        
        if not title:
            title = n.get('title', '')
            if not title:
                continue

        m = re.match(r'.*season-(\d+)$', id)
        if m:
            season = int(m.group(1))

        item = xbmcgui.ListItem(label=title)
        info = item.getVideoInfoTag()
        info.setTitle(title)
        info.setTvShowTitle('The Chosen')
        info.setMediaType('season')
        if season:
            info.setSeason(season)
        items.append((f'{PLUGIN_BASE}?action=playlist&playlist={id}&season={season}', item, True))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=DO_CACHE)

def list_playlist(playlist, season=0):
    data = api_query(f'playlists/{playlist}')

    items = []
    esort = 1
    #log("D: {}", str(data))
    for item in getem(data, 'data', 'items'):
        (itemid, item) = contentItem(item, season=season, episode=len(items)+1)
        if not itemid:
            if item is not None:
                items.append((f'{PLUGIN_BASE}?action=force_login', item, False))
        else:
            item.setProperty('IsPlayable', 'true')
            items.append((f'{PLUGIN_BASE}?action=play&playlist={playlist}&itemid={itemid}', item, False))
    
    #with open(xbmcvfs.translatePath(f'special://temp/the-chosen.{page}.json'), 'w') as f:
    #    json.dump(urls, f)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.setContent(HANDLE, 'episode')
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def contentItem(ci, season=0, episode=0):
    ep = ci.get('video', None)
    if not ep:
        ep = ci.get('livestream', None)

    if not ep:
        return (None, None)

    if not episode:
        episode = ep.get('episodeNumber', episode)
    if not season:
        season = ep.get('seasonNumber', season)

    title = ep['title']
    
    if ep.get('isLocked', False):
        needLogin = True
        if not addon.getSetting('username'):
          title = '(Need Login) ' + title
        else:
          title = '(No Access) ' + title
    else:
        needLogin = False
    
    # old app did this, new app has "starts_at" attribute ... TODO: what is it when its not null??
    #if ep.get('state', '').upper() == 'UPCOMING':
    #    title = '(Upcoming) ' + title

    item = xbmcgui.ListItem(title)
    info = item.getVideoInfoTag()
    info.setTvShowTitle('The Chosen')
    info.setTitle(title)
    info.setPlot(ep.get('description',''))
    
    art = ep.get('thumbs', {})
    if 'landscape' in art and art['landscape']:
        if 'thumb' not in art:
            art['thumb'] = art['landscape']
        if 'portrait' in art and not art['portrait']:
            del art['portrait']
        item.setArt(art)
        for k,v in art.items():
            info.addAvailableArtwork(v, k)
    
    dur = ep.get('duration', 0)
    if dur:
        info.setDuration(int(dur))

    info.setMediaType('video')
    if season:
        info.setSeason(season)
        if episode:
            info.setEpisode(episode)
            info.setMediaType('episode')
    
    if episode is not None:
        info.setSortEpisode(episode)

    # new app doesnt have this information
    #dt = ep.get('createdAt', '')
    #if dt:
    #    p = dt.rfind('.')
    #    if p > 0 and p < len(dt):
    #        dt = dt[:p] + dt[-1]
    #    info.setDateAdded(dt)
    #    item.setDateTime(dt)
   
    if needLogin:
        itemid = None
    else:
        itemid = ep.get('videoID', None)
    return (itemid, item)

def force_login():
    addon.setSetting('tokenTime', '0')

    username = addon.getSetting('username')

    if not username:
        xbmcaddon.openSettings()
    
    login(requests.Session())
    xbmc.executebuiltin('Action(Back)')

def play_video(itemid, playlist):
    log('play {} {}', playlist, itemid)

    #urls = {}
    #with open(xbmcvfs.translatePath(f'special://temp/the-chosen.{page}.json'), 'r') as f:
    #    urls = json.load(f)
    #url = urls.get(itemid, '')

    video = api_query(f'videos/{itemid}')
    url = getem(video, 'details', 'video')
    if url and len(url):
        url = url[0]
    if isinstance(url, dict) and 'url' in url:
        url = url['url']

    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setProperty('inputstream','inputstream.adaptive')
    item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(HANDLE, len(url) > 0, item)

if __name__ == '__main__':
    PLUGIN_BASE = sys.argv[0]
    HANDLE = int(sys.argv[1])

    if len(sys.argv) > 2 and len(sys.argv[2]) > 1:
        args = dict(parse_qsl(sys.argv[2][1:]))
    else:
        args = {}
   
    action = args.get('action', None)
    if not action:
        list_main()
    elif action == 'page':
        list_page(args['page'])
    elif action == 'playlist':
        list_playlist(args['playlist'], int(args.get('season', 0)))
    elif action == 'play':
        play_video(args['itemid'], args.get('playlist', ''))
    elif action == 'force_login':
        force_login()
    else:
        log('Unknown action in params: {}', args, level=xbmc.LOGERROR)
