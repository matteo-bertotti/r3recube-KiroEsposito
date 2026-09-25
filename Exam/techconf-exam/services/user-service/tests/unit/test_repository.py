"""
Unit tests — repository backends.

Parametrized over all three backends (memory, json, sqlite) to verify
that every implementation satisfies the UserRepository contract.

REQ-USR-08: The same CRUD behaviour is available regardless of the
            active storage backend.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.domain.models import User
from app.repository.json_repo import JsonUserRepository
from app.repository.memory import MemoryUserRepository
from app.repository.sqlite_repo import SqliteUserRepository


# ---------------------------------------------------------------------------
# Shared fixture — yields a fresh repository for each backend
# ---------------------------------------------------------------------------

@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    """Return a clean repository instance for each backend variant."""
    if request.param == "memory":
        return MemoryUserRepository()
    elif request.param == "json":
        return JsonUserRepository(str(tmp_path / "data"))
    else:
        return SqliteUserRepository(str(tmp_path / "data"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "test@example.com", role: str = "attendee") -> User:
    return User.create(
        {"first_name": "Test", "last_name": "User", "email": email, "role": role}
    )


# ---------------------------------------------------------------------------
# Tests — parametrized over all backends (REQ-USR-08)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-08")
def test_save_and_find_by_id_round_trip(repo):
    """save() followed by find_by_id() returns the same user."""
    user = _make_user()
    repo.save(user)

    found = repo.find_by_id(user.id)

    assert found is not None
    assert found.id == user.id
    assert found.first_name == user.first_name
    assert found.last_name == user.last_name
    assert found.email == user.email
    assert found.role == user.role


@pytest.mark.req("REQ-USR-08")
def test_find_by_id_absent_returns_none(repo):
    """find_by_id() returns None for an unknown id."""
    result = repo.find_by_id("nonexistent-id")
    assert result is None


@pytest.mark.req("REQ-USR-08")
def test_find_by_email_returns_matching_user(repo):
    """find_by_email() returns the user with the given (lowercase) email."""
    user = _make_user(email="test@example.com")
    repo.save(user)

    found = repo.find_by_email("test@example.com")

    assert found is not None
    assert found.id == user.id


@pytest.mark.req("REQ-USR-08")
def test_find_by_email_absent_returns_none(repo):
    """find_by_email() returns None when no user has that email."""
    result = repo.find_by_email("nobody@example.com")
    assert result is None


@pytest.mark.req("REQ-USR-08")
def test_list_no_filters(repo):
    """list(None, None) returns all saved users."""
    user = _make_user()
    repo.save(user)

    results = repo.list(None, None)

    assert len(results) == 1
    assert results[0].id == user.id


@pytest.mark.req("REQ-USR-08")
def test_list_role_filter(repo):
    """list(role, None) returns only users with that role."""
    attendee = _make_user(email="attendee@example.com", role="attendee")
    speaker = _make_user(email="speaker@example.com", role="speaker")
    repo.save(attendee)
    repo.save(speaker)

    results = repo.list("speaker", None)

    assert len(results) == 1
    assert results[0].id == speaker.id
    assert results[0].role == "speaker"


@pytest.mark.req("REQ-USR-08")
def test_list_email_filter(repo):
    """list(None, email) returns only the user with that email."""
    user1 = _make_user(email="test@example.com")
    user2 = _make_user(email="other@example.com")
    repo.save(user1)
    repo.save(user2)

    results = repo.list(None, "test@example.com")

    assert len(results) == 1
    assert results[0].id == user1.id


@pytest.mark.req("REQ-USR-08")
def test_list_both_filters(repo):
    """list(role, email) applies both filters with AND semantics."""
    match = _make_user(email="speaker@example.com", role="speaker")
    no_match_role = _make_user(email="attendee@example.com", role="attendee")
    no_match_email = _make_user(email="other@example.com", role="speaker")
    repo.save(match)
    repo.save(no_match_role)
    repo.save(no_match_email)

    results = repo.list("speaker", "speaker@example.com")

    assert len(results) == 1
    assert results[0].id == match.id


@pytest.mark.req("REQ-USR-08")
def test_list_returns_empty_when_no_match(repo):
    """list() returns [] when no user satisfies the filter."""
    user = _make_user(role="attendee")
    repo.save(user)

    results = repo.list("organizer", None)

    assert results == []


@pytest.mark.req("REQ-USR-08")
def test_delete_existing_user_returns_true(repo):
    """delete() returns True when the user existed and was removed."""
    user = _make_user()
    repo.save(user)

    result = repo.delete(user.id)

    assert result is True
    assert repo.find_by_id(user.id) is None


@pytest.mark.req("REQ-USR-08")
def test_delete_absent_user_returns_false(repo):
    """delete() returns False when no user with that id exists."""
    result = repo.delete("nonexistent-id")
    assert result is False


@pytest.mark.req("REQ-USR-08")
def test_save_replaces_existing_user(repo):
    """save() with an existing id replaces the stored record in full."""
    user = _make_user(email="original@example.com")
    repo.save(user)

    # Mutate and re-save — simulate an update
    from datetime import datetime
    updated = User(
        id=user.id,
        first_name="Updated",
        last_name=user.last_name,
        email="updated@example.com",
        company=None,
        role=user.role,
        created_at=user.created_at,
        updated_at=datetime.utcnow(),
    )
    repo.save(updated)

    found = repo.find_by_id(user.id)
    assert found is not None
    assert found.first_name == "Updated"
    assert found.email == "updated@example.com"


# ---------------------------------------------------------------------------
# SQLite-specific test — duplicate email raises IntegrityError
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-08")
def test_sqlite_duplicate_email_raises_integrity_error(tmp_path):
    """
    The SQLite schema enforces a UNIQUE constraint on email at the DB level.

    ``save()`` uses ``INSERT OR REPLACE`` which resolves UNIQUE conflicts by
    replacing the conflicting row — that is intentional behaviour allowing
    full-record updates.  The DB-level constraint is verified here by
    executing a plain ``INSERT`` (the operation that fires ``IntegrityError``
    on a conflict) directly against the underlying database file, proving the
    constraint exists independently of the ``save()`` helper.
    """
    import os

    data_dir = str(tmp_path / "data")
    repo = SqliteUserRepository(data_dir)

    user1 = User.create(
        {"first_name": "A", "last_name": "B", "email": "dup@example.com", "role": "attendee"}
    )
    repo.save(user1)

    db_path = os.path.join(data_dir, "users.db")
    import uuid
    from datetime import datetime

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_id = str(uuid.uuid4())

    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users "
                "(id, first_name, last_name, email, company, role, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, "C", "D", "dup@example.com", None, "speaker", now, now),
            )
            conn.commit()
    finally:
        conn.close()
