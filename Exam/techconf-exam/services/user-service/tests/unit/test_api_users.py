"""
Unit tests for user-service API routes — Flask test client.

All tests use an in-memory backend (STORAGE_BACKEND=memory set in conftest.py).
Contract validation via contracts/validator.py (repo root added to sys.path in conftest).

Requirements covered:
  REQ-USR-01, REQ-USR-B01, REQ-USR-B02  — POST /api/v1/users
  REQ-USR-02                             — GET  /api/v1/users/{id}
  REQ-USR-03, REQ-USR-B03               — GET  /api/v1/users
  REQ-USR-04                             — PUT  /api/v1/users/{id}
  REQ-USR-05                             — PATCH /api/v1/users/{id}
  REQ-USR-06                             — DELETE /api/v1/users/{id}
  REQ-USR-07                             — GET /health
  REQ-USR-10                             — standard error envelope
"""

import pytest

from app.__main__ import create_app
from contracts.validator import assert_matches_contract


# ---------------------------------------------------------------------------
# Thin adapter: Flask test client responses don't have .json(), only .get_json()
# ---------------------------------------------------------------------------

def adapt(resp):
    """Build a dict adapter from a Flask test-client response.

    The validator's _extract() function accepts a plain dict with
    ``status_code``, ``headers``, and ``json`` keys directly.
    This avoids all streaming/context issues with Flask test responses.
    """
    import json as _json
    raw = resp.data
    body = None
    if raw:
        try:
            body = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            body = None
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": body,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# Helper: create a valid user and return the parsed JSON body
def _create_user(client, **overrides):
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "role": "attendee",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/users", json=payload)
    return resp


