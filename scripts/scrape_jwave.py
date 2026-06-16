#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://www.j-wave.co.jp/original/travelling/"
BACKNUMBER_URL = urljoin(BASE_URL, "backnumber/")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


@dataclass
class Episode:
    date: str
    theme: str
    url: str


@dataclass
class Track:
    episode_date: str
    episode_theme: str
    episode_url: str
    track_number: int
    title: str
    artist: str
    raw_title: str
    notes: str


def fetch(url: str, retries: int = 3) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 J-WAVE playlist checker"})
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=30) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc
            time.sleep(attempt)
    raise RuntimeError(f"Failed to fetch {url}")


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t\u3000]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_backnumber(page: str) -> list[Episode]:
    cards = re.findall(r'<div class="bn_card\b.*?</div>\s*</a>\s*</div>', page, flags=re.S)
    episodes: list[Episode] = []
    seen: set[str] = set()

    for card in cards:
        href_match = re.search(r'<a href="([^"]+)">', card)
        date_match = re.search(r'<p class="date">([^<]+)</p>', card)
        title_match = re.search(r'<p class="title">(.*?)</p>', card, flags=re.S)
        if not href_match or not date_match:
            continue

        short_date = clean_text(date_match.group(1))
        parts = short_date.split(".")
        if len(parts) != 3:
            continue

        year = int(parts[0])
        full_year = 2000 + year if year < 90 else 1900 + year
        date = f"{full_year:04d}.{int(parts[1]):02d}.{int(parts[2]):02d}"
        url = urljoin(BACKNUMBER_URL, href_match.group(1))
        theme = clean_text(title_match.group(1)) if title_match else ""

        if url in seen:
            continue
        seen.add(url)
        episodes.append(Episode(date=date, theme=theme, url=url))

    episodes.sort(key=lambda episode: episode.date)
    return episodes


def split_song(raw_title: str) -> tuple[str, str]:
    cleaned = re.sub(r"^[♪♫♬\s]+", "", raw_title).strip()
    if "/" not in cleaned:
        return cleaned, ""
    title, artist = cleaned.rsplit("/", 1)
    return title.strip(), artist.strip()


def parse_episode(page: str, episode: Episode) -> list[Track]:
    posts = re.findall(r'<div class="ms_post">(.*?)</div>\s*</div>', page, flags=re.S)
    tracks: list[Track] = []

    for fallback_number, post in enumerate(posts, start=1):
        number_match = re.search(r'<div class="ms_number">([^<]+)</div>', post)
        song_match = re.search(r'<h3 class="ms_song">(.*?)</h3>', post, flags=re.S)
        if not song_match:
            continue

        raw_number = clean_text(number_match.group(1)) if number_match else str(fallback_number)
        number_match_digits = re.search(r"\d+", raw_number)
        track_number = int(number_match_digits.group(0)) if number_match_digits else fallback_number
        raw_title = clean_text(song_match.group(1))
        title, artist = split_song(raw_title)

        text_match = re.search(r'<div class="textbox">.*?<p>(.*?)</p>', post, flags=re.S)
        notes = clean_text(text_match.group(1)) if text_match else ""

        tracks.append(
            Track(
                episode_date=episode.date,
                episode_theme=episode.theme,
                episode_url=episode.url,
                track_number=track_number,
                title=title,
                artist=artist,
                raw_title=raw_title,
                notes=notes,
            )
        )

    return tracks


def write_outputs(episodes: list[Episode], tracks: list[Track]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    payload = {
        "source": BACKNUMBER_URL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "episode_count": len(episodes),
        "track_count": len(tracks),
        "episodes": [asdict(episode) for episode in episodes],
        "tracks": [asdict(track) for track in tracks],
    }

    json_path = DATA_DIR / "tracks.json"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")

    js_path = DATA_DIR / "tracks.js"
    js_path.write_text(f"window.TWM_DATA = {json_text};\n", encoding="utf-8")

    csv_path = DATA_DIR / "tracks.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(tracks[0]).keys()) if tracks else [])
        if tracks:
            writer.writeheader()
            writer.writerows(asdict(track) for track in tracks)


def main(argv: Iterable[str]) -> int:
    limit = None
    args = list(argv)
    if "--limit" in args:
        index = args.index("--limit")
        limit = int(args[index + 1])

    backnumber = fetch(BACKNUMBER_URL)
    episodes = parse_backnumber(backnumber)
    if limit:
        episodes = episodes[:limit]

    tracks: list[Track] = []
    for index, episode in enumerate(episodes, start=1):
        print(f"[{index}/{len(episodes)}] {episode.date} {episode.url}", file=sys.stderr)
        page = fetch(episode.url)
        tracks.extend(parse_episode(page, episode))
        time.sleep(0.12)

    write_outputs(episodes, tracks)
    print(f"Wrote {len(tracks)} tracks from {len(episodes)} episodes to {DATA_DIR}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
