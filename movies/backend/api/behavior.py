"""Behavior tracking API endpoint."""

import time

from flask import Blueprint, jsonify, request

from backend.auth.middleware import token_required
from database.db import execute_insert

behavior_bp = Blueprint("behavior", __name__)


@behavior_bp.route("/", methods=["POST"])
@behavior_bp.route("/log", methods=["POST"])
@token_required
def log_behavior(current_user):
    """
    Log a user behaviour event.

    Expected JSON body:
    {
        "movie_id": int,
        "event_type": "view" | "click" | "search" | "rating",
        "duration": float (optional, in seconds)
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    movie_id = data.get("movie_id")
    event_type = data.get("event_type")
    duration = data.get("duration", 0)

    if movie_id is None or event_type is None:
        return jsonify({"error": "movie_id and event_type are required"}), 400

    valid_events = {"view", "click", "search", "rating"}
    if event_type not in valid_events:
        return jsonify({"error": f"event_type must be one of {valid_events}"}), 400

    # M6: Explicit INTEGER unix timestamp for consistency with ratings.timestamp
    execute_insert(
        "INSERT INTO behaviour (user_id, movie_id, event_type, duration, timestamp) VALUES (?, ?, ?, ?, ?)",
        (current_user["id"], movie_id, event_type, duration, int(time.time())),
    )

    return jsonify({"message": "Behaviour logged"}), 201


@behavior_bp.route("/batch", methods=["POST"])
@token_required
def log_behavior_batch(current_user):
    """
    Log multiple behaviour events at once.

    Expected JSON body:
    {
        "events": [
            {"movie_id": int, "event_type": str, "duration": float},
            ...
        ]
    }
    """
    data = request.get_json()
    if not data or "events" not in data:
        return jsonify({"error": "events array required"}), 400

    valid_events = {"view", "click", "search", "rating"}
    logged = 0
    failed = []

    # M3: Report per-event success/failure instead of silently dropping invalid events
    for idx, event in enumerate(data["events"]):
        movie_id = event.get("movie_id")
        event_type = event.get("event_type")
        duration = event.get("duration", 0)

        if not movie_id or event_type not in valid_events:
            failed.append({"index": idx, "reason": "invalid movie_id or event_type"})
            continue

        try:
            execute_insert(
                "INSERT INTO behaviour (user_id, movie_id, event_type, duration, timestamp) VALUES (?, ?, ?, ?, ?)",
                (current_user["id"], movie_id, event_type, duration, int(time.time())),
            )
            logged += 1
        except Exception as e:
            failed.append({"index": idx, "reason": str(e)})

    status = 201 if logged > 0 else 400
    return jsonify({
        "message": f"Logged {logged} of {len(data['events'])} events",
        "logged": logged,
        "failed": failed,
    }), status
