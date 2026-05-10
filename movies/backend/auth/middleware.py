"""JWT authentication middleware."""

from functools import wraps

import jwt
from flask import jsonify, request

from config.settings import FLASK_CONFIG
from database.db import execute_query


def token_required(f):
    """Decorator to protect routes with JWT authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization token required"}), 401

        token = auth_header.replace("Bearer ", "")

        try:
            payload = jwt.decode(
                token, FLASK_CONFIG["SECRET_KEY"], algorithms=["HS256"]
            )
            user_id = payload["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        # Verify session exists
        session = execute_query(
            "SELECT id FROM sessions WHERE token = ? AND user_id = ?",
            (token, user_id),
            fetchone=True,
        )
        if not session:
            return jsonify({"error": "Session expired or invalid"}), 401

        # Get user
        user = execute_query(
            "SELECT id, username, email, created_at FROM users WHERE id = ?",
            (user_id,),
            fetchone=True,
        )
        if not user:
            return jsonify({"error": "User not found"}), 404

        return f(dict(user), *args, **kwargs)

    return decorated
