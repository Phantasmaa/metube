# Smart music flow — verification report

Date: 2026-10-22. Scope: `/root/metube`; no other service restarted.

## What changed
- `app/main.py`: public-only asynchronous metadata lookup and SoundCloud alternative search; bounded concurrency/timeouts, metadata/search extract in worker threads, query/result caps, no cookies, no redirects for fixed-provider oEmbed requests, Spotify track URL normalization including `/intl-es/`, Spotify public JSON-LD/OG fallback for artist, strict YouTube video ID handling, and Spanish errors. Identification and search do not download.
- `app/tests/test_api.py`: regression tests for Spotify locale normalization/public oEmbed and YouTube Music oEmbed metadata lookup.
- `ui/src/app/app.ts`, `ui/src/app/app.html`, `ui/src/app/services/downloads.service.ts`: single visible primary `Buscar opciones` button/URL input. Detects Spotify/Music for automatic identification + candidate search; all other URLs run video analysis. Manual title/artist fields appear only when public metadata cannot identify the song. Candidate download action remains a separate explicit click. Changed automatic-download-free processing and Spanish messages.
- Preserved all previous uncommitted changes and untracked files. Backup: `/root/metube-backup-smart-music-20261022.tar.gz`.

## Test/build results after last source edit
- `python -m compileall -q app`: passed.
- `.venv/bin/pytest app/tests/ -q`: **331 passed**.
- `cd ui && pnpm exec ng build`: passed (Angular bundle at `ui/dist/metube`).
- `cd ui && pnpm exec ng test --watch=false`: **7 test files, 40 passed**.
- `cd ui && pnpm run lint`: passed (initially flagged `Array<T>` style; fixed and rerun).
- `systemctl restart metube.service`: service active; HTTP `GET /` returned 200, 6221 bytes.

## Live URL trials (real public requests; no download was queued)
- Spotify input `https://open.spotify.com/intl-es/track/5pS1hoVW3gYiqE54R04Egg`: official Spotify public oEmbed returned HTTP 200. Its actual metadata title is **“I Tune In”** (not the previous fabricated/example title); public Spotify metadata yielded artist **Cryo**. The real endpoint search returned 8 SoundCloud candidate entries; the first two are `I Tune In` by Cryo (351.404s and 341.917s). API returned HTTP 200 with `track`, query, candidates, and warning that results may be versions/covers/remixes. Browser verified: one visible URL input, one CTA; search showed candidates and no JS errors. No download action was triggered.
- YouTube Music input `https://music.youtube.com/watch?v=Ka8GThTy5Lc`: the actual public YouTube oEmbed endpoint returned **HTTP 404 Not Found**. No YouTube metadata was invented, and the flow showed the manual title/artist fallback only after lookup failure. Browser verified both fields, zero candidate buttons, Spanish warning, and no JS errors. The prior yt-dlp public extraction likewise reported YouTube’s “Sign in to confirm you’re not a bot”; this feature did not use cookies or attempt a bypass.

## Browser limitation
Hermes browser tool’s configured Chrome sandbox failed as root; system Playwright was used with `--no-sandbox` and successfully exercised the served UI. Screenshots: `/root/metube/smart-music-ui.png`, `/root/metube/smart-music-spotify.png`.

## Safety and caveats
- Music identification uses public metadata only (Spotify official fixed oEmbed; YouTube official fixed oEmbed), plus Spotify page metadata only when required; hardcoded hosts, HTTPS, normalized IDs, no redirects, timeouts, and SSRF host constraints.
- Candidate search uses yt-dlp anonymous SoundCloud search only, with `cookiefile=None` and `cookiesfrombrowser=None`; candidates are not availability guarantees.
- Choosing a candidate is explicit and starts the existing MeTube add flow. DRM or access controls are not bypassed.
- The systemd service has pre-existing cookies configured at startup; they were not used by identification/search. The unrelated `metube-zip`, nginx, and Hermes services were not restarted.
