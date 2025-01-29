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

apiurl = "https://api.frontrow.cc/query"
apiheaders = {
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/134.0',
    'Accept':'application/json, text/plain, */*',
    'Referer': 'https://watch.thechosen.tv/',
    'Origin': 'https://watch.thechosen.tv',
    'Host':'api.frontrow.cc',
    'channelid': '12884901895',
    'x-client-os': 'kodi',
    'x-client-os-version': 'unknown',
    'x-client-platform': 'web',
    'x-client-version': '2.5.664',
    'language' : str(xbmc.getLanguage(xbmc.ISO_639_1)).lower(),
}

cid = addon.getSetting('client-id')
if not cid:
    from uuid import uuid4
    cid = str(uuid4())
    addon.setSetting('client-id', cid)
apiheaders['x-client-id'] = cid

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
    token = None
    username = addon.getSetting('username')
    password = addon.getSetting('password')

    # do we need to rotate this?
    #from uuid import uuid4
    #cid = str(uuid4())
    #addon.setSetting('client-id', cid)
    #apiheaders['x-client-id'] = cid
    
    addon.setSetting('tokenTime', str(int(time.time())))
    if username and password:
        post = {"operationName":"Login","variables":{"ChannelID":"12884901895","Password":password,"Username":username},
                "query":"mutation Login($ChannelID: ID!, $Username: String!, $Password: String!) {\n  login(ChannelID: $ChannelID, Username: $Username, Password: $Password) {\n    accessToken\n    socketToken\n    tokenType\n    __typename\n  }\n}"}
        
        resp = session.post(apiurl, headers=apiheaders, json = post) 
        
        resp_obj = resp.json()
        
        try:
            d = getem(resp_obj, 'data', 'login')
            if d.get('tokenType', None):
                token = d.get('accessToken', '')
                if token:
                    token = d['tokenType'] + " " + d['accessToken']
            else:
                token = d.get('accessToken', '')
                if token:
                    token = 'Bearer ' + token
        except Exception as e:
            log("Login exception: {}", str(e))
            pass

        if token:
            addon.setSetting('authorization', token)
            apiheaders['authorization'] = token
            log('Login OK')
            return True
        
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
            apiheaders['authorization'] = a
            return True
    except:
        pass
    return False

toplevel_query = {
    "operationName":"Channel",
    "variables":{"ChannelID":"12884901895"},
    "query":"query Channel($ChannelID: ID!) {\n  channel(ChannelID: $ChannelID) {\n    id\n    appDownloadQRCode\n    backgroundColor\n    displayName\n    domain\n    donationLanguage\n    label\n    language\n    logo\n    policyURL\n    primaryColor\n    profile\n    supportEmail\n    supportPhone\n    supportURL\n    supportURL\n    termsURL\n    title\n    showViews\n    download: assets(Type: DOWNLOAD_APP) {\n      edges {\n        node {\n          id\n          title\n          url\n          description\n          type\n          contentType\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    background: assets(Type: BACKGROUND_IMAGE) {\n      edges {\n        node {\n          id\n          title\n          url\n          description\n          type\n          contentType\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    favicon: assets(Type: FAVICON) {\n      edges {\n        node {\n          id\n          title\n          url\n          description\n          type\n          contentType\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    donationUrl: assets(Type: DONATE_URL) {\n      edges {\n        node {\n          id\n          title\n          url\n          description\n          type\n          contentType\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    myChannelUser {\n      user {\n        id\n        __typename\n      }\n      subscriptionID\n      __typename\n    }\n    pages {\n      edges {\n        node {\n          id\n          icon\n          title\n          type\n          visibility\n          includeCountries\n          excludeCountries\n          pageHeaders {\n            edges {\n              node {\n                ...BasicPageHeader\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    welcomeVideo {\n      id\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment BasicPageHeader on PageHeader {\n  id\n  visibility\n  image\n  overlay\n  backgroundColor\n  channelID\n  pageID\n  label\n  title\n  description\n  overlayAlignment\n  buttons {\n    title\n    link\n    type\n    icon\n    __typename\n  }\n  createdAt\n  updatedAt\n  excludeCountries\n  contentRef {\n    contentID\n    contentType\n    __typename\n  }\n  __typename\n}"
}

