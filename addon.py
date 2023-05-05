#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import re
import requests
import json
from urllib.parse import parse_qsl, quote_plus

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

PLUGIN_BASE = None
HANDLE = None

# TODO also display "Bonus Content" and "Deep Dives"

def log(txt, *args, level=xbmc.LOGINFO):
    xbmc.log('the-chosen : ' + txt.format(*args), level=level)

def list_all():
    data = {
        'query': 'fragment CoreEpisodeFields on Episode {\n  id\n  guid\n  episodeNumber\n  seasonNumber\n  seasonId\n  subtitle\n  description\n  name\n' + 
                 '  posterCloudinaryPath\n  projectSlug\n  releaseDate\n  source {\n    captions\n    credits\n    duration\n    url\n    __typename\n  }\n' +
                 '  upNext {\n    id\n    guid\n    __typename\n  }\n  __typename\n}\nquery videoList {\n  project(slug: "the-chosen") {\n    seasons {\n' +
                 '      id\n      name\n      episodes {\n        ...CoreEpisodeFields\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n',
        'operationName': 'videoList',
        'variables':{}
    }
    resp = requests.post('https://api.angelstudios.com/graphql', json=data)
    if resp.status_code != 200:
        log('POST graphql failed: code {}', resp.status_code)
        resp = {}
    else:
        resp = resp.json()
    
    return resp.get('data', resp).get('project', resp).get('seasons', [])
 
def list_seasons():
    items = []
    for season in list_all():
        id = season['id']
        item = xbmcgui.ListItem(label=season['name'])
        item.setInfo('video', {
            'title':season['name'], 
            'set':season['name'], 
            'setoverview':season['name'], 
            'season':int(season.get('id')),
            'mediatype':'season'
        })

        url = f'{PLUGIN_BASE}?action=season&id={id}'
        items.append((url, item, True))
    
    
    item = xbmcgui.ListItem(label='Bonus Videos')
    item.setInfo('video', {
        'title':'Bonus Videos', 
        'season':100,
        'mediatype':'season'
    })
    url = f'{PLUGIN_BASE}?action=bonus'
    items.append((url, item, True))
    
    
    item = xbmcgui.ListItem(label='Deep Dives')
    item.setInfo('video', {
        'title':'Deep Dives', 
        'season':101,
        'mediatype':'season'
    })
    url = f'{PLUGIN_BASE}?action=deepDive'
    items.append((url, item, True))
    

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def list_videos(page):
    data = {
        'query':'fragment CoreVideoFields on Video {  id  guid  slug  title  subtitle  page  projectSlug  posterCloudinaryPath  source {    url    credits    duration    name    __typename  }  __typename}\n'+
                 'query getVideos($page: String) {  videos(page: $page) {    ...CoreVideoFields    __typename  }}',
        'operationName': 'getVideos',
        'variables':{'page':page}
    }
    resp = requests.post('https://api.angelstudios.com/graphql', json=data)
    if resp.status_code != 200:
        log('POST graphql failed: code {}', resp.status_code)
        resp = {}
    else:
        resp = resp.json()
    
    items = []
    for video in resp.get('data', resp).get('videos', []):
        item = xbmcgui.ListItem(label=video['title'])
        
        poster = video.get('posterCloudinaryPath', '')
        if poster:
            if not poster.startswith('http'):
                poster = 'https://images.angelstudios.com/image/upload/' + poster
            item.setArt({'landscape':poster, 'thumb':poster})
        
        info = {
            'title':video['title'],
            'plot':video.get('description', video.get('subtitle', '')),
            'episode':video.get('id', 0),
            'season':0,
            'mediatype':'video',
        }
        
        source = video.get('source', {})
        dur = source.get('duration', 0)
        if dur:
            info['duration'] = dur
        
        item.setInfo('video', info)
        item.setProperty('IsPlayable', 'true')
        
        source = quote_plus(source.get("url", ""))
        url = f'{PLUGIN_BASE}?action=play&url={source}'
        items.append((url, item, False))
    
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.endOfDirectory(HANDLE)

def list_episodes(sid):
    episodes = []
    for season in list_all():
        if str(season['id']) == str(sid):
            episodes = season['episodes']
            break
   
    items = []
    for ep in episodes:
        info = {
           'tvshowtitle':'The Chosen',
           'plot':ep.get('description', '')
        }

        if 'subtitle' in ep:
            info['title'] = ep['subtitle']
        else:
            info['title'] = ep['name']
        
        item = xbmcgui.ListItem(info['title'])
        
        poster = ep.get('posterCloudinaryPath', '')
        if poster:
            if not poster.startswith('http'):
                poster = 'https://images.angelstudios.com/image/upload/' + poster
            item.setArt({'landscape':poster, 'thumb':poster})
       
        source = ep.get('source', {})
        dur = source.get('duration', 0)
        if dur:
            info['duration'] = dur
        
        if sid:
            info['mediatype'] = 'episode'
            info['season'] = ep.get('seasonNumber', 0)
            info['episode'] = ep.get('episodeNumber', 0)
        else:
            info['mediatype'] = 'video'
       
        source = quote_plus(source.get("url", ""))
        url = f'{PLUGIN_BASE}?action=play&url={source}'
       
        item.setInfo('video', info)
        item.setProperty('IsPlayable', 'true')
        items.append((url, item, False))
        
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.setContent(HANDLE, 'episode')
    xbmcplugin.endOfDirectory(HANDLE)

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
        list_seasons()
    elif action == 'season':
        list_episodes(args.get('id'))
    elif action == 'bonus':
        list_videos('bonus')
    elif action == 'deepDive':
        list_videos('deepDive')
    elif action == 'play':
        play_video(args.get('url'))
    else:
        log('Unknown action in params: {}', args, level=xbmc.LOGERROR)
