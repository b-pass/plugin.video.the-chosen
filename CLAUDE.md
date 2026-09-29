# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An unofficial Kodi video addon (`plugin.video.the-chosen`) that browses and plays The Chosen from the watch.thechosen.tv REST API. It targets Kodi 20 (Nexus) through 22. The whole addon is a single script, [addon.py](addon.py), plus the manifest [addon.xml](addon.xml) and [resources/settings.xml](resources/settings.xml).

## Development

There is no build system, test suite, or linter. The code imports Kodi-only modules (`xbmc`, `xbmcgui`, `xbmcplugin`, `xbmcaddon`, `inputstreamhelper`), so it can't run outside Kodi without stubs. At minimum, run:

```
python3 -m py_compile addon.py
python3 -c "import xml.dom.minidom as m; m.parse('addon.xml'); m.parse('resources/settings.xml')"
```

For logic changes, a quick check is to stub the `xbmc*` modules, run `addon.py` with `sys.argv = ['plugin://plugin.video.the-chosen/', '1', '?action=...']` against the live API, and diff the recorded ListItems/URLs before and after. Unauthenticated GETs work. To test for real, install or symlink the repo into Kodi's `addons/` directory as `plugin.video.the-chosen`. Log lines start with `the-chosen : ` in `kodi.log`.

Runtime dependencies are declared in `addon.xml`: `xbmc.python` 3.0.1 (the minimum for Kodi 20, needed for the `InfoTagVideo` setters), `script.module.requests`, and `script.module.inputstreamhelper`. For a release, bump `version` in `addon.xml`; version bumps go in their own commits.

## Architecture

Kodi runs `addon.py` fresh for every navigation step, passing `sys.argv = [plugin_base_url, handle, "?query"]`. The code relies on getting a fresh interpreter each time (module globals like `apiheaders` are per-invocation), so don't enable `reuselanguageinvoker`. The `__main__` block dispatches on the `action` query parameter:

| action | function | API call |
|---|---|---|
| (none) | `list_main` | `menu-list`: top-level pages ("Seasons" is a `menu` with `page` children; `external` items are skipped) |
| `page` | `list_page` | `pages/by/{page}`: sections, each of which becomes a playlist folder |
| `playlist` | `list_playlist` → `content_item` | `playlists/{slug}`: episodes |
| `play` | `play_video` | `videos/{itemid}`: HLS URL from `details.video[0].url`, handed back through `setResolvedUrl` |
| `login` / `force_login` | `force_login` → `login` | v2 OTP endpoints, then `Container.Refresh` |

The dispatch is wrapped so that `requests.RequestException`/`ValueError` produce a notification and a proper failure: `endOfDirectory(succeeded=False)` or `setResolvedUrl(False)`, never a script-error traceback. Every request passes `timeout=TIMEOUT`.

**Don't change the play URL format.** It must stay `?action=play&playlist=<slug>&itemid=<videoID>`, with the parameters in that order. `plugin_url()` keeps insertion order. Kodi stores watched and resume state by this exact path, so changing it resets every user's history. Old folder URLs may carry an ignored `&season=` parameter.

### API and auth

- Base URL is `https://api.watch.thechosen.tv/v1/`. The OTP login endpoints (`otpurl`, `/v2/auth/request-otp` and `/v2/auth/verify-otp`) are v2, not v1.
- `apiheaders` is a module-level dict that gets mutated at runtime: `api_query` loads `Authorization` from settings, and `save_tokens`/`clear_tokens` overwrite or remove it. `'Authorization' in apiheaders` is how the code decides "logged in".
- Login is email plus a one-time code. The only visible setting is `username` (the email). The hidden settings `authorization` (`"Bearer <idToken>"`) and `tokens` (the full token JSON, including `refreshToken`) are declared in `settings.xml` as `level 4` / `visible false`. That file uses the v1 settings format.
- `api_query` handles a 401 by calling `refresh()` once and retrying. `refresh()` clears stored tokens only when the server rejects the refresh with a 4xx. On network errors or 5xx it just drops the header for this run. The API returns 200 with anonymous content for a malformed token, so a 401 only happens for tokens it actually recognizes.
- Locked episodes (`isLocked`) get no `itemid`. They're labeled "(Need Login)" when logged out and "(Locked)" when logged in, and they link to `force_login`. `videos/{id}` for a locked video returns 200 with empty `details`.

### Playback

`play_video` runs `inputstreamhelper.Helper('hls').check_inputstream()` and uses `inputstream.adaptive` with mime type `application/vnd.apple.mpegurl`. The ISA property `inputstream.adaptive.manifest_type` is deprecated in Kodi 21 and removed in 22, so it's set only when `kodi_version() < 21`.

### Conventions

- Use `getem(data, 'a', 'b', 0, ...)` for nested lookups in API responses. It returns `{}` when a key or index is missing, null, or the wrong type. The API's shape changes often (see git history: GraphQL → REST rewrites, season-specific fixes), so parsing is deliberately defensive.
- `log()` takes a finished string; build it with an f-string.
- Season/episode numbers: an episode gets a season only from the API's `seasonNumber`. Then its episode number is its position in the playlist. Items without `seasonNumber` (extras, specials, livestreams) are plain `video` items. The `season-N` slug suffix only labels the folder in `list_page`, because extras playlists like `season-1-inside-season-1` match it too.
- `DO_CACHE` controls `cacheToDisc` for the main menu (only when logged in, so the "Log in" item doesn't linger) and for page listings. Playlist listings are never cached.
