"""
Unit tests — domain logic (UserService + MemoryUserRepository).

No Flask, no HTTP calls. All tests operate on UserService injected with a
fresh MemoryUserRepository so there are no file-system or network side-effects.

Test coverage map (task T-13):
  1.  valid creation — UUID, timestamps, role default
  2.  email lowercased                                   REQ-USR-B02
  3.  duplicate email any case → EmailAlreadyExists      REQ-USR-B01
  4.  missing required fields → ValidationError          REQ-USR-01
  5.  field length violations → ValidationError          REQ-USR-01
  6.  invalid email format → ValidationError             REQ-USR-01
  7.  invalid role → ValidationError                     REQ-USR-01
  8.  filter by role                                     REQ-USR-B03
  9.  filter by email                                    REQ-USR-B03
  10. pagination offset/slice                            REQ-USR-03
  11. page_size > 100 → ValidationError                  REQ-USR-03
  12. replace_user preserves id/created_at               REQ-USR-04
  13. replace_user without role defaults to "attendee"   REQ-USR-04
  14. update_user updates only present fields            REQ-USR-05
  15. update_user empty body → ValidationError           REQ-USR-05
  16. delete_user then second call → NotFound            REQ-USR-06
  17. get_user unknown id → NotFound                     REQ-USR-02
"""

from __future__ import annotations

import re
import time

import pytest

from app.domain.user_service import (
    EmailAlreadyExists,
    NotFound,
    UserService,
    ValidationError,
)
from app.repository.memory import MemoryUserRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID = {
    "first_name": "Alice",
    "last_name": "Rossi",
    "email": "alice@example.com",
    "role": "attendee",
}

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def make_service() -> UserService:
    """Return a fresh UserService backed by an empty MemoryUserRepository."""
    return UserService(MemoryUserRepository())


# ---------------------------------------------------------------------------
# 1. Valid creation — UUID, timestamps, role default
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-01")
def test_create_user_valid_returns_user_with_uuid_and_timestamps():
    svc = make_service()
    user = svc.create_user(VALID)

    assert _UUID4_RE.match(user.id), "id must be a valid UUID v4"
    d = user.to_dict()
    assert _ISO_UTC_RE.match(d["created_at"]), "created_at must be ISO 8601 UTC with Z"
    assert _ISO_UTC_RE.match(d["updated_at"]), "updated_at must be ISO 8601 UTC with Z"
    assert d["created_at"] == d["updated_at"], "created_at and updated_at equal at creation"


@pytest.mark.req("REQ-USR-01")
def test_create_user_without_role_defaults_to_attendee():
    svc = make_service()
    data = {k: v for k, v in VALID.items() if k != "role"}
    user = svc.create_user(data)
    assert user.role == "attendee"


# ---------------------------------------------------------------------------
# 2. Email lowercased (REQ-USR-B02)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-B02")
def test_create_user_email_stored_lowercase():
    svc = make_service()
    user = svc.create_user({**VALID, "email": "Alice@EXAMPLE.COM"})
    assert user.email == "alice@example.com"


@pytest.mark.req("REQ-USR-B02")
def test_replace_user_email_stored_lowercase():
    svc = make_service()
    user = svc.create_user(VALID)
    updated = svc.replace_user(user.id, {**VALID, "email": "ALICE@EXAMPLE.COM"})
    assert updated.email == "alice@example.com"


@pytest.mark.req("REQ-USR-B02")
def test_update_user_email_stored_lowercase():
    svc = make_service()
    user = svc.create_user(VALID)
    updated = svc.update_user(user.id, {"email": "Alice@Example.COM"})
    assert updated.email == "alice@example.com"


# ---------------------------------------------------------------------------
# 3. Duplicate email (any case) → EmailAlreadyExists (REQ-USR-B01)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-B01")
def test_create_user_duplicate_email_same_case_raises():
    svc = make_service()
    svc.create_user(VALID)
    with pytest.raises(EmailAlreadyExists):
        svc.create_user({**VALID, "first_name": "Bob"})


@pytest.mark.req("REQ-USR-B01")
def test_create_user_duplicate_email_different_case_raises():
    svc = make_service()
    svc.create_user(VALID)
    with pytest.raises(EmailAlreadyExists):
        svc.create_user({**VALID, "email": "ALICE@EXAMPLE.COM", "first_name": "Bob"})