page_query = {
    "operationName":"PageContainers",
    "variables":{
        "orderBy":{"direction":"ASC","field":"POSITION"},
        "channelID":"12884901895",
        "pageID":""
    },
    "query":"query PageContainers($channelID: ID!, $pageID: ID!, $after: Cursor, $first: Int, $before: Cursor, $last: Int, $orderBy: PageContainerUnionOrder = {direction: ASC, field: POSITION}) {\n  pageContainers(\n    ChannelID: $channelID\n    PageID: $pageID\n    After: $after\n    First: $first\n    Before: $before\n    Last: $last\n    OrderBy: $orderBy\n  ) {\n    pageInfo {\n      ...BasicPageInfo\n      __typename\n    }\n    edges {\n      node {\n        ... on SingletonPageContainer {\n          ...BasicSingletonPageContainer\n          __typename\n        }\n        ... on StaticPageContainer {\n          ...BasicStaticPageContainer\n          __typename\n        }\n        ... on DynamicPageContainer {\n          ...BasicDynamicPageContainer\n          __typename\n        }\n        __typename\n      }\n      cursor\n      __typename\n    }\n    totalCount\n    __typename\n  }\n}\n\nfragment BasicPageInfo on PageInfo {\n  startCursor\n  endCursor\n  hasNextPage\n  hasPreviousPage\n  __typename\n}\n\nfragment BasicSingletonPageContainer on SingletonPageContainer {\n  id\n  channelID\n  pageID\n  language\n  visibility\n  position\n  excludeCountries\n  itemRef {\n    ...BasicItemRef\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}\n\nfragment BasicItemRef on ItemRef {\n  id\n  contentType\n  contentID\n  position\n  contentItem {\n    ... on ItemLivestream {\n      livestreamItem: item {\n        ...PageContainerLivestream\n        __typename\n      }\n      __typename\n    }\n    ... on ItemProduct {\n      productItem: item {\n        ...BasicProduct\n        __typename\n      }\n      __typename\n    }\n    ... on ItemVideo {\n      videoItem: item {\n        ...PageContainerVideo\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment PageContainerLivestream on Livestream {\n  duration\n  id\n  hasAccess\n  hoverOffset\n  excludeCountries\n  state\n  thumbnail\n  title\n  url\n  visibility\n  __typename\n}\n\nfragment BasicProduct on Product {\n  channelID\n  compareAtPrice\n  createdAt\n  currency\n  description\n  excludeCountries\n  expiredAt\n  externalID\n  handle\n  id\n  images {\n    url\n    id\n    __typename\n  }\n  includeCountries\n  openURL\n  price\n  styleType\n  title\n  vendor\n  visibility\n  language\n  position\n  productType\n  publishedAt\n  tags {\n    edges {\n      node {\n        ...BasicTag\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  updatedAt\n  visibilityConditionalID\n  __typename\n}\n\nfragment BasicTag on Tag {\n  id\n  value\n  __typename\n}\n\nfragment PageContainerVideo on Video {\n  createdAt\n  duration\n  excludeCountries\n  hasAccess\n  hoverOffset\n  id\n  playbackPosition\n  showViews\n  thumbnail\n  title\n  url\n  views\n  visibility\n  __typename\n}\n\nfragment BasicStaticPageContainer on StaticPageContainer {\n  id\n  channelID\n  pageID\n  title\n  layout\n  language\n  visibility\n  position\n  excludeCountries\n  itemRefs(OrderBy: {direction: ASC, field: POSITION}) {\n    ...BasicItemRefConnection\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}\n\nfragment BasicItemRefConnection on ItemRefConnection {\n  edges {\n    node {\n      ...BasicItemRef\n      __typename\n    }\n    cursor\n    __typename\n  }\n  pageInfo {\n    ...BasicPageInfo\n    __typename\n  }\n  totalCount\n  __typename\n}\n\nfragment BasicDynamicPageContainer on DynamicPageContainer {\n  id\n  channelID\n  pageID\n  title\n  layout\n  language\n  visibility\n  position\n  excludeCountries\n  itemRefs {\n    ...BasicItemRefConnection\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}"
}

