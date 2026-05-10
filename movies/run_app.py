#!/usr/bin/env python3
"""
Start the Flask backend server.

Usage:
    python run_app.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.logging_config import setup_logging
from config.settings import FLASK_CONFIG

setup_logging()

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    print(f"\n  Movie Recommender API running at http://localhost:{FLASK_CONFIG['PORT']}")
    print(f"  Frontend dev server: http://localhost:5173\n")
    # use_debugger=False disables the Werkzeug interactive HTML debugger
    # (which would leak stack traces + SECRET_KEY on any 500). Auto-reload
    # is kept via use_reloader=True for developer ergonomics.
    app.run(
        host=FLASK_CONFIG["HOST"],
        port=FLASK_CONFIG["PORT"],
        debug=FLASK_CONFIG["DEBUG"],
        use_debugger=False,
        use_reloader=FLASK_CONFIG["DEBUG"],
    )
