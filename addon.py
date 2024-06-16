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
HEADERS = {
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Accept':'application/json, text/plain, */*',
    'Referer':'https://watch.thechosen.tv/',
    'Host':'watch.thechosen.tv',
    'Accept':'application/json, text/plain, */*',
    #"Sec-Fetch-Dest":"empty",
    #"Sec-Fetch-Mode":"cors",
    #"Sec-Fetch-Site":"cross-site",
}
addon = xbmcaddon.Addon('plugin.video.the-chosen')

def log(txt, *args, level=xbmc.LOGINFO):
    xbmc.log('the-chosen : ' + txt.format(*args), level=level)

pageId = {
        'main':128849018914,
        'old':128849019245,
        's5filming':128849019155,

        #'extras':128849018961,
        'extras':128849019248,

        'roundtables':128849018964,
        #'livestreams':128849019143,
        #'s1':128849018940,
        #'s2':128849018941,
        #'s3':128849018942,
        's4':128849019156,
}

def get_data(page='main'):
    pid = pageId.get(page, page)
    cname = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.the-chosen/cookie.txt')
    try:
        m = os.path.getmtime(cname)
    except:
        m = 0

    if m + 86400*5 < time.time():
        cookie = login()
    else:
        cookie = open(cname, 'r').read()
    
    if cookie:
        HEADERS["Cookie"] = cookie
    resp = requests.get(f'https://watch.thechosen.tv/api/containers/Custom?pageID={pid}&first=100&orderByDir=ASC&orderByField=POSITION', headers=HEADERS)
    if resp.status_code != 200:
        log('GET failed: code {}', resp.status_code)
        return {}

    j = resp.json()
    #open(xbmcvfs.translatePath('special://temp/test.json'),'w').write(json.dumps(j))
    return j

