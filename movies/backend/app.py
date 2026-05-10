"""
Flask application factory.
Sets up CORS, blueprints, error handlers, and database initialisation.
"""

import logging
import os
import sys
import traceback

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import FLASK_CONFIG, FRONTEND_URL
from database.db import init_db


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.update(FLASK_CONFIG)

    # CORS for React frontend
    CORS(app, origins=[FRONTEND_URL], supports_credentials=True)

    # Initialise database
    with app.app_context():
        init_db()

    # Register blueprints
    from backend.auth.routes import auth_bp
    from backend.api.movies import movies_bp
    from backend.api.ratings import ratings_bp
    from backend.api.recommendations import recommendations_bp
    from backend.api.behavior import behavior_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(movies_bp, url_prefix="/api/movies")
    app.register_blueprint(ratings_bp, url_prefix="/api/ratings")
    app.register_blueprint(recommendations_bp, url_prefix="/api/recommendations")
    app.register_blueprint(behavior_bp, url_prefix="/api/behavior")

    # Health check
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        # Preserve status codes for abort(400) etc., always return JSON
        return jsonify({"error": e.description or e.name}), e.code

    @app.errorhandler(Exception)
    def handle_any_exception(e):
        # Catch-all so we never leak stack traces / filesystem paths /
        # the SECRET_KEY via the Werkzeug debugger HTML page, even when
        # running with debug=True during development.
        logger.exception("Unhandled exception: %s", e)
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

    return app
