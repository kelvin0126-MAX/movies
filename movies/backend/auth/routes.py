"""Authentication routes: register, login, logout, profile."""

import uuid
from datetime import datetime, timedelta

import bcrypt
import jwt
from flask import Blueprint, jsonify, request

from backend.auth.middleware import token_required
from config.settings import FLASK_CONFIG, JWT_EXPIRY_HOURS
from database.db import execute_insert, execute_query

auth_bp = Blueprint("auth", __name__)


def _hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password, hashed):
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _generate_token(user_id):
    # jti (JWT ID) ensures every token is unique even for concurrent requests
    # in the same second. Without it, two logins in the same second for the
    # same user produce byte-identical tokens and hit the sessions.token
    # UNIQUE constraint.
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, FLASK_CONFIG["SECRET_KEY"], algorithm="HS256")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if user exists
    existing = execute_query(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username, email),
    )
    if existing:
        return jsonify({"error": "Username or email already exists"}), 409

    # Create user
    password_hash = _hash_password(password)
    user_id = execute_insert(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username, email, password_hash),
    )

    token = _generate_token(user_id)

    # Save session
    expires_at = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    execute_insert(
        "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at.isoformat()),
    )

    return jsonify({
        "message": "Registration successful",
        "user_id": user_id,
        "token": token,
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    # Accept either username or email for login
    identifier = data.get("username", "").strip() or data.get("email", "").strip()
    password = data.get("password", "")

    if not identifier or not password:
        return jsonify({"error": "Username/email and password are required"}), 400

    user = execute_query(
        "SELECT id, username, email, password_hash FROM users WHERE username = ? OR email = ?",
        (identifier, identifier),
        fetchone=True,
    )
    if not user or not _check_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # M4: Opportunistically clean up expired sessions so the table doesn't grow unbounded
    try:
        execute_query(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.utcnow().isoformat(),),
        )
    except Exception:
        pass  # Cleanup is best-effort

    token = _generate_token(user["id"])

    # Save session
    expires_at = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    execute_insert(
        "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user["id"], token, expires_at.isoformat()),
    )

    return jsonify({
        "message": "Login successful",
        "user_id": user["id"],
        "username": user["username"],
        "token": token,
    })


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout(current_user):
    """Invalidate the current session."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    execute_query("DELETE FROM sessions WHERE token = ?", (token,))
    return jsonify({"message": "Logged out successfully"})


@auth_bp.route("/profile", methods=["GET"])
@token_required
def profile(current_user):
    """Get current user profile."""
    return jsonify({
        "user_id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "created_at": current_user["created_at"],
    })
