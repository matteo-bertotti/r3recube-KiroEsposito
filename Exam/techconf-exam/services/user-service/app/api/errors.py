"""
Error response helper for user-service.

This is the single place in the service that constructs error response bodies,
ensuring every error conforms to the platform-standard envelope:

    {"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}

REQ-USR-10
"""

import json

from flask import Response


def error_response(
    code: str,
    message: str,
    status: int,
    details: dict = None,
) -> Response:
    """Return a Flask Response with the standard platform error body.

    Args:
        code:    UPPER_SNAKE error code (e.g. "NOT_FOUND", "VALIDATION_ERROR").
        message: Human-readable description of the error.
        status:  HTTP status code (e.g. 400, 404, 409, 422, 503).
        details: Optional dict of additional context; defaults to {}.

    Returns:
        A Flask Response object with Content-Type application/json and the
        given HTTP status code.
    """
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        }
    }
    return Response(
        response=json.dumps(body),
        status=status,
        content_type="application/json",
    )
