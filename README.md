# Travelling Without Moving Played Checker

A small local checker for the J-WAVE `TRAVELLING WITHOUT MOVING` backnumber archive.

## Refresh the data

```sh
python3 scripts/scrape_jwave.py
python3 scripts/enrich_apple_music.py
```

Apple Music matching uses Apple's public search API and only writes links for confident title/artist matches. If Apple rate-limits a run, wait a while and rerun the enrichment script; it uses `data/apple_music_cache.json` to skip work it has already resolved.

The scripts write:

- `data/tracks.json`
- `data/tracks.csv`
- `data/tracks.js`
- `data/apple_music_cache.json`

Open `index.html` directly in a browser, or run:

```sh
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.
