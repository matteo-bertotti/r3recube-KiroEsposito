"""
Domain service for user-service.

REQ-USR-01: create_user — validation, email normalisation, uniqueness, persistence.
REQ-USR-02: get_user — retrieve by id.
REQ-USR-03: list_users — pagination and filters.
REQ-USR-04: replace_user — full update (PUT semantics).
REQ-USR-05: update_user — partial update (PATCH semantics).
REQ-USR-06: delete_user — permanent removal.
REQ-USR-B01: email uniqueness (case-insensitive).
REQ-USR-B02: email always stored in lowercase.
REQ-USR-B03: filters by role and/or email.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.domain.models import User

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a field value violates a business constraint (422)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class EmailAlreadyExists(Exception):
    """Raised when the email is already taken by another user (409)."""


class NotFound(Exception):
    """Raised when a requested user does not exist (404)."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_VALID_ROLES = {"attendee", "speaker", "organizer"}

_KNOWN_FIELDS = {"first_name", "last_name", "email", "company", "role"}


def _validate_first_name(value: str) -> None:
    """REQ-USR-01 #5,9 / REQ-USR-04 #4 / REQ-USR-05 #4"""
    if not value or not value.strip():
        raise ValidationError("first_name", "first_name is required and cannot be empty")
    if len(value) > 50:
        raise ValidationError("first_name", "first_name must not exceed 50 characters")


def _validate_last_name(value: str) -> None:
    """REQ-USR-01 #6,10 / REQ-USR-04 #4 / REQ-USR-05 #4"""
    if not value or not value.strip():
        raise ValidationError("last_name", "last_name is required and cannot be empty")
    if len(value) > 50:
        raise ValidationError("last_name", "last_name must not exceed 50 characters")


def _validate_email(value: str) -> str:
    """
    REQ-USR-01 #7,8 / REQ-USR-B02
    Returns the email normalised to lowercase.
    """
    if not value or not value.strip():
        raise ValidationError("email", "email is required and cannot be empty")
    normalised = value.lower()
    if not _EMAIL_RE.match(normalised):
        raise ValidationError("email", "email must be a valid email address")
    return normalised


def _validate_company(value) -> Optional[str]:
    """REQ-USR-01 #11"""
    if value is None:
        return None
    if len(value) > 100:
        raise ValidationError("company", "company must not exceed 100 characters")
    return value


def _validate_role(value: str) -> str:
    """REQ-USR-01 #12"""
    if value not in _VALID_ROLES:
        raise ValidationError(
            "role",
            f"role must be one of: {', '.join(sorted(_VALID_ROLES))}",
        )
    return value


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------


