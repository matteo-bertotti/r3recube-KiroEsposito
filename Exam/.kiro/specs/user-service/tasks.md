# Implementation Plan: user-service

_Derived from:_ `.kiro/specs/user-service/requirements.md` · `.kiro/specs/user-service/design.md`

Each task maps to one atomic, committable unit of work.  
Commit convention: `feat(user-service): <description> [T-NN]`

---

## Overview

16 tasks implementing `user-service` from scratch: project scaffold, configuration,
domain model and business logic, three repository backends, Flask API layer (7
endpoints + health check), and three suites of tests (domain unit, repository unit,
API unit with contract validation, integration).

The dependency order follows the layered architecture: config and models first, then
repository, then service logic, then API, then tests.

---

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["T-01"]},
    {"wave": 2, "tasks": ["T-02"]},
    {"wave": 3, "tasks": ["T-03"]},
    {"wave": 4, "tasks": ["T-04", "T-05"]},
    {"wave": 5, "tasks": ["T-06", "T-07"]},
    {"wave": 6, "tasks": ["T-08"]},
    {"wave": 7, "tasks": ["T-09"]},
    {"wave": 8, "tasks": ["T-10"]},
    {"wave": 9, "tasks": ["T-11"]},
    {"wave": 10, "tasks": ["T-12"]},
    {"wave": 11, "tasks": ["T-13", "T-14", "T-15", "T-16"]}
  ],
  "edges": [
    {"from": "T-01", "to": "T-02"},
    {"from": "T-02", "to": "T-03"},
    {"from": "T-03", "to": "T-04"},
    {"from": "T-03", "to": "T-05"},
    {"from": "T-05", "to": "T-06"},
    {"from": "T-05", "to": "T-07"},
    {"from": "T-06", "to": "T-08"},
    {"from": "T-07", "to": "T-08"},
    {"from": "T-08", "to": "T-09"},
    {"from": "T-09", "to": "T-10"},
    {"from": "T-10", "to": "T-11"},
    {"from": "T-11", "to": "T-12"},
    {"from": "T-12", "to": "T-13"},
    {"from": "T-12", "to": "T-14"},
    {"from": "T-12", "to": "T-15"},
    {"from": "T-12", "to": "T-16"}
  ]
}
```

---

## Tasks

- [x] 1. Project scaffold — directory structure and dependencies
  - Create directories: `app/api/`, `app/domain/`, `app/repository/`, `tests/unit/`, `tests/integration/` under `services/user-service/`
  - Add `__init__.py` to every Python package directory
  - Write `services/user-service/requirements.txt` with pinned versions: `flask==3.1.1`, `requests==2.32.3`, `pytest==8.3.5`, `pytest-cov==6.1.0`, `responses==0.25.7`
  - Add `pytest.ini` inside `services/user-service/` registering the custom marker `req`
  - _Requirements: REQ-USR-08, REQ-USR-09_

- [x] 2. Configuration module (`app/config.py`)
  - Read `PORT` with `int(os.environ["PORT"])`; raise a descriptive `KeyError` if absent
  - `STORAGE_BACKEND` defaults to `"memory"`; `DATA_DIR` defaults to `"./data"`
  - No other module in `app/` may call `os.environ` directly
  - _Requirements: REQ-USR-09_

- [x] 3. Domain model (`app/domain/models.py`)
  - Implement `User` as a `@dataclass` with fields: `id`, `first_name`, `last_name`, `email`, `company`, `role`, `created_at`, `updated_at`
  - `User.create(data)` generates UUID v4 `id`, sets `created_at`/`updated_at` to `datetime.utcnow()`, defaults `role` to `"attendee"`, stores `email` in lowercase
  - `user.to_dict()` serializes timestamps as ISO 8601 UTC strings ending in `Z`
  - `User.from_dict(d)` reconstructs a `User` from a stored dict
  - No imports from Flask or from `repository/`
  - _Requirements: REQ-USR-01, REQ-USR-B02_

- [x] 4. Domain exceptions and `UserService` (`app/domain/user_service.py`)
  - Define exceptions: `ValidationError(field, message)`, `EmailAlreadyExists`, `NotFound`
  - `UserService.__init__(self, repo)` stores injected repository
  - `create_user(data)`: validate all fields, normalize email, check uniqueness, save and return user
  - `get_user(id)`: return user or raise `NotFound`
  - `list_users(page, page_size, role, email)`: validate pagination params, filter (REQ-USR-B03), paginate, return `UserPage` dict
  - `replace_user(id, data)`: raise `NotFound` if absent; validate all fields; check email uniqueness excluding self; preserve `id`/`created_at`; default `role` to `"attendee"`
  - `update_user(id, data)`: raise `NotFound` if absent; validate only present fields; raise `ValidationError` if no recognized fields; check email uniqueness excluding self; update only present fields
  - `delete_user(id)`: raise `NotFound` if absent; otherwise delete
  - No Flask imports; no `os.environ` calls
  - _Requirements: REQ-USR-01, REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-B01, REQ-USR-B02, REQ-USR-B03_

- [x] 5. Repository interface and `MemoryUserRepository`
  - `app/repository/base.py`: define ABC `UserRepository` with methods `save`, `find_by_id`, `find_by_email`, `list(role, email)`, `delete(id) -> bool`
  - `app/repository/memory.py`: implement `MemoryUserRepository` using `dict[str, User]`
  - `find_by_email` compares against already-lowercase stored emails
  - `delete` returns `False` if id absent, `True` otherwise
  - No file I/O or sqlite3 imports
  - _Requirements: REQ-USR-08_

- [x] 6. `JsonUserRepository` (`app/repository/json_repo.py`)
  - Accept `data_dir: str`; create directory if absent
  - Data file: `{data_dir}/users.json` with structure `{"users": [...]}`
  - Every write reads, mutates, and rewrites the full file
  - Missing file treated as empty collection
  - Only standard-library `json` module used
  - _Requirements: REQ-USR-08_

- [x] 7. `SqliteUserRepository` (`app/repository/sqlite_repo.py`)
  - Accept `data_dir: str`; create directory if absent; db path `{data_dir}/users.db`
  - `_init_db()` runs `CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, company TEXT, role TEXT NOT NULL DEFAULT 'attendee', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`
  - `save` uses `INSERT OR REPLACE`
  - `find_by_email` queries `WHERE email = ?`
  - `list` builds `WHERE` clause dynamically from provided filters
  - Only standard-library `sqlite3`; no ORM
  - _Requirements: REQ-USR-08_

- [x] 8. Repository factory (`app/repository/__init__.py`)
  - Expose `get_repository(backend: str, data_dir: str) -> UserRepository`
  - Return `JsonUserRepository` for `"json"`, `SqliteUserRepository` for `"sqlite"`, `MemoryUserRepository` otherwise
  - This is the single backend-selection point in the codebase
  - _Requirements: REQ-USR-08_

- [x] 9. Error helper (`app/api/errors.py`)
  - `error_response(code, message, status, details=None) -> Response` returns Flask `Response` with `Content-Type: application/json` and body `{"error": {"code": ..., "message": ..., "details": ...}}`
  - This is the only place in the service that constructs error response bodies
  - _Requirements: REQ-USR-10_

- [x] 10. Flask application and health check (`app/__main__.py`)
  - Import `PORT`, `STORAGE_BACKEND`, `DATA_DIR` from `app.config`
  - Call `get_repository(STORAGE_BACKEND, DATA_DIR)`, instantiate `UserService(repo)`, create Flask app, register Blueprint, call `app.run(host="0.0.0.0", port=PORT)`
  - `GET /health` returns `200 {"status": "ok", "service": "user-service"}`
  - Running without `PORT` prints a clear error and exits non-zero
  - _Requirements: REQ-USR-07, REQ-USR-09_

- [x] 11. POST and GET list endpoints (`app/api/users.py`)
  - `POST /api/v1/users`: 400 on bad JSON; 201 + `Location` header on success; 422 on `ValidationError`; 409 on `EmailAlreadyExists`
  - `GET /api/v1/users`: read `page` (default 1), `page_size` (default 20), `role`, `email` from query string; 200 `UserPage` on success; 422 on invalid pagination
  - _Requirements: REQ-USR-01, REQ-USR-B01, REQ-USR-B02, REQ-USR-03, REQ-USR-B03, REQ-USR-10_

- [x] 12. GET by id, PUT, PATCH, DELETE endpoints (`app/api/users.py`)
  - `GET /api/v1/users/<id>`: 200 on success; 404 if absent
  - `PUT /api/v1/users/<id>`: 200 updated user; 400 bad JSON; 404 not found; 422 validation; 409 duplicate email
  - `PATCH /api/v1/users/<id>`: 200 updated user; 400 bad JSON; 404 not found; 422 validation; 409 duplicate email
  - `DELETE /api/v1/users/<id>`: 204 empty body on success; 404 if absent
  - _Requirements: REQ-USR-02, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-B01, REQ-USR-B02, REQ-USR-10_

- [x] 13. Unit tests — domain logic (`tests/unit/test_domain.py`)
  - All tests use `MemoryUserRepository`; no Flask, no HTTP
  - Mark each test with `@pytest.mark.req("REQ-USR-XX")` or include the ID in the test name
  - Cover: valid creation (UUID + timestamps); email lowercased (REQ-USR-B02); duplicate email any case → `EmailAlreadyExists` (REQ-USR-B01); missing required fields → `ValidationError`; field length violations → `ValidationError`; invalid email format → `ValidationError`; invalid role → `ValidationError`; filter by role and email (REQ-USR-B03); pagination offset/slice; `page_size > 100` → `ValidationError`; `replace_user` preserves `id`/`created_at`; `replace_user` without role defaults to `"attendee"`; `update_user` updates only present fields; `update_user` empty body → `ValidationError`; `delete_user` then second call → `NotFound`; `get_user` unknown id → `NotFound`
  - _Requirements: REQ-USR-01, REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-B01, REQ-USR-B02, REQ-USR-B03_

- [x] 14. Unit tests — repository backends (`tests/unit/test_repository.py`)
  - Parametrize over all three backends using a fixture with `tmp_path`
  - Per backend: `save` + `find_by_id` round-trip; `find_by_email` match; `list` no filters; `list` role filter; `list` email filter; `delete` returns `True`/`False`; SQLite duplicate email raises `IntegrityError`
  - _Requirements: REQ-USR-08_

- [x] 15. Unit tests — API routes with contract validation (`tests/unit/test_api_users.py`)
  - Use `app.test_client()` with `STORAGE_BACKEND=memory`
  - Call `assert_matches_contract` from `contracts/validator.py` on at least one success response per endpoint
  - Cover: POST valid (201, Location header, contract); POST bad JSON (400); POST missing field (422); POST duplicate email (409); GET list (200, contract); GET list role filter; GET list email filter; GET list page_size=200 (422); GET by id (200, contract); GET unknown id (404); PUT valid (200, updated_at changed, contract); PUT unknown (404); PUT duplicate email (409); PATCH partial (200); PATCH unknown (404); PATCH no fields (422); DELETE (204); DELETE then GET (404); DELETE unknown (404); GET /health (200)
  - _Requirements: REQ-USR-01, REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-B01, REQ-USR-10_

- [x] 16. Integration tests (`tests/integration/test_integration.py`)
  - Session-scoped fixture: start `python -m app` in `services/user-service/` with `PORT=19001`, `STORAGE_BACKEND=memory`; poll `GET /health` up to 10 s; terminate in teardown
  - Real HTTP to `http://localhost:19001`: POST valid (201, Location); GET created (200); PUT (200, updated_at differs); PATCH (200); DELETE (204); GET after delete (404); POST duplicate email (409); GET /health (200)
  - _Requirements: REQ-USR-01, REQ-USR-02, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-B01_

---

## Notes

- Tasks 1–12 are implementation tasks; commit each as `feat(user-service): <description> [T-NN]`.
- Tasks 13–16 are test tasks; commit each as `test(user-service): <description> [T-NN]`.
- Coverage is measured after task 15: `pytest services/user-service/tests/unit --cov=app`; target ≥ 80%.
- Integration tests (task 16) require the service dependencies installed: `pip install -r services/user-service/requirements.txt`.
- `DATA_DIR` output (`json`/`sqlite` backends) is excluded from git via `services/*/data/` in the root `.gitignore`.
