"""Recommendation API endpoint."""

from flask import Blueprint, jsonify, request

from backend.auth.middleware import token_required
from backend.services.recommendation_service import RecommendationService
from config.settings import (
    MAX_RECOMMENDATIONS,
    TMDB_IMAGE_BASE,
    TMDB_POSTER_SIZE,
    TMDB_BACKDROP_SIZE,
)

recommendations_bp = Blueprint("recommendations", __name__)

rec_service = RecommendationService()


def _enrich(movie):
    """Attach TMDB image URLs to a movie dict."""
    m = dict(movie) if not isinstance(movie, dict) else movie.copy()
    poster = m.pop("poster_path", None)
    backdrop = m.pop("backdrop_path", None)
    m["poster_url"] = f"{TMDB_IMAGE_BASE}/{TMDB_POSTER_SIZE}{poster}" if poster else None
    m["backdrop_url"] = f"{TMDB_IMAGE_BASE}/{TMDB_BACKDROP_SIZE}{backdrop}" if backdrop else None
    return m


@recommendations_bp.route("/", methods=["GET"])
@token_required
def get_recommendations(current_user):
    """Get personalised movie recommendations for the current user."""
    n = request.args.get("n", MAX_RECOMMENDATIONS, type=int)
    n = min(n, MAX_RECOMMENDATIONS)

    recommendations = rec_service.get_recommendations(current_user["id"], n=n)

    return jsonify({
        "user_id": current_user["id"],
        "recommendations": [_enrich(r) for r in recommendations],
        "count": len(recommendations),
    })


@recommendations_bp.route("/similar/<int:movie_id>", methods=["GET"])
def get_similar_movies(movie_id):
    """Get movies similar to a given movie (content-based)."""
    n = request.args.get("n", 10, type=int)
    n = min(n, 50)

    similar = rec_service.get_similar_movies(movie_id, n=n)

    return jsonify({
        "movie_id": movie_id,
        "similar_movies": [_enrich(s) for s in similar],
        "count": len(similar),
    })


@recommendations_bp.route("/popular", methods=["GET"])
def get_popular():
    """Get popular movies (non-personalised fallback)."""
    n = request.args.get("n", 20, type=int)
    n = min(n, 100)

    popular = rec_service.get_popular_movies(n=n)

    return jsonify({
        "movies": [_enrich(p) for p in popular],
        "count": len(popular),
    })