subpage_query = {
    "operationName":"PageContainer",
    "variables":{"channelID":"12884901895","pageContainerID":""},
    "query":"query PageContainer($channelID: ID!, $pageContainerID: ID!) {\n  pageContainer(ChannelID: $channelID, PageContainerID: $pageContainerID) {\n    ... on SingletonPageContainer {\n      ...BasicSingletonPageContainer\n      __typename\n    }\n    ... on StaticPageContainer {\n      ...BasicStaticPageContainer\n      __typename\n    }\n    ... on DynamicPageContainer {\n      ...BasicDynamicPageContainer\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment BasicSingletonPageContainer on SingletonPageContainer {\n  id\n  channelID\n  pageID\n  language\n  visibility\n  position\n  excludeCountries\n  itemRef {\n    ...BasicItemRef\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}\n\nfragment BasicItemRef on ItemRef {\n  id\n  contentType\n  contentID\n  position\n  contentItem {\n    ... on ItemLivestream {\n      livestreamItem: item {\n        ...PageContainerLivestream\n        __typename\n      }\n      __typename\n    }\n    ... on ItemProduct {\n      productItem: item {\n        ...BasicProduct\n        __typename\n      }\n      __typename\n    }\n    ... on ItemVideo {\n      videoItem: item {\n        ...PageContainerVideo\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment PageContainerLivestream on Livestream {\n  duration\n  id\n  hasAccess\n  hoverOffset\n  excludeCountries\n  state\n  thumbnail\n  title\n  url\n  visibility\n  __typename\n}\n\nfragment BasicProduct on Product {\n  channelID\n  compareAtPrice\n  createdAt\n  currency\n  description\n  excludeCountries\n  expiredAt\n  externalID\n  handle\n  id\n  images {\n    url\n    id\n    __typename\n  }\n  includeCountries\n  openURL\n  price\n  styleType\n  title\n  vendor\n  visibility\n  language\n  position\n  productType\n  publishedAt\n  tags {\n    edges {\n      node {\n        ...BasicTag\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  updatedAt\n  visibilityConditionalID\n  __typename\n}\n\nfragment BasicTag on Tag {\n  id\n  value\n  __typename\n}\n\nfragment PageContainerVideo on Video {\n  createdAt\n  duration\n  excludeCountries\n  hasAccess\n  hoverOffset\n  id\n  playbackPosition\n  showViews\n  thumbnail\n  title\n  description\n  url\n  views\n  visibility\n  __typename\n}\n\nfragment BasicStaticPageContainer on StaticPageContainer {\n  id\n  channelID\n  pageID\n  title\n  layout\n  language\n  visibility\n  position\n  excludeCountries\n  itemRefs(OrderBy: {direction: ASC, field: POSITION}) {\n    ...BasicItemRefConnection\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}\n\nfragment BasicItemRefConnection on ItemRefConnection {\n  edges {\n    node {\n      ...BasicItemRef\n      __typename\n    }\n    cursor\n    __typename\n  }\n  pageInfo {\n    ...BasicPageInfo\n    __typename\n  }\n  totalCount\n  __typename\n}\n\nfragment BasicPageInfo on PageInfo {\n  startCursor\n  endCursor\n  hasNextPage\n  hasPreviousPage\n  __typename\n}\n\nfragment BasicDynamicPageContainer on DynamicPageContainer {\n  id\n  channelID\n  pageID\n  title\n  layout\n  language\n  visibility\n  position\n  excludeCountries\n  itemRefs {\n    ...BasicItemRefConnection\n    __typename\n  }\n  createdAt\n  updatedAt\n  __typename\n}"
}

def api_query(req_json, **vars):
    if vars:
        req_json = dict(req_json)
        var = req_json.get('variables', {})
        for k,v in vars.items():
            var[str(k)] = str(v)
    
    session = requests.Session()
    
    get_auth(session)

    resp = session.post(apiurl, headers=apiheaders, json=req_json)
    if resp.status_code >= 400:
        xbmcgui.Dialog().ok("API Fail", f"Remote API post failed: {resp.status_code} {resp.reason}")
        return {}
    else:
        return resp.json()

