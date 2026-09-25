"""
JSON-file backend for UserRepository.

Persists all users as a JSON array inside a single file:
    {DATA_DIR}/users.json  →  {"users": [...]}

Every mutating operation reads the current file, applies the change,
and rewrites the whole file.  A missing file is treated as an empty
collection.  The data directory is created automatically on first write.

Only standard-library modules are used (json, os).

REQ-USR-08: Persistenza multi-backend — json backend.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from app.domain.models import User
from app.repository.base import UserRepository


class JsonUserRepository(UserRepository):
    """Stores users as a JSON file on disk."""

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._path = os.path.join(data_dir, "users.json")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self) -> list[User]:
        """Load all users from the JSON file; return [] if file is absent."""
        if not os.path.exists(self._path):
            return []
        with open(self._path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [User.from_dict(d) for d in data.get("users", [])]

    def _write_all(self, users: list[User]) -> None:
        """Persist the full list to disk, creating the directory if needed."""
        os.makedirs(self._data_dir, exist_ok=True)
        payload = {"users": [u.to_dict() for u in users]}
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # UserRepository interface
    # ------------------------------------------------------------------

    def save(self, user: User) -> None:
        """
        Insert or fully replace a user (matched by id).

        REQ-USR-08: same CRUD semantics across all backends.
        """
        users = self._read_all()
        # Replace existing entry, or append if new
        updated = [u for u in users if u.id != user.id]
        updated.append(user)
        self._write_all(updated)

    def find_by_id(self, id: str) -> Optional[User]:
        """Return the user with the given id, or None."""
        for user in self._read_all():
            if user.id == id:
                return user
        return None

    def find_by_email(self, email: str) -> Optional[User]:
        """
        Return the user whose stored email equals *email*, or None.

        *email* must already be lowercase; stored emails are always
        lowercase (REQ-USR-B02), so plain equality suffices.
        """
        for user in self._read_all():
            if user.email == email:
                return user
        return None

    def list(self, role: Optional[str], email: Optional[str]) -> list[User]:
        """
        Return users matching both filters (AND semantics).

        None values mean "no filter on that field".

        REQ-USR-B03: filter by role and/or email.
        """
        users = self._read_all()
        if role is not None:
            users = [u for u in users if u.role == role]
        if email is not None:
            users = [u for u in users if u.email == email.lower()]
        return users

    def delete(self, id: str) -> bool:
        """
        Remove the user with the given id.

        Returns True if found and removed, False if not found.
        """
        users = self._read_all()
        remaining = [u for u in users if u.id != id]
        if len(remaining) == len(users):
            return False  # nothing was removed
        self._write_all(remaining)
        return True
