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

def log(txt, *args, level=xbmc.LOGINFO):
    xbmc.log('the-chosen : ' + txt.format(*args), level=level)

pageId = {
        'main':128849018914,
        'extras':128849018961,
        'roundtables':128849018964,
        'livestreams':128849019143,
}

def get_data(page='main'):
    pid = pageId[page]
    fname = xbmcvfs.translatePath(f'special://temp/thechosen.{page}.json')
    try:
        m = os.path.getmtime(fname)
        if m + 21600 > time.time():
            return json.load(open(fname, 'r'))
    except:
        pass
    resp = requests.get(f'https://watch.thechosen.tv/api/containers/Custom?pageID={pid}&first=100&orderByDir=ASC&orderByField=POSITION', headers=HEADERS)
    if resp.status_code != 200:
        log('GET failed: code {}', resp.status_code)
        return {}

    j = resp.json()
    with open(fname, 'w') as f:
        json.dump(j, f)
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

    n = 0
    haveContent = False
    for d in data:
        node = d['node']
        if node.get('itemRef',None):
            node = node['itemRef']
        if node.get('contentItem',None):
            tup = contentItem(node.get('contentItem'), n)
            if tup:
                items.append(tup)
                haveContent = True
        else:
            season = node
            sid = n

            item = xbmcgui.ListItem(label=season['title'])
            snum = re.findall(r'\d+', season['title'])
            snum = int(snum[0]) if len(snum) > 0 else 100+n
            info = item.getVideoInfoTag()
            info.setTitle(season['title'])
            info.setTvShowTitle('The Chosen')
            info.setSeason(snum)
            info.setSortSeason(snum)
            info.setSortEpisode(snum + 1000)
            info.setMediaType('season')
            info.setSetOverview(season['title'])
            info.setSet(season['title'])

            url = f'{PLUGIN_BASE}' + params + str(n)
            items.append((url, item, True))
        n += 1

    if page == 'main' and sub is None:
        item = xbmcgui.ListItem(label='Extras')
        info = item.getVideoInfoTag()
        info.setTitle('Extras')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(200)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=extras', item, True))

        item = xbmcgui.ListItem(label='Roundtables')
        info = item.getVideoInfoTag()
        info.setTitle('Roundtables')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(201)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=roundtables', item, True))

        item = xbmcgui.ListItem(label='Livestreams')
        info = item.getVideoInfoTag()
        info.setTitle('Livestreams')
        info.setTvShowTitle('The Chosen')
        info.setSortSeason(201)
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=list&page=livestreams', item, True))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    if not haveContent:
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_DATEADDED)
    else:
        xbmcplugin.setContent(HANDLE, 'episode')
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def contentItem(ci, enum):
    ep = ci.get('videoItem', None)
    if not ep:
        ep = ci.get('livestreamItem', None)

    if not ep:
        return None

    item = xbmcgui.ListItem(ep['title'])
    info = item.getVideoInfoTag()
    info.setTvShowTitle('The Chosen')
    info.setTitle(ep['title'])
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
    info.setSortEpisode(enum)

    dt = ep.get('createdAt', '')
    if dt:
        p = dt.rfind('.')
        if p > 0 and p < len(dt):
            dt = dt[:p] + dt[-1]
        info.setDateAdded(dt)
        
    source = quote_plus(ep.get('url', ''))
    url = f'{PLUGIN_BASE}?action=play&url={source}'
       
    item.setProperty('IsPlayable', 'true')
    if dt:
        item.setDateTime(dt)
    return (url, item, False)

def play_video(url):
    log('play {}', url)
    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setProperty('inputstream','inputstream.adaptive')
    item.setProperty('inputstream.adaptive.manifest_type', 'hls')
    item.setMimeType('application/vnd.apple.mpegurl')
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

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
    else:
        log('Unknown action in params: {}', args, level=xbmc.LOGERROR)

