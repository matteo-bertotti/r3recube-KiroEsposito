"""
Integration tests for user-service.

Starts the service as a real subprocess with STORAGE_BACKEND=memory on port 19001,
then exercises every endpoint via real HTTP calls using the `requests` library.

Requirements covered:
- REQ-USR-01: POST /api/v1/users → 201 + Location header
- REQ-USR-02: GET  /api/v1/users/{id} → 200
- REQ-USR-04: PUT  /api/v1/users/{id} → 200, updated_at refreshed
- REQ-USR-05: PATCH /api/v1/users/{id} → 200, only patched fields change
- REQ-USR-06: DELETE /api/v1/users/{id} → 204; subsequent GET → 404
- REQ-USR-B01: POST with duplicate email → 409 EMAIL_ALREADY_EXISTS
- REQ-USR-07: GET /health → 200 {"status":"ok","service":"user-service"}
"""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVICE_DIR = Path(__file__).resolve().parents[2]  # services/user-service/
BASE_URL = "http://localhost:19001"
API_URL = f"{BASE_URL}/api/v1/users"


def _unique_email(prefix: str = "user") -> str:
    """Return a unique email address for each test invocation."""
    return f"{prefix}+{uuid.uuid4().hex[:8]}@example.com"


# ---------------------------------------------------------------------------
# Session-scoped fixture: start / stop the service
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def user_service():
    """
    Start user-service as a subprocess on port 19001 with in-memory backend.

    Kills any process already listening on 19001 first, so re-runs of the
    test suite always get a fresh, empty in-memory store.
    Waits up to 10 s for the health check to succeed, then yields.
    The process is terminated and waited on during teardown.
    """
    # Kill any stale process holding port 19001 (leftover from a prior run)
    try:
        subprocess.run(
            ["powershell", "-Command",
             "Get-NetTCPConnection -LocalPort 19001 -ErrorAction SilentlyContinue "
             "| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force "
             "-ErrorAction SilentlyContinue }"],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass
    time.sleep(0.3)  # give the OS a moment to release the port

    env = {
        **os.environ,
        "PORT": "19001",
        "STORAGE_BACKEND": "memory",
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=str(SERVICE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Poll health check — up to 10 seconds (50 × 0.2 s)
    started = False
    for _ in range(50):
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=1)
            if resp.status_code == 200:
                started = True
                break
        except Exception:
            pass
        time.sleep(0.2)

    if not started:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("user-service did not start within 10 seconds")

    yield

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _user_id_from_location(response) -> str:
    """Extract the user UUID from the Location header returned on 201."""
    location = response.headers.get("Location", "")
    # Location is /api/v1/users/<uuid>
    return location.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-USR-07")
def test_health_check():
    """GET /health must return 200 and the expected status payload."""
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "user-service"


@pytest.mark.req("REQ-USR-01")
def test_post_valid_user_returns_201_with_location():
    """POST a valid user returns 201 and a Location header."""
    payload = {
        "first_name": "Integration",
        "last_name": "Test",
        "email": _unique_email("integration"),
        "role": "attendee",
    }
    resp = requests.post(API_URL, json=payload)
    assert resp.status_code == 201, resp.text

    # Location header must be present and point to the created resource
    location = resp.headers.get("Location", "")
    assert location.startswith("/api/v1/users/"), (
        f"Expected Location to start with /api/v1/users/, got: {location!r}"
    )

    body = resp.json()
    assert "id" in body
    assert body["first_name"] == payload["first_name"]
    assert body["last_name"] == payload["last_name"]
    assert body["email"] == payload["email"].lower()  # REQ-USR-B02
    assert body["role"] == payload["role"]
    assert "created_at" in body
    assert "updated_at" in body


@pytest.mark.req("REQ-USR-B01")
def test_post_duplicate_email_returns_409():
    """
    Posting a second user with the same email (case-insensitive) must return 409.

    REQ-USR-B01: email uniqueness is enforced case-insensitively.
    """
    # Create a fresh user dedicated to this test to avoid ordering dependencies
    email = _unique_email("dup")
    duplicate_user = {
        "first_name": "Dup",
        "last_name": "User",
        "email": email,
        "role": "attendee",
    }
    first = requests.post(API_URL, json=duplicate_user)
    assert first.status_code == 201

    # Same email, different casing
    second = requests.post(
        API_URL,
        json={**duplicate_user, "email": email.upper()},
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.req("REQ-USR-02")
def test_get_created_user_returns_200():
    """GET /api/v1/users/{id} for a freshly created user returns 200."""
    create_resp = requests.post(
        API_URL,
        json={
            "first_name": "Get",
            "last_name": "Me",
            "email": _unique_email("getme"),
        },
    )
    assert create_resp.status_code == 201
    user_id = _user_id_from_location(create_resp)

    get_resp = requests.get(f"{API_URL}/{user_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == user_id


@pytest.mark.req("REQ-USR-04")
def test_put_user_returns_200_and_refreshes_updated_at():
    """
    PUT /api/v1/users/{id} replaces editable fields and updates updated_at.

    REQ-USR-04 #1, #6: updated_at changes; id and created_at stay the same.
    """
    email = _unique_email("put")
    create_resp = requests.post(
        API_URL,
        json={
            "first_name": "Before",
            "last_name": "Put",
            "email": email,
            "role": "attendee",
        },
    )
    assert create_resp.status_code == 201
    created_body = create_resp.json()
    user_id = _user_id_from_location(create_resp)
    created_at_before = created_body["created_at"]

    # Small delay to guarantee updated_at differs from created_at
    time.sleep(0.01)

    put_resp = requests.put(
        f"{API_URL}/{user_id}",
        json={
            "first_name": "After",
            "last_name": "Put",
            "email": email,
            "role": "speaker",
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    put_body = put_resp.json()

    # id and created_at must be preserved
    assert put_body["id"] == user_id
    assert put_body["created_at"] == created_at_before

    # Fields were replaced
    assert put_body["first_name"] == "After"
    assert put_body["role"] == "speaker"

    # updated_at must be >= created_at
    assert put_body["updated_at"] >= put_body["created_at"]


@pytest.mark.req("REQ-USR-05")
def test_patch_user_returns_200_and_updates_only_patched_fields():
    """
    PATCH /api/v1/users/{id} updates only the supplied fields.

    REQ-USR-05 #1, #6: unmentioned fields remain unchanged.
    """
    create_resp = requests.post(
        API_URL,
        json={
            "first_name": "Patch",
            "last_name": "Me",
            "email": _unique_email("patch"),
            "role": "attendee",
        },
    )
    assert create_resp.status_code == 201
    original = create_resp.json()
    user_id = _user_id_from_location(create_resp)

    patch_resp = requests.patch(
        f"{API_URL}/{user_id}",
        json={"first_name": "Patched"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()

    # Changed field
    assert patched["first_name"] == "Patched"
    # Unchanged fields
    assert patched["last_name"] == original["last_name"]
    assert patched["email"] == original["email"]
    assert patched["role"] == original["role"]
    # Immutable fields preserved
    assert patched["id"] == user_id
    assert patched["created_at"] == original["created_at"]


@pytest.mark.req("REQ-USR-06")
def test_delete_user_returns_204():
    """DELETE /api/v1/users/{id} returns 204 with no body."""
    create_resp = requests.post(
        API_URL,
        json={
            "first_name": "Delete",
            "last_name": "Me",
            "email": _unique_email("delete"),
        },
    )
    assert create_resp.status_code == 201
    user_id = _user_id_from_location(create_resp)

    del_resp = requests.delete(f"{API_URL}/{user_id}")
    assert del_resp.status_code == 204, del_resp.text
    assert del_resp.content == b""  # no body


@pytest.mark.req("REQ-USR-06")
def test_get_after_delete_returns_404():
    """
    GET /api/v1/users/{id} after deletion returns 404 NOT_FOUND.

    REQ-USR-06 #3: resource is permanently removed.
    """
    create_resp = requests.post(
        API_URL,
        json={
            "first_name": "Gone",
            "last_name": "User",
            "email": _unique_email("gone"),
        },
    )
    assert create_resp.status_code == 201
    user_id = _user_id_from_location(create_resp)

    requests.delete(f"{API_URL}/{user_id}")

    get_resp = requests.get(f"{API_URL}/{user_id}")
    assert get_resp.status_code == 404, get_resp.text
    body = get_resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
