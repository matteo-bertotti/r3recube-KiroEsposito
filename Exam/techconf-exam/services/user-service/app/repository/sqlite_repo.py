"""
SQLite-backed UserRepository implementation.

REQ-USR-08: Persistenza multi-backend — sqlite variant.

Uses only the standard-library ``sqlite3`` module; no ORM or external
dependencies.  The database file is created (together with DATA_DIR)
on first use.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from app.domain.models import User
from app.repository.base import UserRepository

# Column order in CREATE TABLE / INSERT matches the positional mapping used
# in _row_to_user().
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    company     TEXT,
    role        TEXT NOT NULL DEFAULT 'attendee',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""


def _row_to_user(row: tuple) -> User:
    """Convert a SQLite row tuple to a User domain object."""
    return User.from_dict(
        {
            "id": row[0],
            "first_name": row[1],
            "last_name": row[2],
            "email": row[3],
            "company": row[4],
            "role": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
    )


class SqliteUserRepository(UserRepository):
    """
    UserRepository backed by a SQLite database file.

    Args:
        data_dir: Path to the directory where ``users.db`` will be stored.
                  The directory is created automatically if it does not exist.
    """

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._db_path = os.path.join(data_dir, "users.db")
        os.makedirs(data_dir, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open and return a new database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = None  # we handle row mapping ourselves
        return conn

    def _init_db(self) -> None:
        """Create the users table if it does not already exist."""
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()

    # ------------------------------------------------------------------
    # UserRepository interface
    # ------------------------------------------------------------------

    def save(self, user: User) -> None:
        """
        Persist a User using INSERT OR REPLACE.

        Replaces the existing row if ``user.id`` already exists; inserts
        a new row otherwise.  Timestamps are stored as ISO 8601 UTC strings.
        """
        d = user.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO users
                    (id, first_name, last_name, email, company, role,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["id"],
                    d["first_name"],
                    d["last_name"],
                    d["email"],
                    d["company"],
                    d["role"],
                    d["created_at"],
                    d["updated_at"],
                ),
            )
            conn.commit()

    def find_by_id(self, id: str) -> Optional[User]:
        """Return the User with the given id, or None if not found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT id, first_name, last_name, email, company, role, "
                "created_at, updated_at FROM users WHERE id = ?",
                (id,),
            )
            row = cursor.fetchone()
        return _row_to_user(row) if row is not None else None

    def find_by_email(self, email: str) -> Optional[User]:
        """
        Return the User whose stored email equals *email*, or None.

        *email* is compared with a case-sensitive equality check;
        all stored emails are already lowercase (REQ-USR-B02).
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT id, first_name, last_name, email, company, role, "
                "created_at, updated_at FROM users WHERE email = ?",
                (email,),
            )
            row = cursor.fetchone()
        return _row_to_user(row) if row is not None else None

    def list(self, role: Optional[str], email: Optional[str]) -> list[User]:
        """
        Return all users matching the given filters (AND-ed when both supplied).

        REQ-USR-B03: The WHERE clause is built dynamically from the
        provided (non-None) filters.
        """
        conditions: list[str] = []
        params: list[str] = []

        if role is not None:
            conditions.append("role = ?")
            params.append(role)
        if email is not None:
            conditions.append("email = ?")
            params.append(email.lower())

        sql = (
            "SELECT id, first_name, last_name, email, company, role, "
            "created_at, updated_at FROM users"
        )
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        return [_row_to_user(row) for row in rows]

    def delete(self, id: str) -> bool:
        """
        Remove the user with the given id.

        Returns:
            ``True``  if the user existed and was removed.
            ``False`` if no user with that id was found.
        """
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (id,))
            conn.commit()
        return cursor.rowcount > 0