@pytest.mark.req("REQ-USR-B01")
def test_replace_user_duplicate_email_different_user_raises():
    svc = make_service()
    alice = svc.create_user(VALID)
    bob = svc.create_user(
        {"first_name": "Bob", "last_name": "Bianchi", "email": "bob@example.com"}
    )
    # Try to give Bob the same email as Alice
    with pytest.raises(EmailAlreadyExists):
        svc.replace_user(bob.id, {**VALID, "email": "ALICE@EXAMPLE.COM"})


@pytest.mark.req("REQ-USR-B01")
def test_update_user_duplicate_email_different_user_raises():
    svc = make_service()
    svc.create_user(VALID)
    bob = svc.create_user(
        {"first_name": "Bob", "last_name": "Bianchi", "email": "bob@example.com"}
    )
    with pytest.raises(EmailAlreadyExists):
        svc.update_user(bob.id, {"email": "Alice@Example.com"})


@pytest.mark.req("REQ-USR-B01")
def test_replace_user_own_email_same_case_variant_no_conflict():
    """A user updating to a case-variant of their own email must NOT raise (REQ-USR-B01 #4)."""
    svc = make_service()
    user = svc.create_user(VALID)
    # Should not raise — it's the same logical email
    updated = svc.replace_user(user.id, {**VALID, "email": "ALICE@EXAMPLE.COM"})
    assert updated.email == "alice@example.com"


@pytest.mark.req("REQ-USR-B01")
def test_update_user_own_email_same_case_variant_no_conflict():
    svc = make_service()
    user = svc.create_user(VALID)
    updated = svc.update_user(user.id, {"email": "Alice@EXAMPLE.COM"})
    assert updated.email == "alice@example.com"


