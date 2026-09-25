"""
Entry point for user-service.

Run with:  python -m app

Responsibilities:
- Read configuration from app.config (PORT, STORAGE_BACKEND, DATA_DIR).
- Instantiate the repository backend and inject it into UserService.
- Create the Flask application, register the API Blueprint, and add the
  /health endpoint.
- Start the HTTP server on the configured PORT.

REQ-USR-07: GET /health → 200 {"status": "ok", "service": "user-service"}
REQ-USR-09: PORT is never hardcoded; missing PORT causes a clear error + exit(1).
"""

import sys

# ---------------------------------------------------------------------------
# Configuration — read once at startup; KeyError means PORT is missing.
# ---------------------------------------------------------------------------
try:
    from app.config import PORT, STORAGE_BACKEND, DATA_DIR
except KeyError as exc:
    print(
        f"[user-service] ERROR: required environment variable {exc} is not set. "
        "Set PORT before starting the service.",
        file=sys.stderr,
    )
    sys.exit(1)
except ValueError as exc:
    print(
        f"[user-service] ERROR: invalid value for PORT — {exc}. "
        "PORT must be a valid integer.",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
from flask import Flask, jsonify

from app.repository import get_repository
from app.domain.user_service import UserService
from app.api.users import users_bp


def create_app() -> Flask:
    """Build and configure the Flask application."""
    app = Flask(__name__)

    # Instantiate storage backend and domain service, then attach to app
    # so that request handlers can retrieve them via current_app.extensions.
    repo = get_repository(STORAGE_BACKEND, DATA_DIR)
    service = UserService(repo)
    app.extensions["user_service"] = service

    # REQ-USR-07: lightweight health check — no dependency on storage.
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "user-service"}), 200

    # Register the users Blueprint (POST/GET/PUT/PATCH/DELETE /api/v1/users)
    app.register_blueprint(users_bp)

    return app


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=PORT)