# ---------------------------------------------------------------------------
# REQ-USR-07 — Health check
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-07")
def test_health_ok(client):
    """GET /health returns 200 {"status": "ok", "service": "user-service"}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"status": "ok", "service": "user-service"}
    assert_matches_contract("user-service", "GET", "/health", adapt(resp))


# ---------------------------------------------------------------------------
# REQ-USR-01 — POST /api/v1/users
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-01")
def test_post_user_valid_201(client):
    """POST with valid body returns 201, Location header, and a User conforming to contract."""
    resp = _create_user(client)
    assert resp.status_code == 201
    # Location header must point to the created resource
    assert "Location" in resp.headers
    body = resp.get_json()
    assert resp.headers["Location"] == f"/api/v1/users/{body['id']}"
    # id, timestamps, and role are server-generated
    assert "id" in body
    assert body["email"] == "alice@example.com"
    assert body["role"] == "attendee"
    assert "created_at" in body
    assert "updated_at" in body
    assert_matches_contract("user-service", "POST", "/api/v1/users", adapt(resp))


@pytest.mark.req("REQ-USR-B02")
def test_post_user_email_lowercased(client):
    """Email is stored and returned in lowercase regardless of input case (REQ-USR-B02)."""
    resp = _create_user(client, email="UPPER@EXAMPLE.COM")
    assert resp.status_code == 201
    assert resp.get_json()["email"] == "upper@example.com"


@pytest.mark.req("REQ-USR-01")
def test_post_user_role_default_attendee(client):
    """POST without role defaults to attendee."""
    payload = {"first_name": "Bob", "last_name": "Jones", "email": "bob@example.com"}
    resp = client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201
    assert resp.get_json()["role"] == "attendee"


@pytest.mark.req("REQ-USR-10")
def test_post_user_bad_json_400(client):
    """POST with malformed JSON returns 400 MALFORMED_JSON (REQ-USR-10)."""
    resp = client.post(
        "/api/v1/users",
        data="not json at all",
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == "MALFORMED_JSON"
    assert_matches_contract("user-service", "POST", "/api/v1/users", adapt(resp))


@pytest.mark.req("REQ-USR-01")
def test_post_user_missing_first_name_422(client):
    """POST without first_name returns 422 VALIDATION_ERROR."""
    resp = client.post("/api/v1/users", json={"last_name": "X", "email": "x@x.com"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-01")
def test_post_user_missing_last_name_422(client):
    """POST without last_name returns 422 VALIDATION_ERROR."""
    resp = client.post("/api/v1/users", json={"first_name": "X", "email": "x@x.com"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-01")
def test_post_user_missing_email_422(client):
    """POST without email returns 422 VALIDATION_ERROR."""
    resp = client.post("/api/v1/users", json={"first_name": "X", "last_name": "Y"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-01")
def test_post_user_invalid_email_format_422(client):
    """POST with an invalid email format returns 422 VALIDATION_ERROR."""
    resp = client.post(
        "/api/v1/users",
        json={"first_name": "X", "last_name": "Y", "email": "not-an-email"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-01")
def test_post_user_first_name_too_long_422(client):
    """POST with first_name exceeding 50 chars returns 422 VALIDATION_ERROR."""
    resp = client.post(
        "/api/v1/users",
        json={"first_name": "A" * 51, "last_name": "Y", "email": "x@x.com"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-01")
def test_post_user_invalid_role_422(client):
    """POST with an invalid role value returns 422 VALIDATION_ERROR."""
    resp = client.post(
        "/api/v1/users",
        json={"first_name": "X", "last_name": "Y", "email": "x@x.com", "role": "admin"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-B01")
def test_post_user_duplicate_email_409(client):
    """POST with a duplicate email (case-insensitive) returns 409 EMAIL_ALREADY_EXISTS (REQ-USR-B01)."""
    _create_user(client, email="dup@example.com")
    # Same email, different case
    resp = client.post(
        "/api/v1/users",
        json={"first_name": "Bob", "last_name": "B", "email": "DUP@EXAMPLE.COM"},
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"]["code"] == "EMAIL_ALREADY_EXISTS"
    assert_matches_contract("user-service", "POST", "/api/v1/users", adapt(resp))


# ---------------------------------------------------------------------------
# REQ-USR-03, REQ-USR-B03 — GET /api/v1/users (list)
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_client(client):
    """Client with three users seeded for list/filter tests."""
    _create_user(client, first_name="Alice", last_name="A", email="alice@example.com", role="attendee")
    _create_user(client, first_name="Bob", last_name="B", email="bob@example.com", role="speaker")
    _create_user(client, first_name="Carol", last_name="C", email="carol@example.com", role="organizer")
    return client


@pytest.mark.req("REQ-USR-03")
def test_get_list_default_pagination(seeded_client):
    """GET /api/v1/users returns 200 UserPage with defaults page=1, page_size=20."""
    resp = seeded_client.get("/api/v1/users")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert_matches_contract("user-service", "GET", "/api/v1/users", adapt(resp))


@pytest.mark.req("REQ-USR-B03")
def test_get_list_role_filter(seeded_client):
    """GET /api/v1/users?role=speaker returns only speakers (REQ-USR-B03)."""
    resp = seeded_client.get("/api/v1/users?role=speaker")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["role"] == "speaker"


@pytest.mark.req("REQ-USR-B03")
def test_get_list_email_filter(seeded_client):
    """GET /api/v1/users?email=... performs case-insensitive exact match (REQ-USR-B03)."""
    resp = seeded_client.get("/api/v1/users?email=BOB@EXAMPLE.COM")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "bob@example.com"


@pytest.mark.req("REQ-USR-B03")
def test_get_list_combined_filters(seeded_client):
    """GET with both role and email filters applied together (REQ-USR-B03)."""
    resp = seeded_client.get("/api/v1/users?role=attendee&email=alice@example.com")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "alice@example.com"


@pytest.mark.req("REQ-USR-03")
def test_get_list_invalid_role_filter_422(seeded_client):
    """GET /api/v1/users with invalid role filter returns 422 VALIDATION_ERROR."""
    resp = seeded_client.get("/api/v1/users?role=unknown")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-03")
def test_get_list_page_size_exceeds_100_422(seeded_client):
    """GET /api/v1/users?page_size=200 returns 422 VALIDATION_ERROR."""
    resp = seeded_client.get("/api/v1/users?page_size=200")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-03")
def test_get_list_page_less_than_1_422(client):
    """GET /api/v1/users?page=0 returns 422 VALIDATION_ERROR."""
    resp = client.get("/api/v1/users?page=0")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-03")
def test_get_list_no_match_returns_empty(client):
    """GET with filters that match nothing returns 200 with empty items and total=0."""
    resp = client.get("/api/v1/users?email=nobody@nowhere.com")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.req("REQ-USR-03")
def test_get_list_pagination_slice(client):
    """Pagination correctly slices results."""
    # Create 3 users
    for i in range(3):
        _create_user(client, email=f"user{i}@example.com")
    # Fetch page 2 with page_size=2 — should return 1 item
    resp = client.get("/api/v1/users?page=2&page_size=2")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["total"] == 3
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# REQ-USR-02 — GET /api/v1/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-02")
def test_get_user_by_id_200(client):
    """GET /api/v1/users/{id} returns 200 with the User (contract-validated)."""
    created = _create_user(client).get_json()
    resp = client.get(f"/api/v1/users/{created['id']}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == created["id"]
    assert_matches_contract(
        "user-service", "GET", f"/api/v1/users/{created['id']}", adapt(resp)
    )


@pytest.mark.req("REQ-USR-02")
def test_get_user_unknown_id_404(client):
    """GET /api/v1/users/{id} with non-existent id returns 404 NOT_FOUND."""
    resp = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
    assert_matches_contract(
        "user-service", "GET",
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        adapt(resp),
    )


# ---------------------------------------------------------------------------
# REQ-USR-04 — PUT /api/v1/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-04")
def test_put_user_valid_200(client):
    """PUT with valid body returns 200, updates fields, updates updated_at, contract-valid."""
    import time
    created = _create_user(client).get_json()
    time.sleep(0.01)  # ensure updated_at > created_at
    replace_payload = {
        "first_name": "Alicia",
        "last_name": "Updated",
        "email": "alicia@example.com",
        "role": "speaker",
    }
    resp = client.put(f"/api/v1/users/{created['id']}", json=replace_payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["first_name"] == "Alicia"
    assert body["email"] == "alicia@example.com"
    assert body["role"] == "speaker"
    # id and created_at must be preserved (REQ-USR-04 #6)
    assert body["id"] == created["id"]
    assert body["created_at"] == created["created_at"]
    # updated_at must have been updated
    assert body["updated_at"] >= created["updated_at"]
    assert_matches_contract(
        "user-service", "PUT", f"/api/v1/users/{created['id']}", adapt(resp)
    )


@pytest.mark.req("REQ-USR-04")
def test_put_user_role_defaults_to_attendee(client):
    """PUT without role in body defaults role to attendee (REQ-USR-04 #5)."""
    created = _create_user(client, role="speaker").get_json()
    resp = client.put(
        f"/api/v1/users/{created['id']}",
        json={"first_name": "A", "last_name": "B", "email": "a@b.com"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "attendee"


@pytest.mark.req("REQ-USR-04")
def test_put_user_unknown_404(client):
    """PUT to a non-existent id returns 404 NOT_FOUND."""
    resp = client.put(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        json={"first_name": "X", "last_name": "Y", "email": "x@y.com"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.req("REQ-USR-10")
def test_put_user_bad_json_400(client):
    """PUT with malformed JSON body returns 400 MALFORMED_JSON."""
    created = _create_user(client).get_json()
    resp = client.put(
        f"/api/v1/users/{created['id']}",
        data="bad json",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


@pytest.mark.req("REQ-USR-B01")
def test_put_user_duplicate_email_409(client):
    """PUT with email belonging to another user returns 409 EMAIL_ALREADY_EXISTS."""
    u1 = _create_user(client, email="u1@example.com").get_json()
    _create_user(client, email="u2@example.com")
    resp = client.put(
        f"/api/v1/users/{u1['id']}",
        json={"first_name": "X", "last_name": "Y", "email": "u2@example.com"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.req("REQ-USR-04")
def test_put_user_missing_required_field_422(client):
    """PUT missing a required field returns 422 VALIDATION_ERROR."""
    created = _create_user(client).get_json()
    resp = client.put(
        f"/api/v1/users/{created['id']}",
        json={"first_name": "X", "last_name": "Y"},  # missing email
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# REQ-USR-05 — PATCH /api/v1/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-05")
def test_patch_user_partial_200(client):
    """PATCH updates only supplied fields; others remain unchanged. Contract-valid."""
    created = _create_user(client).get_json()
    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"first_name": "Patched"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["first_name"] == "Patched"
    # last_name and email unchanged
    assert body["last_name"] == created["last_name"]
    assert body["email"] == created["email"]
    assert_matches_contract(
        "user-service", "PATCH", f"/api/v1/users/{created['id']}", adapt(resp)
    )


@pytest.mark.req("REQ-USR-05")
def test_patch_user_updated_at_changes(client):
    """PATCH updates updated_at (REQ-USR-05 #1)."""
    import time
    created = _create_user(client).get_json()
    time.sleep(0.01)
    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"last_name": "NewLastName"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated_at"] >= created["updated_at"]


@pytest.mark.req("REQ-USR-05")
def test_patch_user_unknown_404(client):
    """PATCH to a non-existent id returns 404 NOT_FOUND."""
    resp = client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        json={"first_name": "X"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.req("REQ-USR-10")
def test_patch_user_bad_json_400(client):
    """PATCH with malformed JSON body returns 400 MALFORMED_JSON."""
    created = _create_user(client).get_json()
    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        data="bad json",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


@pytest.mark.req("REQ-USR-05")
def test_patch_user_no_recognised_fields_422(client):
    """PATCH body with no recognised fields returns 422 VALIDATION_ERROR (REQ-USR-05 #5)."""
    created = _create_user(client).get_json()
    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"unknown_field": "value"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.req("REQ-USR-B01")
def test_patch_user_duplicate_email_409(client):
    """PATCH with email belonging to another user returns 409 EMAIL_ALREADY_EXISTS."""
    u1 = _create_user(client, email="p1@example.com").get_json()
    _create_user(client, email="p2@example.com")
    resp = client.patch(
        f"/api/v1/users/{u1['id']}",
        json={"email": "p2@example.com"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.req("REQ-USR-B01")
def test_patch_user_own_email_case_variant_ok(client):
    """PATCH with a case variant of the user's own email is allowed (REQ-USR-B01 #4)."""
    created = _create_user(client, email="myemail@example.com").get_json()
    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"email": "MYEMAIL@EXAMPLE.COM"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "myemail@example.com"


# ---------------------------------------------------------------------------
# REQ-USR-06 — DELETE /api/v1/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-06")
def test_delete_user_204(client):
    """DELETE existing user returns 204 with no body."""
    created = _create_user(client).get_json()
    resp = client.delete(f"/api/v1/users/{created['id']}")
    assert resp.status_code == 204
    assert resp.data == b""


@pytest.mark.req("REQ-USR-06")
def test_delete_then_get_404(client):
    """DELETE then GET the same id returns 404 NOT_FOUND (REQ-USR-06 #3)."""
    created = _create_user(client).get_json()
    client.delete(f"/api/v1/users/{created['id']}")
    resp = client.get(f"/api/v1/users/{created['id']}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.req("REQ-USR-06")
def test_delete_unknown_id_404(client):
    """DELETE non-existent user returns 404 NOT_FOUND."""
    resp = client.delete("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# REQ-USR-10 — Error envelope format (cross-cutting)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-10")
def test_error_envelope_structure(client):
    """All error responses use the standard {"error": {"code": ..., "message": ..., "details": ...}} envelope."""
    # Use a 404 to check the envelope structure
    resp = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    body = resp.get_json()
    assert "error" in body
    error = body["error"]
    assert "code" in error
    assert "message" in error
    assert "details" in error
    assert_matches_contract(
        "user-service", "GET",
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        adapt(resp),
    )
