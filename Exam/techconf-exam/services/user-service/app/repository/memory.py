"""
In-memory storage backend for UserRepository.

All data is held in a plain Python dict and is lost when the process
restarts.  This backend is the default (STORAGE_BACKEND=memory) and is
used in all unit tests to avoid file-system side-effects.

No file I/O, no sqlite3 — only built-in Python structures.

REQ-USR-08: Persistenza multi-backend.
"""

from __future__ import annotations

from typing import Optional

from app.domain.models import User
from app.repository.base import UserRepository


class MemoryUserRepository(UserRepository):
    """UserRepository backed by an in-process dict[str, User]."""

    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    # ------------------------------------------------------------------
    # UserRepository interface
    # ------------------------------------------------------------------

    def save(self, user: User) -> None:
        """Insert or fully replace a User in the in-memory store."""
        self._store[user.id] = user

    def find_by_id(self, id: str) -> Optional[User]:
        """Return the User with the given id, or None."""
        return self._store.get(id)

    def find_by_email(self, email: str) -> Optional[User]:
        """
        Return the User whose stored email equals *email*, or None.

        Stored emails are already lowercase (REQ-USR-B02), so a plain
        equality check is sufficient.
        """
        for user in self._store.values():
            if user.email == email:
                return user
        return None

    def list(self, role: Optional[str], email: Optional[str]) -> list[User]:
        """
        Return users matching both optional filters (AND semantics).

        REQ-USR-B03: exact role match; case-insensitive email match
        (safe to do as lower() since stored emails are already lowercase).
        """
        results: list[User] = []
        for user in self._store.values():
            if role is not None and user.role != role:
                continue
            if email is not None and user.email != email.lower():
                continue
            results.append(user)
        return results

    def delete(self, id: str) -> bool:
        """Remove the user by id; return True if it existed, False otherwise."""
        if id in self._store:
            del self._store[id]
            return True
        return False
