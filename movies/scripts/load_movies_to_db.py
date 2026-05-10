#!/usr/bin/env python3
"""Load processed movie data, stats, and genre cache into the SQLite database."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from config.settings import PROCESSED_DATA_DIR, RAW_DATA_DIR
from database.db import init_db, execute_many, execute_query, get_connection


def load_genres_from_cache():
    """Load TMDB genre cache and update movies table."""
    cache_path = os.path.join(RAW_DATA_DIR, "tmdb_genre_cache.json")
    if not os.path.exists(cache_path):
        print(f"No TMDB genre cache found at {cache_path}, skipping genre update.")
        return

    with open(cache_path, "r") as f:
        genre_cache = json.load(f)

    print(f"Loaded {len(genre_cache)} genre entries from TMDB cache")

    updates = []
    for movie_id_str, genres in genre_cache.items():
        if genres:
            genre_str = "|".join(genres) if isinstance(genres, list) else str(genres)
            updates.append((genre_str, int(movie_id_str)))

    if updates:
        execute_many(
            "UPDATE movies SET genres = ? WHERE id = ?",
            updates,
        )
        print(f"Updated genres for {len(updates)} movies")


def load_movies():
    """Load movies from parquet into SQLite movies table."""
    init_db()

    movies_path = os.path.join(PROCESSED_DATA_DIR, "movies")
    movies_df = pd.read_parquet(movies_path)
    print(f"Loaded {len(movies_df)} movies from parquet")

    # Check existing count
    existing = execute_query("SELECT COUNT(*) as cnt FROM movies", fetchone=True)
    if existing and existing["cnt"] > 0:
        print(f"Movies table already has {existing['cnt']} rows, skipping insert.")
    else:
        # Prepare data: (id, title, genres, year)
        rows = []
        for _, row in movies_df.iterrows():
            movie_id = int(row["movieId"])
            title = str(row.get("title", "Unknown"))
            genres = str(row.get("genres", "")) if pd.notna(row.get("genres")) else ""
            year = int(row["year"]) if pd.notna(row.get("year")) and row.get("year") else None
            rows.append((movie_id, title, genres, year))

        execute_many(
            "INSERT OR IGNORE INTO movies (id, title, genres, year) VALUES (?, ?, ?, ?)",
            rows,
        )
        print(f"Inserted {len(rows)} movies into database")

    # Load genres from TMDB cache
    load_genres_from_cache()

    # Verify
    count = execute_query("SELECT COUNT(*) as cnt FROM movies", fetchone=True)
    genre_count = execute_query(
        "SELECT COUNT(*) as cnt FROM movies WHERE genres != '' AND genres IS NOT NULL",
        fetchone=True,
    )
    print(f"Movies in database: {count['cnt']} ({genre_count['cnt']} with genres)")


def load_movie_stats():
    """Load pre-computed movie stats from parquet into SQLite."""
    stats_path = os.path.join(PROCESSED_DATA_DIR, "movie_stats")
    if not os.path.exists(stats_path):
        print("No movie_stats parquet found, skipping.")
        return

    stats_df = pd.read_parquet(stats_path)
    print(f"Loaded {len(stats_df)} movie stats from parquet")

    # Check existing
    existing = execute_query("SELECT COUNT(*) as cnt FROM movie_stats", fetchone=True)
    if existing and existing["cnt"] > 0:
        print(f"movie_stats already has {existing['cnt']} rows, skipping.")
        return

    rows = []
    for _, row in stats_df.iterrows():
        movie_id = int(row["movieId"])
        avg_rating = float(row.get("avg_rating", row.get("mean_rating", 0)))
        rating_count = int(row.get("rating_count", row.get("count", 0)))
        rows.append((movie_id, avg_rating, rating_count))

    execute_many(
        "INSERT OR IGNORE INTO movie_stats (movie_id, avg_rating, rating_count) VALUES (?, ?, ?)",
        rows,
    )
    print(f"Inserted {len(rows)} movie stats into database")


if __name__ == "__main__":
    load_movies()
    load_movie_stats()
