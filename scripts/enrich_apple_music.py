#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TRACKS_JSON = DATA_DIR / "tracks.json"
TRACKS_JS = DATA_DIR / "tracks.js"
TRACKS_CSV = DATA_DIR / "tracks.csv"
CACHE_JSON = DATA_DIR / "apple_music_cache.json"
SEARCH_URL = "https://itunes.apple.com/search"
COUNTRIES = ("US", "JP")
MIN_CONFIDENCE = 78


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"[’‘`´]", "'", value)
    value = re.sub(r"[‐-‒–—―]", "-", value)
    value = re.sub(r"\b(feat|ft|featuring)\.?\b", " featuring ", value)
    value = re.sub(r"[^\w\s\u3040-\u30ff\u3400-\u9fff]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_parenthetical(value: str) -> str:
    value = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def word_overlap(left: str, right: str) -> float:
    left_words = {word for word in normalize(left).split() if len(word) > 1}
    right_words = {word for word in normalize(right).split() if len(word) > 1}
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(len(left_words), len(right_words))


def text_score(expected: str, actual: str) -> float:
    expected_norm = normalize(expected)
    actual_norm = normalize(actual)
    if not expected_norm or not actual_norm:
        return 0.0
    if expected_norm == actual_norm:
        return 1.0

    expected_base = normalize(strip_parenthetical(expected))
    actual_base = normalize(strip_parenthetical(actual))
    if expected_base and expected_base == actual_base:
        return 0.94

    if expected_norm in actual_norm or actual_norm in expected_norm:
        shorter = min(len(expected_norm), len(actual_norm))
        longer = max(len(expected_norm), len(actual_norm))
        return max(0.72, shorter / longer)

    return min(0.68, word_overlap(expected, actual))


def cache_key(title: str, artist: str) -> str:
    return f"{normalize(title)}::{normalize(artist)}"


def fetch_json(url: str, retries: int = 4) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 J-WAVE playlist checker"})
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in {403, 429} or attempt == retries:
                raise
            time.sleep(attempt * 8)
    raise RuntimeError(f"Failed to fetch {url}")


def search_itunes(title: str, artist: str, country: str) -> list[dict[str, Any]]:
    params = {
        "term": f"{artist} {title}",
        "media": "music",
        "entity": "song",
        "limit": "10",
        "country": country,
    }
    payload = fetch_json(f"{SEARCH_URL}?{urlencode(params)}")
    return [item for item in payload.get("results", []) if item.get("kind") == "song"]


def score_result(title: str, artist: str, result: dict[str, Any]) -> int:
    title_match = text_score(title, result.get("trackName", ""))
    artist_match = text_score(artist, result.get("artistName", ""))
    collection_artist = result.get("collectionArtistName", "")
    if collection_artist:
        artist_match = max(artist_match, text_score(artist, collection_artist) * 0.94)

    confidence = int(round(title_match * 65 + artist_match * 35))
    if result.get("isStreamable"):
        confidence += 2
    return min(confidence, 100)


def find_best_match(title: str, artist: str) -> dict[str, Any]:
    if not title or not artist:
        return {"status": "skipped"}

    best: dict[str, Any] | None = None
    for country in COUNTRIES:
        try:
            results = search_itunes(title, artist, country)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        for result in results:
            confidence = score_result(title, artist, result)
            candidate = {
                "status": "matched" if confidence >= MIN_CONFIDENCE else "low_confidence",
                "confidence": confidence,
                "country": country,
                "apple_music_url": result.get("trackViewUrl", ""),
                "apple_music_track_name": result.get("trackName", ""),
                "apple_music_artist_name": result.get("artistName", ""),
                "apple_music_album_name": result.get("collectionName", ""),
                "apple_music_track_id": result.get("trackId"),
                "apple_music_artist_id": result.get("artistId"),
                "is_streamable": bool(result.get("isStreamable")),
            }
            if not best or candidate["confidence"] > best.get("confidence", 0):
                best = candidate

        if best and best.get("status") == "matched" and best.get("confidence", 0) >= 92:
            break

    if best:
        return best
    return {"status": "not_found"}


def load_cache() -> dict[str, Any]:
    if not CACHE_JSON.exists():
        return {}
    return json.loads(CACHE_JSON.read_text(encoding="utf-8"))


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_JSON.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_match(track: dict[str, Any], match: dict[str, Any]) -> None:
    if match.get("status") == "matched":
        track["apple_music_url"] = match.get("apple_music_url", "")
        track["apple_music_confidence"] = match.get("confidence", 0)
        track["apple_music_track_name"] = match.get("apple_music_track_name", "")
        track["apple_music_artist_name"] = match.get("apple_music_artist_name", "")
        track["apple_music_album_name"] = match.get("apple_music_album_name", "")
    else:
        track["apple_music_url"] = ""
        track["apple_music_confidence"] = 0
        track["apple_music_track_name"] = ""
        track["apple_music_artist_name"] = ""
        track["apple_music_album_name"] = ""


def write_outputs(payload: dict[str, Any]) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    TRACKS_JSON.write_text(json_text + "\n", encoding="utf-8")
    TRACKS_JS.write_text(f"window.TWM_DATA = {json_text};\n", encoding="utf-8")

    tracks = payload.get("tracks", [])
    fieldnames: list[str] = []
    for track in tracks:
        for key in track.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with TRACKS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tracks)


def parse_args(argv: Iterable[str]) -> tuple[int | None, float, bool, bool]:
    args = list(argv)
    limit = None
    sleep_seconds = 0.35
    force = "--force" in args
    retry_errors = "--retry-errors" in args

    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--sleep" in args:
        sleep_seconds = float(args[args.index("--sleep") + 1])

    return limit, sleep_seconds, force, retry_errors


def main(argv: Iterable[str]) -> int:
    limit, sleep_seconds, force, retry_errors = parse_args(argv)
    payload = json.loads(TRACKS_JSON.read_text(encoding="utf-8"))
    tracks = payload.get("tracks", [])
    cache = load_cache()

    unique_tracks: dict[str, tuple[str, str]] = {}
    for track in tracks:
        key = cache_key(track.get("title", ""), track.get("artist", ""))
        if key != "::":
            unique_tracks.setdefault(key, (track.get("title", ""), track.get("artist", "")))

    keys = list(unique_tracks.keys())
    if limit:
        keys = keys[:limit]

    for index, key in enumerate(keys, start=1):
        title, artist = unique_tracks[key]
        cached_status = cache.get(key, {}).get("status")
        if not force and key in cache and not (retry_errors and cached_status == "error"):
            continue
        print(f"[{index}/{len(keys)}] {artist} - {title}", file=sys.stderr)
        cache[key] = find_best_match(title, artist)
        if index % 25 == 0:
            save_cache(cache)
        time.sleep(sleep_seconds)

    save_cache(cache)

    matched = 0
    for track in tracks:
        key = cache_key(track.get("title", ""), track.get("artist", ""))
        match = cache.get(key, {"status": "not_found"})
        apply_match(track, match)
        if track.get("apple_music_url"):
            matched += 1

    payload["apple_music"] = {
        "source": SEARCH_URL,
        "countries": list(COUNTRIES),
        "minimum_confidence": MIN_CONFIDENCE,
        "matched_track_count": matched,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_outputs(payload)
    print(f"Wrote Apple Music links for {matched}/{len(tracks)} tracks", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