class UserService:
    """
    Business logic layer for the user-service.

    Depends on a ``UserRepository`` injected at construction time; has no
    knowledge of Flask, HTTP, or environment variables.
    """

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # REQ-USR-01
    # ------------------------------------------------------------------

    def create_user(self, data: dict) -> User:
        """
        Validate, normalise, and persist a new user.

        REQ-USR-01: 201 on success, 422 on invalid fields, 409 on duplicate email.
        REQ-USR-B01: email uniqueness (case-insensitive).
        REQ-USR-B02: email stored in lowercase.
        """
        # Validate required fields
        first_name = data.get("first_name")
        if first_name is None:
            raise ValidationError("first_name", "first_name is required")
        _validate_first_name(first_name)

        last_name = data.get("last_name")
        if last_name is None:
            raise ValidationError("last_name", "last_name is required")
        _validate_last_name(last_name)

        email_raw = data.get("email")
        if email_raw is None:
            raise ValidationError("email", "email is required")
        email = _validate_email(email_raw)  # normalised to lowercase

        company = _validate_company(data.get("company"))

        role = data.get("role", "attendee")
        _validate_role(role)

        # REQ-USR-B01: uniqueness check
        if self._repo.find_by_email(email) is not None:
            raise EmailAlreadyExists(f"email '{email}' is already registered")

        # Build and persist
        normalised_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,          # already lowercase
            "company": company,
            "role": role,
        }
        user = User.create(normalised_data)
        self._repo.save(user)
        return user

    # ------------------------------------------------------------------
    # REQ-USR-02
    # ------------------------------------------------------------------

    def get_user(self, user_id: str) -> User:
        """Return the user with the given id, or raise NotFound."""
        user = self._repo.find_by_id(user_id)
        if user is None:
            raise NotFound(f"User '{user_id}' not found")
        return user

    # ------------------------------------------------------------------
    # REQ-USR-03 / REQ-USR-B03
    # ------------------------------------------------------------------

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict:
        """
        Filter, paginate, and return a ``UserPage`` dict.

        REQ-USR-03: default page=1, page_size=20; 422 if page_size>100 or page<1.
        REQ-USR-B03: filter by role (exact) and/or email (case-insensitive exact).
        """
        # Validate pagination params
        try:
            page = int(page)
        except (TypeError, ValueError):
            raise ValidationError("page", "page must be a positive integer")
        try:
            page_size = int(page_size)
        except (TypeError, ValueError):
            raise ValidationError("page_size", "page_size must be a positive integer")

        if page < 1:
            raise ValidationError("page", "page must be >= 1")
        if page_size < 1:
            raise ValidationError("page_size", "page_size must be >= 1")
        if page_size > 100:
            raise ValidationError("page_size", "page_size must not exceed 100")

        # Validate role filter value if provided
        if role is not None and role not in _VALID_ROLES:
            raise ValidationError(
                "role",
                f"role filter must be one of: {', '.join(sorted(_VALID_ROLES))}",
            )

        # Fetch filtered list from repository
        email_filter = email.lower() if email is not None else None
        users = self._repo.list(role=role, email=email_filter)

        # Paginate
        total = len(users)
        offset = (page - 1) * page_size
        items = users[offset: offset + page_size]

        return {
            "items": [u.to_dict() for u in items],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    # ------------------------------------------------------------------
    # REQ-USR-04
    # ------------------------------------------------------------------

    def replace_user(self, user_id: str, data: dict) -> User:
        """
        Replace all editable fields of an existing user (PUT semantics).

        REQ-USR-04: 404 if not found; 422 on invalid fields; 409 on duplicate email;
        preserves id and created_at; defaults role to 'attendee'.
        REQ-USR-B01: email uniqueness excluding self.
        REQ-USR-B02: email normalised to lowercase.
        """
        existing = self._repo.find_by_id(user_id)
        if existing is None:
            raise NotFound(f"User '{user_id}' not found")

        # Validate required fields
        first_name = data.get("first_name")
        if first_name is None:
            raise ValidationError("first_name", "first_name is required")
        _validate_first_name(first_name)

        last_name = data.get("last_name")
        if last_name is None:
            raise ValidationError("last_name", "last_name is required")
        _validate_last_name(last_name)

        email_raw = data.get("email")
        if email_raw is None:
            raise ValidationError("email", "email is required")
        email = _validate_email(email_raw)

        company = _validate_company(data.get("company"))

        role = data.get("role", "attendee")
        _validate_role(role)

        # REQ-USR-B01: uniqueness excluding self
        owner = self._repo.find_by_email(email)
        if owner is not None and owner.id != user_id:
            raise EmailAlreadyExists(f"email '{email}' is already registered")

        # Build updated user preserving id and created_at (REQ-USR-04 #6)
        updated = User(
            id=existing.id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            company=company,
            role=role,
            created_at=existing.created_at,
            updated_at=datetime.utcnow(),
        )
        self._repo.save(updated)
        return updated

    # ------------------------------------------------------------------
    # REQ-USR-05
    # ------------------------------------------------------------------

    def update_user(self, user_id: str, data: dict) -> User:
        """
        Update only the fields present in *data* (PATCH semantics).

        REQ-USR-05: 404 if not found; 422 if no recognised fields; 422 on invalid
        field value; 409 on duplicate email; id and created_at never change.
        REQ-USR-B01: email uniqueness excluding self.
        REQ-USR-B02: email normalised to lowercase.
        """
        existing = self._repo.find_by_id(user_id)
        if existing is None:
            raise NotFound(f"User '{user_id}' not found")

        # Require at least one recognised field (REQ-USR-05 #5)
        recognised = {k: v for k, v in data.items() if k in _KNOWN_FIELDS}
        if not recognised:
            raise ValidationError(
                "_body",
                "Request body must contain at least one recognised field: "
                + ", ".join(sorted(_KNOWN_FIELDS)),
            )

        # Start from current values
        first_name = existing.first_name
        last_name = existing.last_name
        email = existing.email
        company = existing.company
        role = existing.role

        if "first_name" in recognised:
            _validate_first_name(recognised["first_name"])
            first_name = recognised["first_name"]

        if "last_name" in recognised:
            _validate_last_name(recognised["last_name"])
            last_name = recognised["last_name"]

        if "email" in recognised:
            email = _validate_email(recognised["email"])
            # REQ-USR-B01: uniqueness excluding self
            owner = self._repo.find_by_email(email)
            if owner is not None and owner.id != user_id:
                raise EmailAlreadyExists(f"email '{email}' is already registered")

        if "company" in recognised:
            company = _validate_company(recognised["company"])

        if "role" in recognised:
            _validate_role(recognised["role"])
            role = recognised["role"]

        updated = User(
            id=existing.id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            company=company,
            role=role,
            created_at=existing.created_at,
            updated_at=datetime.utcnow(),
        )
        self._repo.save(updated)
        return updated

    # ------------------------------------------------------------------
    # REQ-USR-06
    # ------------------------------------------------------------------

    def delete_user(self, user_id: str) -> None:
        """
        Permanently remove the user with the given id.

        REQ-USR-06: 404 if not found; 204 (no content) signalled by returning None.
        """
        deleted = self._repo.delete(user_id)
        if not deleted:
            raise NotFound(f"User '{user_id}' not found")
