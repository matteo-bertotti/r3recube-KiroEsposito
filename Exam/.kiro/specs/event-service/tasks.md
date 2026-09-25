# Implementation Plan: event-service

_Derived from:_ `.kiro/specs/event-service/requirements.md` · `.kiro/specs/event-service/design.md`

Each task maps to one atomic, committable unit of work.  
Commit convention: `feat(event-service): <description> [T-NN]` for implementation tasks,
`test(event-service): <description> [T-NN]` for test tasks.

---

## Overview

18 tasks implementing `event-service` from scratch: project scaffold, configuration,
domain model, a dedicated `clients/` layer to call `user-service` (the one structural
difference from `user-service`), business logic with a status state machine, three
repository backends, Flask API layer (6 endpoints + health check), and five suites of
tests (domain unit incl. property tests, `UserClient` unit, repository unit incl.
property test, API unit with contract validation, integration against a real
`user-service` subprocess).

The dependency order follows the layered architecture from `design.md`: config and
domain model first, then the `UserClient` (needed by the domain layer), then
`EventService`, then the three repository backends and their factory, then the API
layer, then tests.

---

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["T-01"]},
    {"wave": 2, "tasks": ["T-02"]},
    {"wave": 3, "tasks": ["T-03"]},
    {"wave": 4, "tasks": ["T-04"]},
    {"wave": 5, "tasks": ["T-05"]},
    {"wave": 6, "tasks": ["T-06"]},
    {"wave": 7, "tasks": ["T-07", "T-08"]},
    {"wave": 8, "tasks": ["T-09"]},
    {"wave": 9, "tasks": ["T-10"]},
    {"wave": 10, "tasks": ["T-11"]},
    {"wave": 11, "tasks": ["T-12"]},
    {"wave": 12, "tasks": ["T-13"]},
    {"wave": 13, "tasks": ["T-14", "T-15", "T-16", "T-17", "T-18"]}
  ],
  "edges": [
    {"from": "T-01", "to": "T-02"},
    {"from": "T-02", "to": "T-03"},
    {"from": "T-03", "to": "T-04"},
    {"from": "T-04", "to": "T-05"},
    {"from": "T-05", "to": "T-06"},
    {"from": "T-06", "to": "T-07"},
    {"from": "T-06", "to": "T-08"},
    {"from": "T-07", "to": "T-09"},
    {"from": "T-08", "to": "T-09"},
    {"from": "T-09", "to": "T-10"},
    {"from": "T-10", "to": "T-11"},
    {"from": "T-11", "to": "T-12"},
    {"from": "T-12", "to": "T-13"},
    {"from": "T-13", "to": "T-14"},
    {"from": "T-13", "to": "T-15"},
    {"from": "T-13", "to": "T-16"},
    {"from": "T-13", "to": "T-17"},
    {"from": "T-13", "to": "T-18"}
  ]
}
```

---

## Tasks

- [ ] 1. Project scaffold — directory structure and dependencies
  - Create directories: `app/api/`, `app/domain/`, `app/clients/`, `app/repository/`, `tests/unit/`, `tests/integration/` under `services/event-service/`
  - Add `__init__.py` to every Python package directory (`app/`, `app/api/`, `app/domain/`, `app/clients/`, `app/repository/`, `tests/`, `tests/unit/`, `tests/integration/`)
  - Write `services/event-service/requirements.txt` with pinned versions: `flask==3.1.1`, `requests==2.32.3`, `pytest==8.3.5`, `pytest-cov==6.1.0`, `responses==0.25.7`
  - Add `pytest.ini` inside `services/event-service/` registering the custom marker `req`
  - _Requirements: REQ-EVT-F07, REQ-EVT-F08_

- [ ] 2. Configuration module (`app/config.py`)
  - Read `PORT` with `int(os.environ["PORT"])`; raise a descriptive `KeyError`/error if absent or out of the 1–65535 range
  - `USER_SERVICE_URL` defaults to `"http://localhost:5001"`; `STORAGE_BACKEND` defaults to `"memory"`; `DATA_DIR` defaults to `"./data"`
  - Expose a fixed `USER_SERVICE_TIMEOUT = 2` (seconds) constant, never configurable via environment
  - No other module in `app/` may call `os.environ` directly
  - _Requirements: REQ-EVT-F08_

- [ ] 3. Domain model (`app/domain/models.py`)
  - Implement `Event` as a `@dataclass` with fields: `id`, `title`, `description`, `organizer_id`, `venue`, `city`, `start_date`, `end_date`, `capacity`, `price` (`Decimal`), `status`, `created_at`, `updated_at`
  - `Event.create(data)` generates UUID v4 `id`, sets `created_at`/`updated_at` to the current UTC timestamp, defaults `status` to `"draft"` when absent, normalizes a missing/`null` `description` to `None`
  - `event.to_dict()` serializes `start_date`/`end_date` as `"YYYY-MM-DD"` strings, timestamps as ISO 8601 UTC strings ending in `Z`, and `price` as a number with exactly 2 decimals
  - `Event.from_dict(d)` reconstructs an `Event` from a stored dict
  - No imports from Flask, `repository/`, or `clients/`
  - _Requirements: REQ-EVT-01, REQ-EVT-F03, REQ-EVT-F10_

- [ ] 4. `UserClient` (`app/clients/user_client.py`)
  - `UserClient.__init__(self, base_url, timeout=2.0)`
  - `get_organizer(organizer_id)` calls `GET {base_url}/api/v1/users/{organizer_id}` with the configured timeout
  - Translate outcomes: `requests.Timeout`/`requests.ConnectionError` → raise `DependencyUnavailable("user-service")`; HTTP 404 → raise `ReferenceNotFound("organizer_id", organizer_id)`; HTTP 500–599 → raise `DependencyUnavailable("user-service")`; otherwise return the parsed JSON user dict
  - Does not check the `role` field — that check stays in `domain/event_service.py` (REQ-EVT-B02) so it is testable without re-mocking HTTP
  - This is the only module allowed to import and call `requests` directly
  - _Requirements: REQ-EVT-B01, REQ-EVT-B05, REQ-EVT-F08_

- [ ] 5. Domain exceptions and `EventService` (`app/domain/event_service.py`)
  - Define exceptions: `ValidationError(field, message)`, `ReferenceNotFound(field, value)`, `InvalidOrganizer(organizer_id, role)`, `InvalidStatusTransition(current, requested)`, `DependencyUnavailable(service_name)`, `NotFound`
  - `EventService.__init__(self, repository, user_client)` stores both injected dependencies
  - `create_event(data)`: validate all fields (aggregating every violation into one `ValidationError` with a `details` map, never stopping at the first failure), validate `end_date >= start_date`, call `_validate_organizer` unconditionally, create and persist
  - `_validate_organizer(organizer_id)`: calls `user_client.get_organizer(organizer_id)`, then raises `InvalidOrganizer` if the returned `role != "organizer"`
  - `get_event(id)`: return event or raise `NotFound` (including when `id` is not a valid UUID)
  - `list_events(page, page_size, status, city)`: validate pagination params, filter by `status` (exact, case-sensitive) and `city` (case-insensitive) combined with AND, paginate after filtering, return an `EventPage` dict
  - `replace_event(id, data)`: raise `NotFound` if absent; validate all fields as in `create_event`; call `_validate_organizer` only if `organizer_id` is present and differs from the stored value; apply the status transition check via `_check_transition`; preserve `id`/`created_at`
  - `update_event(id, data)`: raise `NotFound` if absent; validate only the fields present in the payload; same organizer/date/status rules as `replace_event`, applied only to provided fields; leave absent fields unchanged
  - `delete_event(id)`: raise `NotFound` if absent; otherwise delete
  - Implement `_ALLOWED_TRANSITIONS = {("draft","published"), ("draft","cancelled"), ("published","cancelled")}` and `_check_transition(current, requested)`: no-op if equal, raise `InvalidStatusTransition` otherwise (making `cancelled` terminal)
  - No Flask imports; no `os.environ` calls; no direct `requests` calls (always through `user_client`)
  - _Requirements: REQ-EVT-01, REQ-EVT-02, REQ-EVT-03, REQ-EVT-04, REQ-EVT-05, REQ-EVT-06, REQ-EVT-F01, REQ-EVT-F02, REQ-EVT-F03, REQ-EVT-F10, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B06_

- [ ] 6. Repository interface and `MemoryEventRepository`
  - `app/repository/base.py`: define ABC `EventRepository` with methods `save(event)`, `find_by_id(id) -> Event | None`, `list(status, city) -> list[Event]`, `delete(id) -> bool`
  - `app/repository/memory.py`: implement `MemoryEventRepository` using `dict[str, Event]`
  - `list` applies the `status` filter with exact case-sensitive comparison and the `city` filter case-insensitively, directly inside the repository implementation
  - `delete` returns `False` if id absent, `True` otherwise
  - No file I/O or `sqlite3` imports
  - _Requirements: REQ-EVT-F07, REQ-EVT-B06_

- [ ] 7. `JsonEventRepository` (`app/repository/json_repo.py`)
  - Accept `data_dir: str`; create the directory if absent
  - Data file: `{data_dir}/events.json` with structure `{"events": [...]}`
  - Every write reads, mutates, and rewrites the full file; missing file treated as an empty collection
  - Only standard-library `json` module used; same filter semantics as `MemoryEventRepository`
  - _Requirements: REQ-EVT-F07_

- [ ] 8. `SqliteEventRepository` (`app/repository/sqlite_repo.py`)
  - Accept `data_dir: str`; create the directory if absent; db path `{data_dir}/events.db`
  - `_init_db()` runs `CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, organizer_id TEXT NOT NULL, venue TEXT NOT NULL, city TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, capacity INTEGER NOT NULL, price TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`
  - `price` is stored and read back as `TEXT` (decimal string) to avoid float rounding
  - `save` uses `INSERT OR REPLACE`; `list` builds the `WHERE` clause dynamically from the provided `status`/`city` filters, comparing `city` case-insensitively (e.g. `LOWER(city) = LOWER(?)`)
  - Only standard-library `sqlite3`; no ORM
  - _Requirements: REQ-EVT-F07_

- [ ] 9. Repository factory (`app/repository/__init__.py`)
  - Expose `get_repository(backend: str, data_dir: str) -> EventRepository`
  - Return `JsonEventRepository` for `"json"`, `SqliteEventRepository` for `"sqlite"`, `MemoryEventRepository` for `"memory"` or when unset
  - Raise a clear startup error identifying the invalid value when `backend` is anything else
  - This is the single backend-selection point in the codebase
  - _Requirements: REQ-EVT-F07_

- [ ] 10. Error helper (`app/api/errors.py`)
  - `error_response(code, message, status, details=None) -> Response` returns a Flask `Response` with `Content-Type: application/json` and body `{"error": {"code": ..., "message": ..., "details": ...}}`
  - This is the only place in the service that constructs error response bodies
  - _Requirements: REQ-EVT-F06_

- [ ] 11. Flask application and health check (`app/__main__.py`)
  - Import `PORT`, `USER_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR` from `app.config`
  - Call `get_repository(STORAGE_BACKEND, DATA_DIR)`, instantiate `UserClient(USER_SERVICE_URL)`, instantiate `EventService(repo, user_client)`, create the Flask app, register the Blueprint, call `app.run(host="0.0.0.0", port=PORT)`
  - `GET /health` returns `200 {"status": "ok", "service": "event-service"}` regardless of storage state or `user-service` reachability
  - Running without `PORT` prints a clear error and exits non-zero
  - _Requirements: REQ-EVT-F05, REQ-EVT-F08_

- [ ] 12. POST and GET list endpoints (`app/api/events.py`)
  - `POST /api/v1/events`: parse JSON body first (400 `MALFORMED_JSON` on invalid/empty body, evaluated before field validation); on success call `create_event`, 201 + `Location` header pointing to `/api/v1/events/{id}`; map `ValidationError` → 422 `VALIDATION_ERROR`, `ReferenceNotFound` → 422 `REFERENCE_NOT_FOUND`, `InvalidOrganizer` → 422 `INVALID_ORGANIZER`, `DependencyUnavailable` → 503 `DEPENDENCY_UNAVAILABLE`
  - `GET /api/v1/events`: read `page` (default 1), `page_size` (default 20), `status`, `city` from the query string; 200 `EventPage` on success; 422 `VALIDATION_ERROR` on invalid pagination or an out-of-enum `status` filter
  - _Requirements: REQ-EVT-01, REQ-EVT-03, REQ-EVT-F01, REQ-EVT-F02, REQ-EVT-F04, REQ-EVT-F06, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B05, REQ-EVT-B06_

- [ ] 13. GET by id, PUT, PATCH, DELETE endpoints (`app/api/events.py`)
  - `GET /api/v1/events/<id>`: 200 on success; 404 `NOT_FOUND` if absent or `id` is not a valid UUID v4
  - `PUT /api/v1/events/<id>`: 200 updated event; 400 `MALFORMED_JSON`; 404 `NOT_FOUND`; 422 `VALIDATION_ERROR`/`REFERENCE_NOT_FOUND`/`INVALID_ORGANIZER`/`INVALID_STATUS_TRANSITION`; 503 `DEPENDENCY_UNAVAILABLE`
  - `PATCH /api/v1/events/<id>`: same status/error mapping as PUT, applied to partial payloads
  - `DELETE /api/v1/events/<id>`: 204 empty body on success; 404 `NOT_FOUND` if absent or not a valid UUID
  - Register a 405 handler (with `Allow` header) for methods not defined on a given path
  - _Requirements: REQ-EVT-02, REQ-EVT-04, REQ-EVT-05, REQ-EVT-06, REQ-EVT-F01, REQ-EVT-F02, REQ-EVT-F04, REQ-EVT-F06, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05_

- [ ] 14. Unit tests — domain logic (`tests/unit/test_domain.py`)
  - All tests use `MemoryEventRepository` and a hand-written stub/fake `UserClient`; no Flask, no HTTP
  - Mark each test with `@pytest.mark.req("REQ-EVT-XX")`
  - Cover: valid creation with organizer `role=organizer` (UUID generated, `created_at`/`updated_at` present, `status` defaults to `draft`) (REQ-EVT-01, REQ-EVT-F10); organizer not found via stub raising `ReferenceNotFound` → 422 semantics (REQ-EVT-B01); organizer with wrong role → `InvalidOrganizer` (REQ-EVT-B02); `end_date < start_date` on create, on PUT, and on PATCH with partially provided dates → `ValidationError` (REQ-EVT-B03); combined `status`/`city` filtering (REQ-EVT-B06); pagination offset/slice correctness and `page_size > 100` → `ValidationError` (REQ-EVT-03); PATCH updates only provided fields, unknown field → `ValidationError` (REQ-EVT-F02, REQ-EVT-F03); `delete_event` then a second call → `NotFound` (REQ-EVT-06)
  - **Property test**: using `@pytest.mark.parametrize` over the exhaustive 3×3 cartesian product of `(current, requested)` pairs from `{draft, published, cancelled}` (9 cases total), assert the transition is accepted if and only if `current == requested` or the pair belongs to the allowed set — **Property 3: le transizioni di stato seguono solo il grafo consentito e cancelled è terminale**, `@pytest.mark.req("REQ-EVT-B04")`
  - **Property test**: a plain pytest test (optionally parametrized over 2-3 fixed, manually constructed sequences of PUT/PATCH operations) applied to a created event, asserting `id` and `created_at` never change and `updated_at` is non-decreasing at each step — **Property 4/5: immutabilità di id/created_at e monotonicità di updated_at**, `@pytest.mark.req("REQ-EVT-04")` and `@pytest.mark.req("REQ-EVT-05")`
  - _Requirements: REQ-EVT-01, REQ-EVT-02, REQ-EVT-03, REQ-EVT-04, REQ-EVT-05, REQ-EVT-06, REQ-EVT-F01, REQ-EVT-F02, REQ-EVT-F03, REQ-EVT-F10, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B06_

- [ ] 15. Unit tests — `UserClient` (`tests/unit/test_user_client.py`)
  - Mock outbound HTTP with `responses`; no `user-service` instance is started
  - Cover: HTTP 200 with `role=organizer` → user dict returned; HTTP 404 → `ReferenceNotFound`; simulated timeout → `DependencyUnavailable`; simulated `ConnectionError` → `DependencyUnavailable`; HTTP 500/502/503 → `DependencyUnavailable`
  - _Requirements: REQ-EVT-B01, REQ-EVT-B05, REQ-EVT-F08_

- [ ] 16. Unit tests — repository backends (`tests/unit/test_repository.py`)
  - Parametrize over all three backends using a fixture with `tmp_path`
  - Per backend: `save` + `find_by_id` round-trip; `list` with no filters, with `status` filter, with `city` filter (case-insensitive), and with both combined; `delete` returns `True`/`False`
  - **Property test**: apply the same fixed, manually constructed sequence of CRUD operations (create, update, filter, delete) to all three backends in turn (optionally parametrized over 2-3 fixed sequences) and assert identical observable results across backends — **Property 7: intercambiabilità dei backend**, `@pytest.mark.req("REQ-EVT-F07")`
  - _Requirements: REQ-EVT-F07, REQ-EVT-B06_

- [ ] 17. Unit tests — API routes with contract validation (`tests/unit/test_api_events.py`)
  - Use `app.test_client()` with `STORAGE_BACKEND=memory`; mock `user-service` calls with `responses`
  - Call `assert_matches_contract` from `contracts/validator.py` on at least one response per endpoint (success and at least one error case)
  - Cover: POST valid (201, `Location` header, contract); POST bad JSON (400 `MALFORMED_JSON`); POST missing/invalid/unknown/read-only field (422 `VALIDATION_ERROR`); POST with `user-service` mocked to 404 (422 `REFERENCE_NOT_FOUND`); POST with `user-service` mocked to 200 and `role != organizer` (422 `INVALID_ORGANIZER`); POST with `user-service` mocked to timeout/5xx (503 `DEPENDENCY_UNAVAILABLE`); GET list (200, contract), with `status` filter, with `city` filter, with `page_size=200` (422); GET by id (200, contract); GET unknown/non-UUID id (404 `NOT_FOUND`); PUT valid (200, `updated_at` changed, contract); PUT disallowed status transition (422 `INVALID_STATUS_TRANSITION`); PUT unknown id (404); PATCH partial (200); PATCH unknown id (404); DELETE (204); DELETE then GET (404); 405 on an unsupported method; `GET /health` (200)
  - _Requirements: REQ-EVT-01, REQ-EVT-02, REQ-EVT-03, REQ-EVT-04, REQ-EVT-05, REQ-EVT-06, REQ-EVT-F01, REQ-EVT-F02, REQ-EVT-F04, REQ-EVT-F05, REQ-EVT-F06, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05, REQ-EVT-B06_

- [ ] 18. Integration tests (`tests/integration/test_integration.py`)
  - Session-scoped `autouse` fixture: start a real `user-service` (`python -m app` in `services/user-service/`) with `PORT=19011`, `STORAGE_BACKEND=memory`, and `event-service` (`python -m app` in `services/event-service/`) with `PORT=19002`, `STORAGE_BACKEND=memory`, `USER_SERVICE_URL=http://localhost:19011`; poll both `/health` endpoints up to 10 s; terminate both in teardown
  - **Positive case**: create a real organizer on `user-service` (`role=organizer`), then create an event referencing that `organizer_id` on `event-service` → 201, and the event is subsequently readable via `GET /api/v1/events/{id}` (REQ-EVT-01, REQ-EVT-B01, REQ-EVT-B02)
  - **`REFERENCE_NOT_FOUND` case**: create an event with a syntactically valid but non-existent `organizer_id` (random UUID v4) → 422 `REFERENCE_NOT_FOUND` (REQ-EVT-B01)
  - **`DEPENDENCY_UNAVAILABLE` case**: stop the `user-service` subprocess (or point `USER_SERVICE_URL` at an unused port for that test) and attempt to create an event → 503 `DEPENDENCY_UNAVAILABLE` (REQ-EVT-B05)
  - _Requirements: REQ-EVT-01, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

---

## Notes

- Tasks 1–13 are implementation tasks; commit each as `feat(event-service): <description> [T-NN]`.
- Tasks 14–18 are test tasks; commit each as `test(event-service): <description> [T-NN]`.
- Coverage is measured after task 17: `pytest services/event-service/tests/unit --cov=app`; target ≥ 80%.
- Integration tests (task 18) require both services' dependencies installed: `pip install -r services/user-service/requirements.txt` and `pip install -r services/event-service/requirements.txt`.
- `DATA_DIR` output (`json`/`sqlite` backends) is excluded from git via `services/*/data/` in the root `.gitignore`.
