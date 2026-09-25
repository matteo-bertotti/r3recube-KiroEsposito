"""
Abstract base class for UserRepository.

Defines the interface that all storage backends must implement.
Domain and API layers depend only on this interface — never on a
concrete implementation — so switching backends (memory / json / sqlite)
requires no changes to business logic.

REQ-USR-08: Persistenza multi-backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.models import User


class UserRepository(ABC):
    """Storage interface for User entities."""

    @abstractmethod
    def save(self, user: User) -> None:
        """
        Persist a User (insert or full replacement).

        If a user with the same id already exists it is replaced in full;
        otherwise it is inserted.  The caller is responsible for
        ensuring email uniqueness before calling save().
        """

    @abstractmethod
    def find_by_id(self, id: str) -> Optional[User]:
        """Return the User with the given id, or None if not found."""

    @abstractmethod
    def find_by_email(self, email: str) -> Optional[User]:
        """
        Return the User whose stored email equals *email*, or None.

        *email* must already be lowercase; stored emails are always
        lowercase (REQ-USR-B02), so a plain equality check suffices.
        """

    @abstractmethod
    def list(self, role: Optional[str], email: Optional[str]) -> list[User]:
        """
        Return all users matching the given filters.

        Both filters are optional; when both are supplied they are AND-ed.

        Args:
            role:  Exact match against the user's ``role`` field.
                   ``None`` means no filter.
            email: Exact match (case-insensitive) against the stored
                   lowercase email.  ``None`` means no filter.

        Returns:
            A list of matching User objects (may be empty).
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """
        Remove the user with the given id.

        Returns:
            ``True``  if the user existed and was removed.
            ``False`` if no user with that id was found.
        """
