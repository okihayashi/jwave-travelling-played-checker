# Travelling Without Moving Played Checker

A small local checker for the J-WAVE `TRAVELLING WITHOUT MOVING` backnumber archive.

## Refresh the data

```sh
python3 scripts/scrape_jwave.py
```

The scraper writes:

- `data/tracks.json`
- `data/tracks.csv`
- `data/tracks.js`

Open `index.html` directly in a browser, or run:

```sh
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.
