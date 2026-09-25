# Implementation Plan: registration-service

_Derived from:_ `.kiro/specs/registration-service/requirements.md` · `.kiro/specs/registration-service/design.md`

Each task maps to one atomic, committable unit of work.
Commit convention: `feat(registration-service): <description> [T-NN]` for implementation tasks,
`test(registration-service): <description> [T-NN]` for test tasks.

---

## Overview

21 tasks implementing `registration-service` from scratch: project scaffold,
configuration, domain model, **two** dedicated `clients/` modules (`user_client.py` and
`event_client.py` — the structural difference from `event-service`, which has only
one), business logic with the strict evaluation order of REQ-REG-01 AC7 and the
per-event capacity lock, three repository backends plus factory, Flask API layer (7
endpoints + health check, with `/stats` registered before the parametric `/{id}`
route), and six suites of tests (domain unit incl. property tests, `UserClient` unit,
`EventClient` unit, repository unit incl. property test, API unit with contract
validation, integration against real `user-service`/`event-service` subprocesses), plus
a final coverage checkpoint.

The dependency order follows the layered architecture from `design.md`: config and
domain model first, then the two HTTP clients (needed by the domain layer), then
`RegistrationService`, then the three repository backends and their factory, then the
API layer, then tests.

---

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["T-01"]},
    {"wave": 2, "tasks": ["T-02"]},
    {"wave": 3, "tasks": ["T-03", "T-11"]},
    {"wave": 4, "tasks": ["T-04", "T-05", "T-07"]},
    {"wave": 5, "tasks": ["T-06", "T-08", "T-09"]},
    {"wave": 6, "tasks": ["T-10"]},
    {"wave": 7, "tasks": ["T-12"]},
    {"wave": 8, "tasks": ["T-13"]},
    {"wave": 9, "tasks": ["T-14"]},
    {"wave": 10, "tasks": ["T-15", "T-16", "T-17", "T-18", "T-19"]},
    {"wave": 11, "tasks": ["T-20"]},
    {"wave": 12, "tasks": ["T-21"]}
  ],
  "edges": [
    {"from": "T-01", "to": "T-02"},
    {"from": "T-02", "to": "T-03"},
    {"from": "T-02", "to": "T-11"},
    {"from": "T-03", "to": "T-04"},
    {"from": "T-03", "to": "T-05"},
    {"from": "T-03", "to": "T-07"},
    {"from": "T-04", "to": "T-06"},
    {"from": "T-05", "to": "T-06"},
    {"from": "T-07", "to": "T-06"},
    {"from": "T-07", "to": "T-08"},
    {"from": "T-07", "to": "T-09"},
    {"from": "T-08", "to": "T-10"},
    {"from": "T-09", "to": "T-10"},
    {"from": "T-06", "to": "T-12"},
    {"from": "T-10", "to": "T-12"},
    {"from": "T-11", "to": "T-12"},
    {"from": "T-12", "to": "T-13"},
    {"from": "T-13", "to": "T-14"},
    {"from": "T-06", "to": "T-15"},
    {"from": "T-04", "to": "T-16"},
    {"from": "T-05", "to": "T-17"},
    {"from": "T-10", "to": "T-18"},
    {"from": "T-14", "to": "T-19"},
    {"from": "T-14", "to": "T-20"},
    {"from": "T-15", "to": "T-21"},
    {"from": "T-16", "to": "T-21"},
    {"from": "T-17", "to": "T-21"},
    {"from": "T-18", "to": "T-21"},
    {"from": "T-19", "to": "T-21"},
    {"from": "T-20", "to": "T-21"}
  ]
}
```

---

## Tasks

- [ ] 1. Project scaffold — directory structure and dependencies
  - Create directories: `app/api/`, `app/domain/`, `app/clients/`, `app/repository/`, `tests/unit/`, `tests/integration/` under `services/registration-service/`
  - Add `__init__.py` to every Python package directory (`app/`, `app/api/`, `app/domain/`, `app/clients/`, `app/repository/`, `tests/`, `tests/unit/`, `tests/integration/`)
  - Write `services/registration-service/requirements.txt` with pinned versions: `flask==3.1.1`, `requests==2.32.3`, `pytest==8.3.5`, `pytest-cov==6.1.0`, `responses==0.25.7`
  - Add `pytest.ini` inside `services/registration-service/` registering the custom marker `req`
  - _Requirements: REQ-REG-F06, REQ-REG-F07_

- [ ] 2. Configuration module (`app/config.py`)
  - Read `PORT` with `int(os.environ["PORT"])`; raise a descriptive error if absent or out of the 1–65535 range
  - `USER_SERVICE_URL` defaults to `"http://localhost:5001"`; `EVENT_SERVICE_URL` defaults to `"http://localhost:5002"`; `STORAGE_BACKEND` defaults to `"memory"`; `DATA_DIR` defaults to `"./data"`; each treated as absent (and its default applied) when unset or set to an empty string
  - Expose a fixed `DEPENDENCY_TIMEOUT = 2` (seconds) constant, never configurable via environment
  - No other module in `app/` may call `os.environ` directly
  - _Requirements: REQ-REG-F07_

- [ ] 3. Domain model (`app/domain/models.py`)
  - Implement `Registration` as a `@dataclass` with fields: `id`, `user_id`, `event_id`, `amount` (`Decimal`), `status`, `created_at`, `updated_at`
  - `Registration.create(user_id, event_id, amount)` generates UUID v4 `id`, sets `created_at`/`updated_at` to the current UTC timestamp, sets `status = "confirmed"`
  - `registration.to_dict()` serializes `amount` as a number with exactly 2 decimals and timestamps as ISO 8601 UTC strings ending in `Z`
  - `Registration.from_dict(d)` reconstructs a `Registration` from a stored dict
  - No imports from Flask, `repository/`, or `clients/`
  - _Requirements: REQ-REG-01, REQ-REG-B06_

- [ ] 4. `UserClient` (`app/clients/user_client.py`)
  - `UserClient.__init__(self, base_url, timeout=2.0)`
  - `get_user(user_id)` calls `GET {base_url}/api/v1/users/{user_id}` with the configured timeout
  - Translate outcomes: `requests.Timeout`/`requests.ConnectionError` → raise `DependencyUnavailable("user-service")`; HTTP 404 → raise `ReferenceNotFound("user_id", user_id)`; HTTP 500–599 → raise `DependencyUnavailable("user-service")`; otherwise return the parsed JSON user dict
  - This is the only module allowed to call `requests` for reaching `user-service`
  - _Requirements: REQ-REG-B01, REQ-REG-B09, REQ-REG-F07_

- [ ] 5. `EventClient` (`app/clients/event_client.py`)
  - `EventClient.__init__(self, base_url, timeout=2.0)`
  - `get_event(event_id)` calls `GET {base_url}/api/v1/events/{event_id}` with the configured timeout, returning a dict that is reused by the caller for the published-status check, the `amount`/`price` copy, the capacity check, and the `/stats` computation (a single HTTP call per request, never repeated)
  - Translate outcomes: `requests.Timeout`/`requests.ConnectionError` → raise `DependencyUnavailable("event-service")`; HTTP 404 → raise `ReferenceNotFound("event_id", event_id)`; HTTP 500–599 → raise `DependencyUnavailable("event-service")`; HTTP 2xx whose body lacks a valid numeric `capacity` field → raise `DependencyUnavailable("event-service")` (REQ-REG-07 AC4); otherwise return the parsed JSON event dict
  - This is the only module allowed to call `requests` for reaching `event-service`
  - _Requirements: REQ-REG-B02, REQ-REG-B09, REQ-REG-07, REQ-REG-F07_

- [ ] 6. Domain exceptions and `RegistrationService` (`app/domain/registration_service.py`)
  - Define exceptions: `MalformedJson`, `ValidationError(field, message)`, `ReferenceNotFound(field, value)`, `EventNotOpen(event_id, status)`, `AlreadyRegistered(user_id, event_id)`, `EventFull(event_id)`, `InvalidStatusTransition(current, requested)`, `DependencyUnavailable(service_name)`, `NotFound`
  - `RegistrationService.__init__(self, repository, user_client, event_client)` stores all three injected dependencies, plus a per-event lock registry (`_event_locks: dict[str, threading.Lock]`, guarded by `_locks_guard`) for the capacity check below
  - `create_registration(raw_body)`: parse the JSON body (empty/invalid body → `MalformedJson`), validate `user_id`/`event_id` format aggregating every field violation into one `ValidationError` (never stopping at the first failure), then evaluate — strictly in this order, stopping at the first failure, per REQ-REG-01 AC7 — `user_client.get_user` (B01), `event_client.get_event` + published check (B02, B03), duplicate-confirmed check via `repository.has_confirmed_for` (B04), and finally, inside the per-`event_id` lock, `repository.count_confirmed_by_event` vs `event["capacity"]` (B05) before creating and persisting the `Registration` with `amount = event["price"]` (B06)
  - `_capacity_lock(event_id)`: lazily creates/returns the `threading.Lock` for that `event_id` from `_event_locks`, so concurrent capacity checks on different events never block each other while concurrent requests for the same event are fully serialized
  - `get_registration(id)`: return the registration or raise `NotFound` (including when `id` is not a valid UUID v4)
  - `list_registrations(page, page_size, user_id, event_id, status)`: validate pagination and filter parameters, filter by `user_id`/`event_id`/`status` combined with AND, sort by `created_at` ascending, then paginate
  - `patch_registration(id, data)`: raise `NotFound` if absent; validate that `status` is present, is the only field, and is a member of `{confirmed, cancelled}` (REQ-REG-F01) before applying the transition rule (`confirmed → cancelled` only; same-value and `cancelled → confirmed` both raise `InvalidStatusTransition`, REQ-REG-B07)
  - `delete_registration(id)`: raise `NotFound` if absent; otherwise permanently remove the record, freeing the seat if it was `confirmed`
  - `get_stats(event_id)`: validate `event_id` format; call `event_client.get_event`, mapping its `ReferenceNotFound` to a 404 `NotFound` for this endpoint (REQ-REG-07 AC3, distinct from the 422 mapping used during creation); compute `confirmed = repository.count_confirmed_by_event(event_id)` and `available = max(capacity - confirmed, 0)`
  - No Flask imports; no `os.environ` calls; no direct `requests` calls (always through `user_client`/`event_client`)
  - _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-05, REQ-REG-07, REQ-REG-F01, REQ-REG-F02, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 7. Repository interface and `MemoryRegistrationRepository`
  - `app/repository/base.py`: define ABC `RegistrationRepository` with methods `save(registration)`, `find_by_id(id) -> Registration | None`, `list(user_id, event_id, status) -> list[Registration]`, `delete(id) -> bool`, `count_confirmed_by_event(event_id) -> int`, `has_confirmed_for(user_id, event_id) -> bool`
  - `app/repository/memory.py`: implement `MemoryRegistrationRepository` using `dict[str, Registration]`
  - `list` applies the `user_id`/`event_id`/`status` filters (AND) and returns results ordered by `created_at` ascending (REQ-REG-03 AC15), directly inside the repository implementation
  - `delete` returns `False` if id absent, `True` otherwise
  - No file I/O or `sqlite3` imports
  - _Requirements: REQ-REG-F06, REQ-REG-03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B08_

- [ ] 8. `JsonRegistrationRepository` (`app/repository/json_repo.py`)
  - Accept `data_dir: str`; create the directory if absent
  - Data file: `{data_dir}/registrations.json` with structure `{"registrations": [...]}`
  - Every write reads, mutates, and rewrites the full file; missing file treated as an empty collection (REQ-REG-F06 AC7)
  - `amount` stored as a decimal string to avoid float rounding; only standard-library `json` module used; same filter/ordering semantics as `MemoryRegistrationRepository`
  - _Requirements: REQ-REG-F06_

- [ ] 9. `SqliteRegistrationRepository` (`app/repository/sqlite_repo.py`)
  - Accept `data_dir: str`; create the directory if absent; db path `{data_dir}/registrations.db`
  - `_init_db()` runs `CREATE TABLE IF NOT EXISTS registrations (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, event_id TEXT NOT NULL, amount TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)` plus `idx_registrations_event(event_id, status)` and `idx_registrations_user_event(user_id, event_id)` indexes
  - `price`/`amount` stored and read back as `TEXT` (decimal string) to avoid float rounding
  - `count_confirmed_by_event` and `has_confirmed_for` implemented as indexed `SELECT COUNT(*)` queries; `list` builds its `WHERE` clause dynamically from the provided filters and orders by `created_at`
  - `save_if_capacity_available(event_id, capacity, registration)` performs the count-then-insert of task 6's capacity check inside a single `BEGIN IMMEDIATE` … `COMMIT` transaction, as the durable backstop to the in-process lock if the service were ever run with multiple processes sharing the same file
  - Only standard-library `sqlite3`; no ORM
  - _Requirements: REQ-REG-F06, REQ-REG-B05_

- [ ] 10. Repository factory (`app/repository/__init__.py`)
  - Expose `get_repository(backend: str, data_dir: str) -> RegistrationRepository`
  - Return `JsonRegistrationRepository` for `"json"`, `SqliteRegistrationRepository` for `"sqlite"`, `MemoryRegistrationRepository` for `"memory"` or when unset
  - Raise a clear startup error identifying the invalid value when `backend` is anything else
  - This is the single backend-selection point in the codebase
  - _Requirements: REQ-REG-F06_

- [ ] 11. Error helper (`app/api/errors.py`)
  - `error_response(code, message, status, details=None) -> Response` returns a Flask `Response` with `Content-Type: application/json` and body `{"error": {"code": ..., "message": ..., "details": ...}}`
  - This is the only place in the service that constructs error response bodies
  - _Requirements: REQ-REG-F05_

- [ ] 12. Flask application and health check (`app/__main__.py`)
  - Import `PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR` from `app.config`
  - Call `get_repository(STORAGE_BACKEND, DATA_DIR)`, instantiate `UserClient(USER_SERVICE_URL)` and `EventClient(EVENT_SERVICE_URL)`, instantiate `RegistrationService(repo, user_client, event_client)`, create the Flask app, register the Blueprint, call `app.run(host="0.0.0.0", port=PORT)`
  - `GET /health` (and `HEAD /health`) returns 200 `{"status": "ok", "service": "registration-service"}` without invoking `user-service` or `event-service`, regardless of `STORAGE_BACKEND` or their reachability; any other method on `/health` returns 405 with an `Allow` header (REQ-REG-F04)
  - Running without `PORT` prints a clear error and exits non-zero
  - _Requirements: REQ-REG-F04, REQ-REG-F07_

- [ ] 13. POST, GET list, and GET stats endpoints (`app/api/registrations.py`)
  - Register `/api/v1/registrations/stats` **before** the parametric `/api/v1/registrations/<id>` route so it is never shadowed
  - `POST /api/v1/registrations`: parse JSON body first (400 `MALFORMED_JSON` on invalid/empty body, evaluated before field validation); on success call `create_registration`, 201 + `Location` header pointing to `/api/v1/registrations/{id}`; map `ValidationError` → 422 `VALIDATION_ERROR`, `ReferenceNotFound` → 422 `REFERENCE_NOT_FOUND`, `EventNotOpen` → 422 `EVENT_NOT_OPEN`, `AlreadyRegistered` → 409 `ALREADY_REGISTERED`, `EventFull` → 409 `EVENT_FULL`, `DependencyUnavailable` → 503 `DEPENDENCY_UNAVAILABLE`
  - `GET /api/v1/registrations`: read `page` (default 1), `page_size` (default 20), `user_id`, `event_id`, `status` from the query string; 200 `RegistrationPage` on success; 422 `VALIDATION_ERROR` on invalid pagination or an invalid filter value
  - `GET /api/v1/registrations/stats`: read the required `event_id` query parameter; 200 `RegistrationStats` on success; 422 `VALIDATION_ERROR` if missing/not a UUID v4; 404 `NOT_FOUND` if the event does not exist on `event-service`; 503 `DEPENDENCY_UNAVAILABLE` on dependency failure; 405 for non-GET methods on this path
  - _Requirements: REQ-REG-01, REQ-REG-03, REQ-REG-07, REQ-REG-F01, REQ-REG-F02, REQ-REG-F03, REQ-REG-F05, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B08, REQ-REG-B09_

- [ ] 14. GET by id, PUT (405), PATCH, DELETE endpoints (`app/api/registrations.py`)
  - `GET /api/v1/registrations/<id>`: 200 on success; 404 `NOT_FOUND` if absent or `id` is not a valid UUID v4
  - `PUT /api/v1/registrations/<id>`: always responds 405 with an `Allow` header listing `GET, PATCH, DELETE`, using the standard error body format, and never calls `RegistrationService` (REQ-REG-06)
  - `PATCH /api/v1/registrations/<id>`: 200 updated `Registration`; 400 `MALFORMED_JSON`; 404 `NOT_FOUND`; 422 `VALIDATION_ERROR`/`INVALID_STATUS_TRANSITION`
  - `DELETE /api/v1/registrations/<id>`: 204 empty body on success; 404 `NOT_FOUND` if absent or not a valid UUID
  - Register a 405 handler (with `Allow` header) for any other method not defined on the collection or item path (e.g. PUT/DELETE/PATCH on the collection, POST/PUT on the item path)
  - _Requirements: REQ-REG-02, REQ-REG-04, REQ-REG-05, REQ-REG-06, REQ-REG-F02, REQ-REG-F03, REQ-REG-F05, REQ-REG-B07_

- [ ] 15. Unit tests — domain logic (`tests/unit/test_domain.py`)
  - All tests use `MemoryRegistrationRepository` and hand-written stub/fake `UserClient`/`EventClient`; no Flask, no HTTP
  - Mark each test with `@pytest.mark.req("REQ-REG-XX")`
  - Cover: valid creation with user existing, event `published`, capacity available → `confirmed`, `amount` equal to the stubbed event `price` (REQ-REG-01, REQ-REG-B06); missing user (stub raising `ReferenceNotFound`) → REQ-REG-B01; missing event → REQ-REG-B02; event `draft`/`cancelled` → `EventNotOpen` (REQ-REG-B03); pagination offset/slice correctness after sorting by `created_at`, and `page_size > 100` → `ValidationError` (REQ-REG-03); combined `user_id`/`event_id`/`status` filters in AND (REQ-REG-03); PATCH `confirmed → cancelled` accepted (REQ-REG-B07 AC1); PATCH unknown/read-only field → `ValidationError` (REQ-REG-F02); `delete_registration` then a second call → `NotFound`, and deleting a `confirmed` registration frees a seat for a subsequent creation (REQ-REG-05, REQ-REG-B05 AC3); `get_stats` correctness for a plain, non-generated example (REQ-REG-07, REQ-REG-B08); an explicit test asserting the REQ-REG-01 AC7 evaluation order (e.g. a request that simultaneously fails validation and B01 yields the validation error, never the B01 error)
  - **Property test**: using `hypothesis`, for capacities `C` generated in [1, 20] and a number of concurrent requests generated in `[C, C+10]`, launched on multiple threads against the same `MemoryRegistrationRepository` with an `EventClient` stub fixed at capacity `C`, assert the final number of `confirmed` registrations equals `min(requests, C)` and every excess request raises `EventFull`; minimum 100 iterations — **Property 1: la capienza dell'evento non viene mai superata, anche in concorrenza**, `@pytest.mark.req("REQ-REG-B05")`
  - **Property test**: `@pytest.mark.parametrize` over the exhaustive 2×2 cartesian product of `(previous_status_for_pair, request_outcome)` where `previous_status_for_pair` ranges over `{none, confirmed, cancelled}`, asserting a new registration for the same `(user_id, event_id)` pair is rejected with `AlreadyRegistered` if and only if a `confirmed` registration for that pair already exists, and is accepted as a distinct record when the prior registration for that pair is `cancelled` or absent — **Property 2: divieto di doppia iscrizione confermata**, `@pytest.mark.req("REQ-REG-B04")`
  - **Property test**: using `hypothesis`, for event prices generated in [0.00, 9999.99] (2 decimals) and generated sequences of reads/status updates performed after creation (including changing the `price` the `EventClient` stub would return for later calls), assert `amount` observed on every read stays identical to the `price` captured at creation time; minimum 100 iterations — **Property 3: amount è immutabile e coerente con il prezzo dell'evento al momento dell'iscrizione**, `@pytest.mark.req("REQ-REG-B06")`
  - **Property test**: `@pytest.mark.parametrize` over the exhaustive 2×2 cartesian product of `(current, requested)` pairs from `{confirmed, cancelled}`, asserting the transition is accepted if and only if `(current, requested) == ("confirmed", "cancelled")` — **Property 4: le transizioni di stato seguono solo confirmed→cancelled e cancelled è terminale**, `@pytest.mark.req("REQ-REG-B07")`
  - **Property test**: using `hypothesis`, for capacities and numbers of `confirmed`/`cancelled` registrations generated randomly, assert `available == max(capacity - confirmed, 0)` and `available` is never negative; minimum 100 iterations — **Property 5: le statistiche sono sempre coerenti con confirmed e capacity**, `@pytest.mark.req("REQ-REG-B08")`
  - **Property test**: stub `UserClient`/`EventClient` raising `DependencyUnavailable` during `create_registration` and `get_stats`, asserting HTTP-mappable 503 semantics and that the repository state is unchanged before and after each failing call — **Property 6: dipendenze irraggiungibili producono sempre 503 senza effetti collaterali**, `@pytest.mark.req("REQ-REG-B09")`
  - _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-05, REQ-REG-07, REQ-REG-F01, REQ-REG-F02, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 16. Unit tests — `UserClient` (`tests/unit/test_user_client.py`)
  - Mock outbound HTTP with `responses`; no `user-service` instance is started
  - Cover: HTTP 200 → user dict returned; HTTP 404 → `ReferenceNotFound`; simulated timeout → `DependencyUnavailable`; simulated `ConnectionError` → `DependencyUnavailable`; HTTP 500/502/503 → `DependencyUnavailable`
  - _Requirements: REQ-REG-B01, REQ-REG-B09, REQ-REG-F07_

- [ ] 17. Unit tests — `EventClient` (`tests/unit/test_event_client.py`)
  - Mock outbound HTTP with `responses`; no `event-service` instance is started
  - Cover: HTTP 200 with a numeric `capacity` → event dict returned; HTTP 200 without a valid numeric `capacity` → `DependencyUnavailable` (REQ-REG-07 AC4); HTTP 404 → `ReferenceNotFound`; simulated timeout / `ConnectionError` / HTTP 5xx → `DependencyUnavailable`
  - _Requirements: REQ-REG-B02, REQ-REG-B09, REQ-REG-07, REQ-REG-F07_

- [ ] 18. Unit tests — repository backends (`tests/unit/test_repository.py`)
  - Parametrize over all three backends using a fixture with `tmp_path`
  - Per backend: `save` + `find_by_id` round-trip; `list` with no filters and with `user_id`/`event_id`/`status` filters (individually and combined); `count_confirmed_by_event`; `has_confirmed_for`; `delete` returns `True`/`False`
  - **Property test**: apply the same fixed, manually constructed sequence of CRUD operations (e.g. save 3 registrations with distinct `user_id`/`event_id`/`status`, list filtered by `event_id`, list filtered by `status`, `count_confirmed_by_event` for one event, delete one registration, `find_by_id` on the deleted one) to all three backends in turn, parametrized over 2 distinct fixed sequences, and assert identical observable results across backends — **Property 7: intercambiabilità dei backend**, `@pytest.mark.req("REQ-REG-F06")`
  - _Requirements: REQ-REG-F06, REQ-REG-03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B08_

- [ ] 19. Unit tests — API routes with contract validation (`tests/unit/test_api_registrations.py`)
  - Use `app.test_client()` with `STORAGE_BACKEND=memory`; mock `user-service`/`event-service` calls with `responses`
  - Call `assert_matches_contract` from `contracts/validator.py` on at least one response per endpoint (success and at least one error case), including `GET /api/v1/registrations/stats` and `PUT /api/v1/registrations/{id}`
  - Cover: POST valid (201, `Location` header, contract); POST malformed JSON (400 `MALFORMED_JSON`); POST missing/invalid/unknown/read-only field (422 `VALIDATION_ERROR`); POST with `user-service` mocked to 404 (422 `REFERENCE_NOT_FOUND`); POST with `event-service` mocked to 404 (422 `REFERENCE_NOT_FOUND`); POST with `event-service` mocked to 200 and `status != published` (422 `EVENT_NOT_OPEN`); POST duplicate confirmed pair (409 `ALREADY_REGISTERED`); POST at capacity (409 `EVENT_FULL`); POST/`stats` with `user-service`/`event-service` mocked to timeout/5xx (503 `DEPENDENCY_UNAVAILABLE`); GET list (200, contract), with `user_id`/`event_id`/`status` filters and combinations, with `page_size=200` (422); GET by id (200, contract); GET unknown/non-UUID id (404 `NOT_FOUND`); PATCH valid transition (200, contract); PATCH invalid transition (422 `INVALID_STATUS_TRANSITION`); PATCH malformed body (400); PATCH unknown id (404); DELETE (204); DELETE then GET (404); PUT on item path (405, `Allow` header, contract error format); `GET /stats` valid (200, `RegistrationStats` contract); `GET /stats` missing/invalid `event_id` (422); `GET /stats` unknown `event_id` (404); non-GET on `/stats` (405); unsupported method on the collection path (405); `GET /health` and `HEAD /health` (200)
  - _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-05, REQ-REG-06, REQ-REG-07, REQ-REG-F01, REQ-REG-F02, REQ-REG-F03, REQ-REG-F04, REQ-REG-F05, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 20. Integration tests (`tests/integration/test_integration.py`)
  - Session-scoped `autouse` fixture: start a real `user-service` (`python -m app` in `services/user-service/`) with `PORT=19031`, `STORAGE_BACKEND=memory`; a real `event-service` (`python -m app` in `services/event-service/`) with `PORT=19032`, `STORAGE_BACKEND=memory`, `USER_SERVICE_URL=http://localhost:19031`; and `registration-service` (`python -m app` in `services/registration-service/`) with `PORT=19033`, `STORAGE_BACKEND=memory`, `USER_SERVICE_URL=http://localhost:19031`, `EVENT_SERVICE_URL=http://localhost:19032`; poll all three `/health` endpoints up to 10 s; terminate all three in teardown
  - **Positive case**: create a real user on `user-service`, a real organizer and a `published` event with capacity ≥ 1 on `event-service`, then create a registration referencing that `user_id`/`event_id` on `registration-service` → 201, `amount` consistent with the event's `price`, subsequently readable via `GET /api/v1/registrations/{id}` and reflected in `GET /api/v1/registrations/stats` (REQ-REG-01, REQ-REG-B01, REQ-REG-B02, REQ-REG-B06, REQ-REG-B08)
  - **`REFERENCE_NOT_FOUND` case**: create a registration with a syntactically valid but non-existent `event_id` (random UUID v4) → 422 `REFERENCE_NOT_FOUND` (REQ-REG-B02)
  - **`DEPENDENCY_UNAVAILABLE` case**: stop the `event-service` subprocess (or point `EVENT_SERVICE_URL` at an unused port for that test) and attempt to create a registration → 503 `DEPENDENCY_UNAVAILABLE` (REQ-REG-B09)
  - _Requirements: REQ-REG-01, REQ-REG-B01, REQ-REG-B02, REQ-REG-B06, REQ-REG-B08, REQ-REG-B09_

- [ ] 21. Checkpoint — full test suite and coverage verification
  - Run `pytest services/registration-service/tests/unit --cov=app` and confirm every unit test (including all property tests) passes and line coverage on `app/` is ≥ 80%
  - Run `pytest services/registration-service/tests/integration` and confirm all three integration scenarios pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks 1–14 are implementation tasks; commit each as `feat(registration-service): <description> [T-NN]`.
- Tasks 15–20 are test tasks; commit each as `test(registration-service): <description> [T-NN]`.
- Task 21 is a verification checkpoint; no application or test code is added, only test execution and coverage confirmation.
- Integration tests (task 20) require dependencies installed for all three services: `pip install -r services/user-service/requirements.txt`, `pip install -r services/event-service/requirements.txt`, `pip install -r services/registration-service/requirements.txt`.
- `DATA_DIR` output (`json`/`sqlite` backends) is excluded from git via `services/*/data/` in the root `.gitignore`.
