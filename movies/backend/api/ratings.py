"""Rating submission and retrieval API endpoints."""

import logging
import time

from flask import Blueprint, jsonify, request

from backend.auth.middleware import token_required
from database.db import execute_insert, execute_query

logger = logging.getLogger(__name__)

ratings_bp = Blueprint("ratings", __name__)


@ratings_bp.route("/", methods=["POST"])
@token_required
def submit_rating(current_user):
    """Submit or update a movie rating."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    movie_id = data.get("movie_id")
    rating = data.get("rating")

    if movie_id is None or rating is None:
        return jsonify({"error": "movie_id and rating are required"}), 400

    # M5: Coerce to correct types, reject malformed input cleanly
    try:
        movie_id = int(movie_id)
        rating = float(rating)
    except (TypeError, ValueError):
        return jsonify({"error": "movie_id must be int and rating must be numeric"}), 400

    if not (1.0 <= rating <= 5.0):
        return jsonify({"error": "Rating must be between 1 and 5"}), 400

    # Check movie exists
    movie = execute_query(
        "SELECT id FROM movies WHERE id = ?", (movie_id,), fetchone=True
    )
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    # M2: Wrap DB calls so constraint failures surface as clean errors
    try:
        existing = execute_query(
            "SELECT id FROM ratings WHERE user_id = ? AND movie_id = ?",
            (current_user["id"], movie_id),
            fetchone=True,
        )

        timestamp = int(time.time())
        if existing:
            execute_query(
                "UPDATE ratings SET rating = ?, timestamp = ? WHERE user_id = ? AND movie_id = ?",
                (rating, timestamp, current_user["id"], movie_id),
            )
            # C3: Invalidate stale recommendations cache for this user
            execute_query(
                "DELETE FROM recommendations_cache WHERE user_id = ?",
                (current_user["id"],),
            )
            # M9: Explicit 200 for REST clarity on update
            return jsonify({"message": "Rating updated", "rating": rating}), 200
        else:
            execute_insert(
                "INSERT INTO ratings (user_id, movie_id, rating, timestamp) VALUES (?, ?, ?, ?)",
                (current_user["id"], movie_id, rating, timestamp),
            )
            # C3: Invalidate stale recommendations cache for this user
            execute_query(
                "DELETE FROM recommendations_cache WHERE user_id = ?",
                (current_user["id"],),
            )
            return jsonify({"message": "Rating submitted", "rating": rating}), 201
    except Exception as e:
        logger.exception("Failed to persist rating: %s", e)
        return jsonify({"error": "Failed to save rating"}), 500


@ratings_bp.route("/user", methods=["GET"])
@token_required
def get_user_ratings(current_user):
    """Get all ratings by the current user."""
    ratings = execute_query(
        """SELECT r.movie_id, r.rating, r.timestamp, m.title, m.genres, m.year
           FROM ratings r
           JOIN movies m ON r.movie_id = m.id
           WHERE r.user_id = ?
           ORDER BY r.timestamp DESC""",
        (current_user["id"],),
    )
    return jsonify({"ratings": [dict(r) for r in ratings]})


@ratings_bp.route("/movie/<int:movie_id>", methods=["GET"])
def get_movie_ratings(movie_id):
    """Get rating distribution for a movie."""
    stats = execute_query(
        """SELECT AVG(rating) as avg_rating,
                  COUNT(*) as total_ratings,
                  SUM(CASE WHEN rating >= 4.0 THEN 1 ELSE 0 END) as positive_count
           FROM ratings WHERE movie_id = ?""",
        (movie_id,),
        fetchone=True,
    )
    return jsonify(dict(stats) if stats else {"avg_rating": 0, "total_ratings": 0})
