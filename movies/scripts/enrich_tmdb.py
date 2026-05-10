#!/usr/bin/env python3
"""
Enrich movies in the database with TMDB metadata:
  - poster_path, backdrop_path
  - overview (synopsis)
  - genres (| separated, overwrites if stronger)
  - tmdb_id (for cross-reference)

Runs against all movies where tmdb_id IS NULL.
Rate-limited to 40 requests / 10 seconds (TMDB limit).
Idempotent — safe to re-run; only processes un-enriched rows.
"""

import os
import sys
import time
import logging
from collections import deque

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import TMDB_API_KEY, TMDB_BASE_URL
from config.logging_config import setup_logging
from database.db import get_connection

setup_logging()
logger = logging.getLogger(__name__)

# TMDB free tier: 40 req / 10s. We stay safely under at 35/10s.
WINDOW_SECONDS = 10.0
MAX_REQUESTS_PER_WINDOW = 35
REQUEST_TIMESTAMPS = deque()

SEARCH_URL = f"{TMDB_BASE_URL}/search/movie"
DETAILS_URL = f"{TMDB_BASE_URL}/movie/{{}}"

GENRE_NAME_CACHE = {}  # tmdb_id -> list[str]


def rate_limit():
    """Block until we're within rate limit."""
    now = time.time()
    # Drop timestamps older than window
    while REQUEST_TIMESTAMPS and now - REQUEST_TIMESTAMPS[0] > WINDOW_SECONDS:
        REQUEST_TIMESTAMPS.popleft()
    if len(REQUEST_TIMESTAMPS) >= MAX_REQUESTS_PER_WINDOW:
        sleep_for = WINDOW_SECONDS - (now - REQUEST_TIMESTAMPS[0]) + 0.05
        if sleep_for > 0:
            time.sleep(sleep_for)
    REQUEST_TIMESTAMPS.append(time.time())


def tmdb_get(url, params=None):
    """GET helper with rate limiting, retries, and auth."""
    params = dict(params or {})
    params["api_key"] = TMDB_API_KEY

    for attempt in range(3):
        rate_limit()
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 429:
                # Too many requests — back off
                retry_after = int(r.headers.get("Retry-After", "5"))
                logger.warning(f"429 Too Many Requests, sleeping {retry_after}s")
                time.sleep(retry_after + 1)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt + 1}/3): {e}")
            time.sleep(2 ** attempt)
    return None


def search_movie(title, year):
    """Search TMDB for best match by title + year."""
    # Netflix titles sometimes have formatting quirks — strip common suffixes
    clean_title = title
    for suffix in [": Bonus Material", ": Extended Edition", ": Special Edition"]:
        clean_title = clean_title.replace(suffix, "")
    clean_title = clean_title.strip()

    params = {"query": clean_title, "include_adult": "false", "language": "en-US"}
    if year:
        params["year"] = year

    data = tmdb_get(SEARCH_URL, params)
    if not data or not data.get("results"):
        # Retry without year (year mismatch is common — TMDB release year
        # vs Netflix listing year can differ by 1)
        params.pop("year", None)
        data = tmdb_get(SEARCH_URL, params)

    if not data or not data.get("results"):
        return None

    results = data["results"]
    # Prefer results with matching year (±1 tolerance), else top result
    if year:
        for r in results:
            release_date = r.get("release_date", "")
            if release_date and release_date[:4].isdigit():
                r_year = int(release_date[:4])
                if abs(r_year - year) <= 1:
                    return r
    return results[0]


def enrich_batch(batch_size=200):
    """Fetch enrichment data for movies where tmdb_id IS NULL.

    Ordered by rating_count DESC so the most-viewed/popular movies are
    enriched first — users see real posters on the homepage within minutes
    rather than hours.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT m.id, m.title, m.year
               FROM movies m
               LEFT JOIN movie_stats ms ON m.id = ms.movie_id
               WHERE m.tmdb_id IS NULL
               ORDER BY COALESCE(ms.rating_count, 0) DESC
               LIMIT ?""",
            (batch_size,),
        ).fetchall()

    if not rows:
        return 0

    processed = 0
    matched = 0
    skipped_no_match = 0

    for row in rows:
        movie_id, title, year = row["id"], row["title"], row["year"]

        tmdb_result = search_movie(title, year)

        with get_connection() as conn:
            if tmdb_result is None:
                # Mark with tmdb_id=-1 so we don't retry every run
                conn.execute(
                    "UPDATE movies SET tmdb_id = -1 WHERE id = ?",
                    (movie_id,),
                )
                skipped_no_match += 1
            else:
                tmdb_id = tmdb_result["id"]
                poster_path = tmdb_result.get("poster_path") or None
                backdrop_path = tmdb_result.get("backdrop_path") or None
                overview = tmdb_result.get("overview") or None
                genre_ids = tmdb_result.get("genre_ids", [])

                # Translate genre IDs -> names
                genre_names = []
                for gid in genre_ids:
                    if gid in GENRE_NAME_CACHE:
                        genre_names.append(GENRE_NAME_CACHE[gid])
                genres_str = "|".join(genre_names) if genre_names else None

                conn.execute(
                    """UPDATE movies
                       SET tmdb_id = ?, poster_path = ?, backdrop_path = ?,
                           overview = ?,
                           genres = COALESCE(NULLIF(?, ''), genres)
                       WHERE id = ?""",
                    (tmdb_id, poster_path, backdrop_path, overview,
                     genres_str or "", movie_id),
                )
                matched += 1

        processed += 1
        if processed % 25 == 0:
            logger.info(f"  ...processed {processed}/{len(rows)} in this batch "
                        f"(matched {matched}, no-match {skipped_no_match})")

    logger.info(f"Batch complete: {processed} processed, {matched} matched, "
                f"{skipped_no_match} unmatched.")
    return processed


def load_genre_map():
    """Fetch the TMDB genre list and populate the id->name cache."""
    data = tmdb_get(f"{TMDB_BASE_URL}/genre/movie/list", {"language": "en-US"})
    if not data:
        logger.warning("Failed to fetch genre list, genres won't be resolved")
        return
    for g in data.get("genres", []):
        GENRE_NAME_CACHE[g["id"]] = g["name"]
    logger.info(f"Loaded {len(GENRE_NAME_CACHE)} TMDB genres")


def main():
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY is not set.")
        sys.exit(1)

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as cnt FROM movies").fetchone()["cnt"]
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM movies WHERE tmdb_id IS NULL"
        ).fetchone()["cnt"]

    logger.info(f"TMDB enrichment: {remaining}/{total} movies to process")

    if remaining == 0:
        logger.info("All movies already enriched. Nothing to do.")
        return

    load_genre_map()

    start = time.time()
    total_processed = 0
    while True:
        n = enrich_batch(batch_size=200)
        if n == 0:
            break
        total_processed += n
        elapsed = time.time() - start
        rate = total_processed / elapsed if elapsed > 0 else 0
        eta_seconds = (remaining - total_processed) / rate if rate > 0 else 0
        logger.info(
            f"TOTAL: {total_processed}/{remaining} processed, "
            f"rate={rate:.1f}/s, ETA={eta_seconds/60:.1f} min"
        )

    logger.info(f"Enrichment complete in {(time.time() - start)/60:.1f} min")

    # Final stats
    with get_connection() as conn:
        matched = conn.execute(
            "SELECT COUNT(*) as cnt FROM movies WHERE poster_path IS NOT NULL"
        ).fetchone()["cnt"]
        logger.info(f"Final: {matched}/{total} movies have posters "
                    f"({matched/total*100:.1f}%)")


if __name__ == "__main__":
    main()
