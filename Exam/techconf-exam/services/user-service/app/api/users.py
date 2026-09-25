"""
Users Blueprint — Flask routes for /api/v1/users.

REQ-USR-01: POST /api/v1/users
REQ-USR-02: GET  /api/v1/users/<id>
REQ-USR-03: GET  /api/v1/users
REQ-USR-04: PUT  /api/v1/users/<id>
REQ-USR-05: PATCH /api/v1/users/<id>
REQ-USR-06: DELETE /api/v1/users/<id>
REQ-USR-B01: email uniqueness (case-insensitive)
REQ-USR-B02: email stored in lowercase
REQ-USR-B03: filters by role and/or email
REQ-USR-10: standard error envelope
"""

from flask import Blueprint, current_app, jsonify, make_response, request

from app.api.errors import error_response
from app.domain.user_service import EmailAlreadyExists, NotFound, ValidationError

users_bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


# ---------------------------------------------------------------------------
# REQ-USR-01 — Create user
# REQ-USR-B01 — Email uniqueness
# REQ-USR-B02 — Email normalisation
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("", methods=["POST"])
def create_user():
    """POST /api/v1/users — create a new user.

    Returns 201 with Location header on success.
    Returns 400 on malformed JSON, 409 on duplicate email, 422 on validation errors.
    """
    data = request.get_json(force=True, silent=True)
    if data is None:
        return error_response(
            code="MALFORMED_JSON",
            message="Request body must be valid JSON.",
            status=400,
        )

    service = current_app.extensions["user_service"]

    try:
        user = service.create_user(data)
    except ValidationError as exc:
        return error_response(
            code="VALIDATION_ERROR",
            message=exc.message,
            status=422,
            details={"field": exc.field, "reason": exc.message},
        )
    except EmailAlreadyExists as exc:
        return error_response(
            code="EMAIL_ALREADY_EXISTS",
            message=str(exc),
            status=409,
        )

    response = make_response(jsonify(user.to_dict()), 201)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return response


# ---------------------------------------------------------------------------
# REQ-USR-03 — List users with pagination and filters
# REQ-USR-B03 — Filters by role and/or email
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("", methods=["GET"])
def list_users():
    """GET /api/v1/users — return a paginated, filtered list of users.

    Query params: page (default 1), page_size (default 20), role, email.
    Returns 200 UserPage on success, 422 on invalid pagination or filter values.
    """
    page = request.args.get("page", "1")
    page_size = request.args.get("page_size", "20")
    role = request.args.get("role", None)
    email = request.args.get("email", None)

    service = current_app.extensions["user_service"]

    try:
        result = service.list_users(page=page, page_size=page_size, role=role, email=email)
    except ValidationError as exc:
        return error_response(
            code="VALIDATION_ERROR",
            message=exc.message,
            status=422,
            details={"field": exc.field, "reason": exc.message},
        )

    return jsonify(result), 200


# ---------------------------------------------------------------------------
# REQ-USR-02 — Get user by id
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("/<user_id>", methods=["GET"])
def get_user(user_id: str):
    """GET /api/v1/users/<user_id> — retrieve a single user by UUID.

    Returns 200 with the User object on success, 404 if the user does not exist.
    """
    service = current_app.extensions["user_service"]

    try:
        user = service.get_user(user_id)
    except NotFound:
        return error_response(
            code="NOT_FOUND",
            message=f"User '{user_id}' not found.",
            status=404,
        )

    return jsonify(user.to_dict()), 200


# ---------------------------------------------------------------------------
# REQ-USR-04 — Replace user (PUT)
# REQ-USR-B01 — Email uniqueness
# REQ-USR-B02 — Email normalisation
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("/<user_id>", methods=["PUT"])
def replace_user(user_id: str):
    """PUT /api/v1/users/<user_id> — replace all editable fields of a user.

    Returns 200 with the updated User on success.
    Returns 400 on malformed JSON, 404 if not found, 409 on duplicate email,
    422 on validation errors.
    """
    data = request.get_json(force=True, silent=True)
    if data is None:
        return error_response(
            code="MALFORMED_JSON",
            message="Request body must be valid JSON.",
            status=400,
        )

    service = current_app.extensions["user_service"]

    try:
        user = service.replace_user(user_id, data)
    except NotFound:
        return error_response(
            code="NOT_FOUND",
            message=f"User '{user_id}' not found.",
            status=404,
        )
    except ValidationError as exc:
        return error_response(
            code="VALIDATION_ERROR",
            message=exc.message,
            status=422,
            details={"field": exc.field, "reason": exc.message},
        )
    except EmailAlreadyExists as exc:
        return error_response(
            code="EMAIL_ALREADY_EXISTS",
            message=str(exc),
            status=409,
        )

    return jsonify(user.to_dict()), 200


# ---------------------------------------------------------------------------
# REQ-USR-05 — Partial update user (PATCH)
# REQ-USR-B01 — Email uniqueness
# REQ-USR-B02 — Email normalisation
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("/<user_id>", methods=["PATCH"])
def update_user(user_id: str):
    """PATCH /api/v1/users/<user_id> — update only the fields present in the body.

    Returns 200 with the updated User on success.
    Returns 400 on malformed JSON, 404 if not found, 409 on duplicate email,
    422 on validation errors or empty/unrecognised body.
    """
    data = request.get_json(force=True, silent=True)
    if data is None:
        return error_response(
            code="MALFORMED_JSON",
            message="Request body must be valid JSON.",
            status=400,
        )

    service = current_app.extensions["user_service"]

    try:
        user = service.update_user(user_id, data)
    except NotFound:
        return error_response(
            code="NOT_FOUND",
            message=f"User '{user_id}' not found.",
            status=404,
        )
    except ValidationError as exc:
        return error_response(
            code="VALIDATION_ERROR",
            message=exc.message,
            status=422,
            details={"field": exc.field, "reason": exc.message},
        )
    except EmailAlreadyExists as exc:
        return error_response(
            code="EMAIL_ALREADY_EXISTS",
            message=str(exc),
            status=409,
        )

    return jsonify(user.to_dict()), 200


# ---------------------------------------------------------------------------
# REQ-USR-06 — Delete user
# REQ-USR-10  — Standard error format
# ---------------------------------------------------------------------------


@users_bp.route("/<user_id>", methods=["DELETE"])
def delete_user(user_id: str):
    """DELETE /api/v1/users/<user_id> — permanently remove a user.

    Returns 204 with no body on success, 404 if the user does not exist.
    """
    service = current_app.extensions["user_service"]

    try:
        service.delete_user(user_id)
    except NotFound:
        return error_response(
            code="NOT_FOUND",
            message=f"User '{user_id}' not found.",
            status=404,
        )

    return "", 204
