"""Movie browsing and search API endpoints."""

from flask import Blueprint, jsonify, request

from config.settings import TMDB_IMAGE_BASE, TMDB_POSTER_SIZE, TMDB_BACKDROP_SIZE
from database.db import execute_query

movies_bp = Blueprint("movies", __name__)

# Shared SELECT list — keeps all endpoints consistent. Uses movie_stats
# (pre-computed from Netflix ratings during preprocessing) so avg_rating
# is meaningful even before users rate anything in the app.
_MOVIE_COLUMNS = """
    m.id, m.title, m.genres, m.year,
    m.poster_path, m.backdrop_path, m.overview,
    COALESCE(ms.avg_rating, 0) as avg_rating,
    COALESCE(ms.rating_count, 0) as rating_count
"""
_MOVIE_JOIN = "LEFT JOIN movie_stats ms ON m.id = ms.movie_id"


def _enrich(row):
    """Add fully-qualified TMDB image URLs to a movie row."""
    m = dict(row)
    poster = m.pop("poster_path", None)
    backdrop = m.pop("backdrop_path", None)
    m["poster_url"] = f"{TMDB_IMAGE_BASE}/{TMDB_POSTER_SIZE}{poster}" if poster else None
    m["backdrop_url"] = f"{TMDB_IMAGE_BASE}/{TMDB_BACKDROP_SIZE}{backdrop}" if backdrop else None
    return m


@movies_bp.route("/", methods=["GET"])
def list_movies():
    """List movies with pagination and optional genre filter."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    genre = request.args.get("genre", "")

    # M1: clamp inputs
    if page is None or page < 1:
        page = 1
    if per_page is None or per_page < 1:
        per_page = 20
    per_page = min(per_page, 100)
    offset = (page - 1) * per_page

    if genre:
        movies = execute_query(
            f"""SELECT {_MOVIE_COLUMNS}
                FROM movies m {_MOVIE_JOIN}
                WHERE m.genres LIKE ?
                ORDER BY ms.rating_count DESC
                LIMIT ? OFFSET ?""",
            (f"%{genre}%", per_page, offset),
        )
    else:
        movies = execute_query(
            f"""SELECT {_MOVIE_COLUMNS}
                FROM movies m {_MOVIE_JOIN}
                ORDER BY ms.rating_count DESC
                LIMIT ? OFFSET ?""",
            (per_page, offset),
        )

    return jsonify({
        "movies": [_enrich(m) for m in movies],
        "page": page,
        "per_page": per_page,
    })


@movies_bp.route("/<int:movie_id>", methods=["GET"])
def get_movie(movie_id):
    """Get movie details."""
    movie = execute_query(
        f"""SELECT {_MOVIE_COLUMNS}
            FROM movies m {_MOVIE_JOIN}
            WHERE m.id = ?""",
        (movie_id,),
        fetchone=True,
    )
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    return jsonify(_enrich(movie))


@movies_bp.route("/search", methods=["GET"])
def search_movies():
    """Search movies by title (paginated)."""
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)
    page = request.args.get("page", 1, type=int)

    if not query or len(query) < 2:
        return jsonify({"error": "Search query must be at least 2 characters"}), 400

    # L1/M1: clamp inputs
    if page is None or page < 1:
        page = 1
    if limit is None or limit < 1:
        limit = 20
    limit = min(limit, 100)
    offset = (page - 1) * limit

    movies = execute_query(
        f"""SELECT {_MOVIE_COLUMNS}
            FROM movies m {_MOVIE_JOIN}
            WHERE m.title LIKE ?
            ORDER BY ms.rating_count DESC
            LIMIT ? OFFSET ?""",
        (f"%{query}%", limit, offset),
    )

    return jsonify({
        "movies": [_enrich(m) for m in movies],
        "query": query,
        "page": page,
        "limit": limit,
    })


@movies_bp.route("/genres", methods=["GET"])
def list_genres():
    """Get all unique genres."""
    movies = execute_query(
        "SELECT DISTINCT genres FROM movies WHERE genres IS NOT NULL AND genres != ''"
    )
    genre_set = set()
    for m in movies:
        for g in (m["genres"] or "").split("|"):
            g = g.strip()
            if g and g != "(no genres listed)":
                genre_set.add(g)

    return jsonify({"genres": sorted(genre_set)})