def list_main():
    data = api_query(toplevel_query)
    skip = ['128849018914','128849019104'] # Home, Gift Store

    items = []
    for e in getem(data, 'data', 'channel', 'pages', 'edges'):
        n = e.get('node', {})
        id = n.get('id', '')
        title = n.get('title', '')
        if not title or not id or id in skip:
            continue
        
        item = xbmcgui.ListItem(label=title)
        info = item.getVideoInfoTag()
        info.setTitle(title)
        info.setTvShowTitle('The Chosen')
        info.setMediaType('season')
        items.append((f'{PLUGIN_BASE}?action=page&page={id}', item, True))

    #authItem = xbmcgui.ListItem("Login")
    #items.append((f'{PLUGIN_BASE}?action=login', authItem, False))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=DO_CACHE)

def list_page(page):
    data = api_query(page_query, pageID=page)

    items = []
    #log("D: {}", str(data))
    for e in getem(data, 'data', 'pageContainers', 'edges'):
        
        e = e.get('node', {})
        id = str(e.get('id', ''))
        if not id:
            continue
        
        item = xbmcgui.ListItem(label=e.get('title', ''))
        info = item.getVideoInfoTag()
        info.setTitle(e.get('title', ''))
        info.setTvShowTitle('The Chosen')
        info.setMediaType('season')
        if 'position' in e:
            info.setSortSeason(int(e['position']))

        items.append((f'{PLUGIN_BASE}?action=subpage&page={id}', item, True))

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=DO_CACHE)
        
def list_subpage(page):
    data = api_query(subpage_query, pageContainerID=page)
    thispage = getem(data, 'data', 'pageContainer')

    items = []
    for ve in getem(thispage, 'itemRefs', 'edges'):
        n = ve.get('node', {})
        ci = n.get('contentItem', {})
        if ci:
            it = contentItem(ci, int(n.get('position', 0)))
            if it:
                items.append(it)
    
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.setContent(HANDLE, 'episode')
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=DO_CACHE)
    return

def contentItem(ci, esort=None):
    ep = ci.get('videoItem', None)
    if not ep:
        ep = ci.get('livestreamItem', None)

    if not ep:
        return None

    title = ep['title']
    
    needLogin = False
    if not ep.get('hasAccess', True):
        needLogin = True
        if not addon.getSetting('username'):
          title = '(Need Login) ' + title
        else:
          title = '(No Access) ' + title
    if ep.get('state', '').upper() == 'UPCOMING':
        title = '(Upcoming) ' + title

    item = xbmcgui.ListItem(title)
    info = item.getVideoInfoTag()
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
    
    #m = re.match(r'^\s*S\s*(\d+)\s*E\s*(\d+)\s*:.*$', ep['title'])
    #if m:
    #    info.setMediaType('episode')
    #    info.setSeason(int(m.group(1)))
    #    info.setEpisode(int(m.group(2)))
    
    info.setMediaType('video')
    if esort is not None:
        info.setSortEpisode(esort)
    elif 'position' in ep:
        info.setSortEpisode(int(ep['position']))

    dt = ep.get('createdAt', '')
    if dt:
        p = dt.rfind('.')
        if p > 0 and p < len(dt):
            dt = dt[:p] + dt[-1]
        info.setDateAdded(dt)
        item.setDateTime(dt)
   
    url = ep.get('url', '')
    if needLogin and not url:
        return (f'{PLUGIN_BASE}?action=force_login', item, False)
    
    item.setProperty('IsPlayable', 'true')
    return (f'{PLUGIN_BASE}?action=play&url={quote_plus(url)}', item, False)

def force_login():
    addon.setSetting('tokenTime', '0')

    username = addon.getSetting('username')
    password = addon.getSetting('password')

    if not username or not password:
        xbmcaddon.openSettings()
    
    login(requests.Session())
    xbmc.executebuiltin('Action(Back)')

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
        list_main()
    elif action == 'page':
        list_page(args['page'])
    elif action == 'subpage':
        list_subpage(args['page'])
    elif action == 'play':
        play_video(args.get('url'))
    elif action == 'force_login':
        force_login()
    else:
        log('Unknown action in params: {}', args, level=xbmc.LOGERROR)
