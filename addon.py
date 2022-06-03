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
    resp = requests.post('https://chosen-hydra.vidangel.com/graphql', json=data)
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
        log(url)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    #xbmcplugin.setContent(HANDLE, 'season')
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
           item.setArt({'landscape':poster})
       
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
       log(url)
       
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
   item = xbmcgui.ListItem(path=url, offscreen=True)
   item.setProperty('inputstream','inputstream.adaptive')
   item.setProperty('inputstream.adaptive.manifest_type', 'hls')
   item.setMimeType('application/vnd.apple.mpegurl')
   item.setProperty('IsPlayable', 'true')
   xbmcplugin.setResolvedUrl(HANDLE, True, item)

if __name__ == '__main__':
   PLUGIN_BASE = sys.argv[0]
   HANDLE = int(sys.argv[1])
   
   log('{}', sys.argv)

   if len(sys.argv) > 2 and len(sys.argv[2]) > 1:
       args = dict(parse_qsl(sys.argv[2][1:]))
   else:
       args = {}
   
   action = args.get('action', None)
   if not action:
       list_seasons()
   elif action == 'season':
       list_episodes(args.get('id'))
   elif action == 'play':
       play_video(args.get('url'))
   else:
       log('Unknown action in params: {}', args, level=xbmc.LOGERROR)
