"""
Domain model for user-service.

REQ-USR-01: User creation with server-generated id, timestamps, and role default.
REQ-USR-B02: Email stored and returned in lowercase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Represents a TechConf platform user."""

    id: str
    first_name: str
    last_name: str
    email: str
    company: Optional[str]
    role: str
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, data: dict) -> "User":
        """
        Create a new User from client-supplied data.

        REQ-USR-01: Generates UUID v4 id, sets created_at/updated_at to
        current UTC time, defaults role to 'attendee'.
        REQ-USR-B02: Normalises email to lowercase.
        """
        now = datetime.utcnow()
        return cls(
            id=str(uuid.uuid4()),
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"].lower(),   # REQ-USR-B02
            company=data.get("company"),
            role=data.get("role", "attendee"),
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serialise to a JSON-safe dict.

        Timestamps are formatted as ISO 8601 UTC strings ending in 'Z'
        (e.g. '2026-10-15T09:30:00Z').
        """
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "company": self.company,
            "role": self.role,
            "created_at": _to_iso_z(self.created_at),
            "updated_at": _to_iso_z(self.updated_at),
        }

    # ------------------------------------------------------------------
    # Deserialisation
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, d: dict) -> "User":
        """
        Reconstruct a User from a stored dict (e.g. from JSON or SQLite).

        Timestamps are parsed from ISO 8601 UTC strings back to datetime objects.
        """
        return cls(
            id=d["id"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            email=d["email"],
            company=d.get("company"),
            role=d.get("role", "attendee"),
            created_at=_from_iso_z(d["created_at"]),
            updated_at=_from_iso_z(d["updated_at"]),
        )


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _to_iso_z(dt: datetime) -> str:
    """Format a UTC datetime as an ISO 8601 string ending with 'Z'."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_iso_z(s: str) -> datetime:
    """Parse an ISO 8601 UTC string (with or without trailing 'Z') to datetime."""
    # Support both '2026-10-15T09:30:00Z' and '2026-10-15T09:30:00'
    if s.endswith("Z"):
        s = s[:-1]
    return datetime.fromisoformat(s)