def list_page(page,sub=None,subsub=None):
    items = []
    n = 0
    data = get_data(page)['pageContainers']['edges']
    if sub is not None:
        if sub >= 0 and sub < len(data):
            data = data[sub]['node'].get('itemRefs',{}).get('edges',[])
            if subsub is not None:
                if subsub >= 0 and subsub < len(x):
                    data = x[subsub]['node'].get('itemRefs',{}).get('edges',[])
                else:
                    log(f'Bad sub-sub item of {page}[{sub} - must be in range [0,{len(x)})')
        else:
            log(f'Bad sub page ({sub}) of {page} - must be in range [0,{len(data)})')

    params = f'?action=list&page={page}&sub='
    if sub is not None:
        params += f'{sub}&subsub='

    haveContent = False
    done = set()

    if page == 'main' and sub is None:
        #for i in range(7,0,-1):
        for i in [4]:
            k = f's{i}'
            kn = f'Season {i}'
            if k in pageId and kn not in done:
                done.add(kn)
                item = xbmcgui.ListItem(label=kn)
                info = item.getVideoInfoTag()
                info.setTitle(kn)
                info.setTvShowTitle('The Chosen')
                info.setSortSeason(200 + i)
                info.setMediaType('season')
                items.append((f'{PLUGIN_BASE}?action=list&page=s{i}', item, True))

    n = 0
    for d in data:
        node = d['node']
        nsub = n
        n += 1
        if node.get('itemRef',None):
            node = node['itemRef']
        if node.get('contentItem',None):
            tup = contentItem(node.get('contentItem'), nsub)
            if tup:
                items.append(tup)
                haveContent = True
        else:
            season = node

            if season['title'] in done:
                continue
            done.add(season['title'])
            item = xbmcgui.ListItem(label=season['title'])
            snum = re.findall(r'\d+', season['title'])
            snum = int(snum[0]) if len(snum) > 0 else 100+nsub
            info = item.getVideoInfoTag()
            info.setTitle(season['title'])
            info.setTvShowTitle('The Chosen')
            info.setSeason(snum)
            info.setSortSeason(snum)
            info.setSortEpisode(snum + 1000)
            info.setMediaType('season')
            info.setSetOverview(season['title'])
            info.setSet(season['title'])

            url = f'{PLUGIN_BASE}' + params + str(nsub)
            items.append((url, item, True))
        n += 1

    if page == 'main' and sub is None:
        item = xbmcgui.ListItem(label='Seasons 1-3')
        info = item.getVideoInfoTag()
        info.setTitle('Seasons 1-3')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(201)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=old', item, True))

        item = xbmcgui.ListItem(label='Season 5 Filming')
        info = item.getVideoInfoTag()
        info.setTitle('Seasons 5 Filming')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(205)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=s5filming', item, True))

        item = xbmcgui.ListItem(label='Extras')
        info = item.getVideoInfoTag()
        info.setTitle('Extras')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(298)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=extras', item, True))

        item = xbmcgui.ListItem(label='Roundtables')
        info = item.getVideoInfoTag()
        info.setTitle('Roundtables')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(299)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=roundtables', item, True))

        '''item = xbmcgui.ListItem(label='Livestreams')
        info = item.getVideoInfoTag()
        info.setTitle('Livestreams')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(201)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=livestreams', item, True))'''
        
        #authItem = xbmcgui.ListItem("Login")
        #items.append((f'{PLUGIN_BASE}?action=login', authItem, False))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    if not haveContent:
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    else:
        xbmcplugin.setContent(HANDLE, 'episode')
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def contentItem(ci, esort):
    ep = ci.get('videoItem', None)
    if not ep:
        ep = ci.get('livestreamItem', None)

    if not ep:
        return None

    title = ep['title']
    if not ep.get('hasAccess', True):
        if not addon.getSetting('username'):
          title = '(Need Login) ' + title
        else:
          title = '(No Access) ' + title
    if ep.get('state', '').upper() == 'UPCOMING':
        title = '(Upcoming) ' + title

    item = xbmcgui.ListItem(title)
    info = item.getVideoInfoTag()
    #if not ep.get('hasAccess', True):
    #    info.setOverlay(3)
    info.setTvShowTitle('The Chosen')
    info.setTitle(title)
    info.setPlot(ep.get('description',''))
        
    poster = ep.get('thumbnail', '')
    if poster:
        item.setArt({'landscape':poster, 'thumb':poster})
        info.addAvailableArtwork(poster, 'landscape')
       
    dur = ep.get('duration', 0)
    if dur:
        info.setDuration(int(dur))
        
    m = re.match(r'^\s*S\s*(\d+)\s*E\s*(\d+)\s*:.*$', ep['title'])
    if m:
        info.setMediaType('episode')
        info.setSeason(int(m.group(1)))
        info.setEpisode(int(m.group(2)))
    else:
        info.setMediaType('video')
    info.setSortEpisode(esort)

    dt = ep.get('createdAt', '')
    if dt:
        p = dt.rfind('.')
        if p > 0 and p < len(dt):
            dt = dt[:p] + dt[-1]
        info.setDateAdded(dt)
        item.setDateTime(dt)
   
    url = ep.get('url', '')
    if url:
      source = quote_plus(url)
      url = f'{PLUGIN_BASE}?action=play&url={source}'
       
    item.setProperty('IsPlayable', 'true')
    return (url, item, False)

def play_video(url):
    log('play {}', url)
    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setProperty('inputstream','inputstream.adaptive')
    item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

def login():
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        return None

    session = requests.Session()
    loginurl = "https://watch.thechosen.tv/"
    loginheaders = {
        'Next-Action': '42bfd550d46990e907d7b4bde08d059f83c8cd87'
    }
    json = [{"username":username,"password":password,"subscriptionID":"$undefined"}]
    resp = session.post(loginurl, headers = loginheaders, json = json) 
    
    cookies = session.cookies.get_dict()
    if cookies == {}:
        xbmcgui.Dialog().ok("Login Fail", "Login attempt failed")
        return None
    else:
        cookie_string = '; '.join([f"{key}={value}" for key, value in cookies.items()])
        cname = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.the-chosen/cookie.txt')
        open(cname, 'w').write(cookie_string)
        return cookie_string

if __name__ == '__main__':
    PLUGIN_BASE = sys.argv[0]
    HANDLE = int(sys.argv[1])

    if len(sys.argv) > 2 and len(sys.argv[2]) > 1:
        args = dict(parse_qsl(sys.argv[2][1:]))
    else:
        args = {}
   
    action = args.get('action', None)
    if not action:
        list_page('main', None, None)
    elif action == 'list':
        if 'sub' in args:
            sub = int(args['sub'])
            if 'subsub' in args:
                subsub = args.get('subsub')
            else:
                subsub = None
        else:
            sub = None
            subsub = None
        list_page(args['page'], sub, subsub)
    elif action == 'play':
        play_video(args.get('url'))
    elif action == 'login':
        login()
    else:
        log('Unknown action in params: {}', args, level=xbmc.LOGERROR)

