"""
Recommendation service layer.
Connects trained models to the Flask API.
Manages recommendation caching for response time targets (<200ms).
"""

import logging
from datetime import datetime, timedelta

from config.settings import RECOMMENDATIONS_CACHE_TTL_HOURS
from database.db import execute_many, execute_query

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating and caching recommendations."""

    def get_recommendations(self, user_id, n=20):
        """
        Get recommendations for a user.
        Checks cache first, then user-based recs, falls back to popularity.
        """
        # Check cache
        cached = self._get_cached(user_id, n)
        if cached:
            return cached

        # Try to recommend based on user's rated genres
        user_recs = self._get_genre_based_recs(user_id, n)
        if user_recs:
            self._cache_recommendations(user_id, user_recs, algorithm="genre_profile")
            return user_recs

        # Fall back to popularity-based recommendations
        recs = self.get_popular_movies(n=n)

        # Cache results
        self._cache_recommendations(user_id, recs, algorithm="popular")

        return recs

    def _get_genre_based_recs(self, user_id, n):
        """
        Recommend based on the user's actual genre preferences.

        Algorithm:
          1. Pull all (rating, genres) pairs for the user
          2. Build per-genre score: sum(rating - 3.0) so above-3 reinforces,
             below-3 down-weights
          3. Pull a wide pool of un-rated movies that contain ANY positive
             genre, then re-score in Python by genre overlap × user_genre_score
             so candidates matching MULTIPLE preferred genres rank highest.
          4. Apply a small popularity boost for tie-breaking, but the dominant
             signal is genre fit so the user actually sees their preferred
             genres reflected back.
        """
        # Pull rated movies WITH their genres in one query
        rated = execute_query(
            """SELECT r.movie_id, r.rating, m.genres
               FROM ratings r
               JOIN movies m ON r.movie_id = m.id
               WHERE r.user_id = ?""",
            (user_id,),
        )
        if not rated:
            return None

        rated_ids = set(r["movie_id"] for r in rated)

        # Build genre preference profile from user's ratings
        genre_scores = {}
        for r in rated:
            if not r["genres"]:
                continue
            weight = float(r["rating"]) - 3.0  # mean-centered
            for g in r["genres"].split("|"):
                g = g.strip()
                if g:
                    genre_scores[g] = genre_scores.get(g, 0.0) + weight

        positive_genres = {g: s for g, s in genre_scores.items() if s > 0}
        if not positive_genres:
            return None

        # Pool: movies matching ANY positive genre (broad pool, then re-score)
        rated_placeholders = ",".join("?" for _ in rated_ids) if rated_ids else "NULL"
        genre_conditions = " OR ".join("m.genres LIKE ?" for _ in positive_genres)

        pool = execute_query(
            f"""SELECT m.id, m.title, m.genres, m.year,
                       m.poster_path, m.backdrop_path, m.overview,
                       COALESCE(ms.avg_rating, 0) as avg_rating,
                       COALESCE(ms.rating_count, 0) as rating_count
                FROM movies m
                JOIN movie_stats ms ON m.id = ms.movie_id
                WHERE m.id NOT IN ({rated_placeholders})
                  AND ({genre_conditions})
                  AND ms.rating_count >= 50
                LIMIT 500""",
            list(rated_ids) + [f"%{g}%" for g in positive_genres],
        )

        if not pool:
            return None

        # Re-score in Python: dominated by genre fit, popularity is tie-break
        scored = []
        for row in pool:
            row_d = dict(row)
            movie_genres = (row_d.get("genres") or "").split("|")
            genre_fit = sum(
                positive_genres.get(g.strip(), 0.0)
                for g in movie_genres
                if g.strip()
            )
            if genre_fit <= 0:
                continue
            popularity = float(row_d["avg_rating"]) * (1.0 + min(row_d["rating_count"], 200000) / 200000.0)
            row_d["_score"] = genre_fit * 10.0 + popularity
            scored.append(row_d)

        scored.sort(key=lambda r: r["_score"], reverse=True)
        # Strip internal scoring field
        for r in scored:
            r.pop("_score", None)
        return scored[:n] if scored else None

    def get_similar_movies(self, movie_id, n=10):
        """Get content-similar movies based on genre overlap or similar ratings."""
        # Genre-based similarity via SQL
        movie = execute_query(
            "SELECT genres, year FROM movies WHERE id = ?",
            (movie_id,),
            fetchone=True,
        )
        if not movie:
            return []

        # Try genre-based similarity first
        # Filter out empty strings that arise from "".split("|") == [""]
        # or "Action||Drama".split("|") == ["Action", "", "Drama"]
        if movie["genres"]:
            genres = [g for g in movie["genres"].split("|") if g.strip()]
            if genres:
                conditions = " OR ".join("m.genres LIKE ?" for _ in genres)
                params = [f"%{g}%" for g in genres]
                params.extend([movie_id, n])

                similar = execute_query(
                    f"""SELECT m.id, m.title, m.genres, m.year, m.poster_path, m.backdrop_path, m.overview,
                               COALESCE(ms.avg_rating, 0) as avg_rating,
                               COALESCE(ms.rating_count, 0) as rating_count
                        FROM movies m
                        LEFT JOIN movie_stats ms ON m.id = ms.movie_id
                        WHERE ({conditions}) AND m.id != ?
                        ORDER BY ms.avg_rating DESC
                        LIMIT ?""",
                    params,
                )
                if similar:
                    return [dict(m) for m in similar]

        # Fallback: similar by year and high ratings
        # Explicit None-check so a legitimate year=0 wouldn't silently become 2000
        year = movie["year"] if movie["year"] is not None else 2000
        similar = execute_query(
            """SELECT m.id, m.title, m.genres, m.year, m.poster_path, m.backdrop_path, m.overview,
                      COALESCE(ms.avg_rating, 0) as avg_rating,
                      COALESCE(ms.rating_count, 0) as rating_count
               FROM movies m
               JOIN movie_stats ms ON m.id = ms.movie_id
               WHERE m.id != ? AND ABS(m.year - ?) <= 3
               AND ms.rating_count >= 100
               ORDER BY ms.avg_rating DESC
               LIMIT ?""",
            (movie_id, year, n),
        )

        return [dict(m) for m in similar]

    def get_popular_movies(self, n=20):
        """Get popular movies sorted by weighted rating."""
        # First try with user ratings in the app
        movies = execute_query(
            """SELECT m.id, m.title, m.genres, m.year, m.poster_path, m.backdrop_path, m.overview,
                      AVG(r.rating) as avg_rating,
                      COUNT(r.id) as rating_count
               FROM movies m
               JOIN ratings r ON m.id = r.movie_id
               GROUP BY m.id
               HAVING rating_count >= 1
               ORDER BY avg_rating DESC, rating_count DESC
               LIMIT ?""",
            (n,),
        )

        # If no user ratings exist yet, fall back to movie_stats from preprocessing
        if not movies:
            movies = execute_query(
                """SELECT m.id, m.title, m.genres, m.year, m.poster_path, m.backdrop_path, m.overview,
                          COALESCE(ms.avg_rating, 0) as avg_rating,
                          COALESCE(ms.rating_count, 0) as rating_count
                   FROM movies m
                   LEFT JOIN movie_stats ms ON m.id = ms.movie_id
                   WHERE ms.rating_count >= 100
                   ORDER BY ms.avg_rating DESC, ms.rating_count DESC
                   LIMIT ?""",
                (n,),
            )

        # Last resort: just return movies by id
        if not movies:
            movies = execute_query(
                """SELECT id, title, genres, year, 0 as avg_rating, 0 as rating_count
                   FROM movies ORDER BY year DESC LIMIT ?""",
                (n,),
            )

        return [dict(m) for m in movies]

    def _get_cached(self, user_id, n):
        """Retrieve cached recommendations if still valid."""
        cutoff = (
            datetime.utcnow() - timedelta(hours=RECOMMENDATIONS_CACHE_TTL_HOURS)
        ).isoformat()

        cached = execute_query(
            """SELECT rc.movie_id as id, rc.score, rc.algorithm,
                      m.title, m.genres, m.year,
                      m.poster_path, m.backdrop_path, m.overview,
                      COALESCE(ms.avg_rating, 0) as avg_rating,
                      COALESCE(ms.rating_count, 0) as rating_count
               FROM recommendations_cache rc
               JOIN movies m ON rc.movie_id = m.id
               LEFT JOIN movie_stats ms ON m.id = ms.movie_id
               WHERE rc.user_id = ? AND rc.generated_at > ?
               ORDER BY rc.score DESC
               LIMIT ?""",
            (user_id, cutoff, n),
        )

        if cached:
            return [dict(c) for c in cached]
        return None

    def _cache_recommendations(self, user_id, recommendations, algorithm="hybrid"):
        """Store recommendations in cache."""
        # Clear old cache for this user
        execute_query(
            "DELETE FROM recommendations_cache WHERE user_id = ?",
            (user_id,),
        )

        # Insert new cache entries
        rows = [
            (user_id, rec.get("id", rec.get("movie_id")),
             rec.get("score", rec.get("avg_rating", 0)), algorithm)
            for rec in recommendations
            if rec.get("id") or rec.get("movie_id")
        ]

        if rows:
            execute_many(
                """INSERT INTO recommendations_cache
                   (user_id, movie_id, score, algorithm)
                   VALUES (?, ?, ?, ?)""",
                rows,
            )