# ---------------------------------------------------------------------------
# 4. Missing required fields → ValidationError (REQ-USR-01)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-01")
@pytest.mark.parametrize("missing_field", ["first_name", "last_name", "email"])
def test_create_user_missing_required_field_raises(missing_field):
    svc = make_service()
    data = {k: v for k, v in VALID.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user(data)
    assert exc_info.value.field == missing_field


@pytest.mark.req("REQ-USR-04")
@pytest.mark.parametrize("missing_field", ["first_name", "last_name", "email"])
def test_replace_user_missing_required_field_raises(missing_field):
    svc = make_service()
    user = svc.create_user(VALID)
    data = {k: v for k, v in VALID.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        svc.replace_user(user.id, data)
    assert exc_info.value.field == missing_field


# ---------------------------------------------------------------------------
# 5. Field length violations → ValidationError (REQ-USR-01)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-01")
def test_create_user_first_name_too_long_raises():
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user({**VALID, "first_name": "A" * 51})
    assert exc_info.value.field == "first_name"


@pytest.mark.req("REQ-USR-01")
def test_create_user_last_name_too_long_raises():
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user({**VALID, "last_name": "B" * 51})
    assert exc_info.value.field == "last_name"


@pytest.mark.req("REQ-USR-01")
def test_create_user_company_too_long_raises():
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user({**VALID, "company": "C" * 101})
    assert exc_info.value.field == "company"


@pytest.mark.req("REQ-USR-01")
def test_create_user_first_name_exactly_50_chars_succeeds():
    svc = make_service()
    user = svc.create_user({**VALID, "first_name": "A" * 50})
    assert len(user.first_name) == 50


@pytest.mark.req("REQ-USR-01")
def test_create_user_company_exactly_100_chars_succeeds():
    svc = make_service()
    user = svc.create_user({**VALID, "company": "C" * 100})
    assert len(user.company) == 100


@pytest.mark.req("REQ-USR-05")
def test_update_user_first_name_too_long_raises():
    svc = make_service()
    user = svc.create_user(VALID)
    with pytest.raises(ValidationError) as exc_info:
        svc.update_user(user.id, {"first_name": "A" * 51})
    assert exc_info.value.field == "first_name"


# ---------------------------------------------------------------------------
# 6. Invalid email format → ValidationError (REQ-USR-01)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-01")
@pytest.mark.parametrize(
    "bad_email",
    [
        "not-an-email",
        "missing@tld",
        "@nodomain.com",
        "spaces in@email.com",
        "",
    ],
)
def test_create_user_invalid_email_format_raises(bad_email):
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user({**VALID, "email": bad_email})
    assert exc_info.value.field == "email"


# ---------------------------------------------------------------------------
# 7. Invalid role → ValidationError (REQ-USR-01)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-01")
@pytest.mark.parametrize("bad_role", ["admin", "guest", "ATTENDEE", ""])
def test_create_user_invalid_role_raises(bad_role):
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.create_user({**VALID, "email": "new@example.com", "role": bad_role})
    assert exc_info.value.field == "role"


# ---------------------------------------------------------------------------
# 8. Filter by role (REQ-USR-B03)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-B03")
def test_list_users_filter_by_role_returns_matching_only():
    svc = make_service()
    svc.create_user({**VALID, "role": "attendee"})
    svc.create_user(
        {"first_name": "Bob", "last_name": "Bianchi", "email": "bob@example.com", "role": "speaker"}
    )
    svc.create_user(
        {"first_name": "Carol", "last_name": "Verdi", "email": "carol@example.com", "role": "organizer"}
    )

    result = svc.list_users(role="speaker")
    assert result["total"] == 1
    assert all(u["role"] == "speaker" for u in result["items"])


@pytest.mark.req("REQ-USR-B03")
def test_list_users_filter_by_role_no_match_returns_empty():
    svc = make_service()
    svc.create_user(VALID)  # attendee
    result = svc.list_users(role="organizer")
    assert result["total"] == 0
    assert result["items"] == []


# ---------------------------------------------------------------------------
# 9. Filter by email (REQ-USR-B03)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-B03")
def test_list_users_filter_by_email_case_insensitive():
    svc = make_service()
    svc.create_user(VALID)
    svc.create_user(
        {"first_name": "Bob", "last_name": "Bianchi", "email": "bob@example.com"}
    )
    # Filter with mixed-case variant of alice's email
    result = svc.list_users(email="ALICE@EXAMPLE.COM")
    assert result["total"] == 1
    assert result["items"][0]["email"] == "alice@example.com"


@pytest.mark.req("REQ-USR-B03")
def test_list_users_filter_by_role_and_email_combined():
    svc = make_service()
    svc.create_user(VALID)  # alice, attendee
    svc.create_user(
        {"first_name": "Dave", "last_name": "Neri", "email": "dave@example.com", "role": "attendee"}
    )
    # Only alice matches both email and attendee role
    result = svc.list_users(role="attendee", email="alice@example.com")
    assert result["total"] == 1
    assert result["items"][0]["email"] == "alice@example.com"


# ---------------------------------------------------------------------------
# 10. Pagination offset/slice (REQ-USR-03)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-03")
def test_list_users_pagination_slice():
    svc = make_service()
    emails = [f"user{i}@example.com" for i in range(5)]
    for i, email in enumerate(emails):
        svc.create_user({"first_name": f"User{i}", "last_name": "Test", "email": email})

    # First page: 2 items
    page1 = svc.list_users(page=1, page_size=2)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert page1["page"] == 1
    assert page1["page_size"] == 2

    # Second page: 2 items
    page2 = svc.list_users(page=2, page_size=2)
    assert len(page2["items"]) == 2

    # Third page: 1 item (remainder)
    page3 = svc.list_users(page=3, page_size=2)
    assert len(page3["items"]) == 1

    # Pages don't overlap
    ids_p1 = {u["id"] for u in page1["items"]}
    ids_p2 = {u["id"] for u in page2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


@pytest.mark.req("REQ-USR-03")
def test_list_users_default_pagination():
    svc = make_service()
    result = svc.list_users()
    assert result["page"] == 1
    assert result["page_size"] == 20


@pytest.mark.req("REQ-USR-03")
def test_list_users_page_less_than_1_raises():
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.list_users(page=0)
    assert exc_info.value.field == "page"


# ---------------------------------------------------------------------------
# 11. page_size > 100 → ValidationError (REQ-USR-03)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-03")
def test_list_users_page_size_exceeds_100_raises():
    svc = make_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.list_users(page_size=101)
    assert exc_info.value.field == "page_size"


@pytest.mark.req("REQ-USR-03")
def test_list_users_page_size_100_is_valid():
    svc = make_service()
    result = svc.list_users(page_size=100)
    assert result["page_size"] == 100


# ---------------------------------------------------------------------------
# 12. replace_user preserves id and created_at (REQ-USR-04)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-04")
def test_replace_user_preserves_id_and_created_at():
    svc = make_service()
    user = svc.create_user(VALID)
    original_id = user.id
    original_created_at = user.to_dict()["created_at"]

    updated = svc.replace_user(
        user.id,
        {"first_name": "Alicia", "last_name": "Rossi", "email": "alice@example.com"},
    )
    assert updated.id == original_id
    assert updated.to_dict()["created_at"] == original_created_at


@pytest.mark.req("REQ-USR-04")
def test_replace_user_updates_updated_at():
    svc = make_service()
    user = svc.create_user(VALID)
    original_updated_at = user.updated_at

    # Sleep briefly so clock ticks
    time.sleep(0.01)
    updated = svc.replace_user(user.id, {**VALID, "first_name": "Alicia"})
    assert updated.updated_at >= original_updated_at


@pytest.mark.req("REQ-USR-04")
def test_replace_user_unknown_id_raises():
    svc = make_service()
    with pytest.raises(NotFound):
        svc.replace_user("00000000-0000-4000-8000-000000000000", VALID)


# ---------------------------------------------------------------------------
# 13. replace_user without role defaults to "attendee" (REQ-USR-04)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-04")
def test_replace_user_without_role_defaults_to_attendee():
    svc = make_service()
    user = svc.create_user({**VALID, "role": "speaker"})
    assert user.role == "speaker"

    # PUT without role → should reset to attendee
    updated = svc.replace_user(
        user.id,
        {"first_name": "Alice", "last_name": "Rossi", "email": "alice@example.com"},
    )
    assert updated.role == "attendee"


# ---------------------------------------------------------------------------
# 14. update_user updates only present fields (REQ-USR-05)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-05")
def test_update_user_updates_only_present_fields():
    svc = make_service()
    user = svc.create_user({**VALID, "company": "Acme", "role": "speaker"})

    # Patch only first_name
    updated = svc.update_user(user.id, {"first_name": "Alicia"})
    assert updated.first_name == "Alicia"
    assert updated.last_name == user.last_name       # unchanged
    assert updated.email == user.email               # unchanged
    assert updated.company == user.company           # unchanged
    assert updated.role == user.role                 # unchanged


@pytest.mark.req("REQ-USR-05")
def test_update_user_preserves_id_and_created_at():
    svc = make_service()
    user = svc.create_user(VALID)
    updated = svc.update_user(user.id, {"first_name": "Alicia"})
    assert updated.id == user.id
    assert updated.created_at == user.created_at


@pytest.mark.req("REQ-USR-05")
def test_update_user_unknown_id_raises():
    svc = make_service()
    with pytest.raises(NotFound):
        svc.update_user("00000000-0000-4000-8000-000000000000", {"first_name": "X"})


# ---------------------------------------------------------------------------
# 15. update_user empty body → ValidationError (REQ-USR-05)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-05")
def test_update_user_empty_body_raises():
    svc = make_service()
    user = svc.create_user(VALID)
    with pytest.raises(ValidationError):
        svc.update_user(user.id, {})


@pytest.mark.req("REQ-USR-05")
def test_update_user_only_unknown_fields_raises():
    svc = make_service()
    user = svc.create_user(VALID)
    with pytest.raises(ValidationError):
        svc.update_user(user.id, {"unknown_field": "value", "another": 123})


# ---------------------------------------------------------------------------
# 16. delete_user then second call → NotFound (REQ-USR-06)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-06")
def test_delete_user_success_then_second_delete_raises():
    svc = make_service()
    user = svc.create_user(VALID)

    # First delete — should succeed (no exception)
    svc.delete_user(user.id)

    # Second delete — user is gone → NotFound
    with pytest.raises(NotFound):
        svc.delete_user(user.id)


@pytest.mark.req("REQ-USR-06")
def test_delete_user_then_get_raises_not_found():
    svc = make_service()
    user = svc.create_user(VALID)
    svc.delete_user(user.id)

    with pytest.raises(NotFound):
        svc.get_user(user.id)


@pytest.mark.req("REQ-USR-06")
def test_delete_user_unknown_id_raises():
    svc = make_service()
    with pytest.raises(NotFound):
        svc.delete_user("00000000-0000-4000-8000-000000000000")


# ---------------------------------------------------------------------------
# 17. get_user unknown id → NotFound (REQ-USR-02)
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-02")
def test_get_user_unknown_id_raises():
    svc = make_service()
    with pytest.raises(NotFound):
        svc.get_user("00000000-0000-4000-8000-000000000000")


@pytest.mark.req("REQ-USR-02")
def test_get_user_returns_correct_user():
    svc = make_service()
    created = svc.create_user(VALID)
    fetched = svc.get_user(created.id)
    assert fetched.id == created.id
    assert fetched.email == created.email
