# Requirements — user-service

**Servizio:** `user-service`  
**Base path:** `/api/v1/users`  
**Porta di sviluppo:** 5001  
**Tipo:** obbligatorio  
**Contratto OpenAPI:** `contracts/openapi/user-service.yaml`

---

## Contesto

Il `user-service` è l'anagrafica centrale della piattaforma TechConf. Gestisce la
creazione, lettura, modifica e cancellazione degli utenti (partecipanti, speaker,
organizzatori). È chiamato da `event-service`, `registration-service` e
`notification-service` per verificare l'esistenza e il ruolo degli utenti; non chiama
nessun altro servizio.

---

## Modello dati

### Risorsa `User`

| Campo | Tipo | Obbligatorio | Vincoli |
|---|---|---|---|
| `id` | UUID v4 | read-only | generato dal server, mai accettato in input |
| `first_name` | string | Sì | 1–50 caratteri |
| `last_name` | string | Sì | 1–50 caratteri |
| `email` | string | Sì | formato email valido; univoca (case-insensitive); salvata in minuscolo |
| `company` | string | No | max 100 caratteri; nullable |
| `role` | enum | No | `attendee` \| `speaker` \| `organizer`; default `attendee` |
| `created_at` | datetime ISO 8601 UTC | read-only | generato al momento della creazione |
| `updated_at` | datetime ISO 8601 UTC | read-only | aggiornato ad ogni modifica |

---

## User story e acceptance criteria

---

### REQ-USR-01 — Creazione utente (POST /api/v1/users)

**User story:**  
As a platform client, I want to register a new user so that they can participate in
TechConf events as an attendee, speaker, or organizer.

**Acceptance criteria**

1. WHEN a POST request is received with a valid JSON body containing `first_name`,
   `last_name`, and `email` THE SYSTEM SHALL create the user, assign a server-generated
   UUID v4 as `id`, set `created_at` and `updated_at` to the current UTC timestamp,
   default `role` to `attendee` if not provided, and respond with HTTP 201.

2. WHEN a user is created successfully THE SYSTEM SHALL include a `Location` header
   pointing to `/api/v1/users/{id}` in the 201 response.

3. WHEN a POST request is received with a valid JSON body THE SYSTEM SHALL store the
   `email` field in lowercase regardless of the case provided by the client (REQ-USR-B02).

4. WHEN a POST request body is not valid JSON THE SYSTEM SHALL respond with HTTP 400
   and an error body with code `MALFORMED_JSON`.

5. WHEN a POST request is received and `first_name` is absent or empty THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

6. WHEN a POST request is received and `last_name` is absent or empty THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

7. WHEN a POST request is received and `email` is absent THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR`.

8. WHEN a POST request is received and `email` does not conform to a valid email format
   THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

9. WHEN a POST request is received and `first_name` exceeds 50 characters THE SYSTEM
   SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

10. WHEN a POST request is received and `last_name` exceeds 50 characters THE SYSTEM
    SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

11. WHEN a POST request is received and `company` is provided and exceeds 100 characters
    THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

12. WHEN a POST request is received and `role` is provided with a value outside
    `attendee`, `speaker`, `organizer` THE SYSTEM SHALL respond with HTTP 422 and error
    code `VALIDATION_ERROR`.

13. WHEN a POST request is received and the response body is returned THE SYSTEM SHALL
    conform to the `User` schema defined in `contracts/openapi/user-service.yaml`.

---

### REQ-USR-B01 — Email univoca (case-insensitive)

**User story:**  
As a platform administrator, I want each email address to belong to only one user so
that login and communication channels remain unambiguous.

**Acceptance criteria**

1. WHEN a POST request is received and the `email` value (compared case-insensitively)
   already belongs to an existing user THE SYSTEM SHALL respond with HTTP 409 and error
   code `EMAIL_ALREADY_EXISTS` (REQ-USR-B01).

2. WHEN a PUT request is received and the `email` value (compared case-insensitively)
   already belongs to a different existing user THE SYSTEM SHALL respond with HTTP 409
   and error code `EMAIL_ALREADY_EXISTS` (REQ-USR-B01).

3. WHEN a PATCH request is received with an `email` field and the new value (compared
   case-insensitively) already belongs to a different existing user THE SYSTEM SHALL
   respond with HTTP 409 and error code `EMAIL_ALREADY_EXISTS` (REQ-USR-B01).

4. IF a POST or PUT or PATCH request contains an `email` value that is a case variant
   of the requesting user's own current email THEN THE SYSTEM SHALL treat it as a valid
   update (no conflict) and store the new lowercase value.

---

### REQ-USR-B02 — Normalizzazione email

**User story:**  
As a platform client, I want email addresses to be stored consistently so that lookups
and comparisons always work without case sensitivity issues.

**Acceptance criteria**

1. WHEN a user is created or updated with an `email` value THE SYSTEM SHALL store and
   return `email` in lowercase, regardless of the case submitted by the client (REQ-USR-B02).

---

### REQ-USR-02 — Lettura singolo utente (GET /api/v1/users/{id})

**User story:**  
As a platform client or another service, I want to retrieve a user by their UUID so
that I can verify their existence and read their profile.

**Acceptance criteria**

1. WHEN a GET request is received for `/api/v1/users/{id}` and the user exists THE
   SYSTEM SHALL respond with HTTP 200 and the `User` object conforming to the
   `contracts/openapi/user-service.yaml` schema.

2. WHEN a GET request is received for `/api/v1/users/{id}` and no user with that `id`
   exists THE SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a GET request is received and `{id}` is not a valid UUID format THE SYSTEM SHALL
   respond with HTTP 404 and error code `NOT_FOUND`.

---

### REQ-USR-03 — Lista utenti paginata con filtri (GET /api/v1/users)

**User story:**  
As a platform client, I want to list users with optional filters so that I can find
users by role or email without fetching the full dataset.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/users` with no query parameters THE
   SYSTEM SHALL respond with HTTP 200 and a paginated response with default `page=1`
   and `page_size=20`.

2. WHEN a GET request is received with `page` and `page_size` parameters THE SYSTEM
   SHALL return the corresponding slice of users and include `page`, `page_size`, and
   `total` in the response body.

3. WHEN `page_size` exceeds 100 THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

4. WHEN `page` is less than 1 or not a positive integer THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR`.

5. WHEN a GET request includes a `role` query parameter with a valid value THE SYSTEM
   SHALL return only users whose `role` matches the filter (REQ-USR-B03).

6. WHEN a GET request includes an `email` query parameter THE SYSTEM SHALL return only
   users whose stored (lowercase) `email` matches the filter value
   case-insensitively (REQ-USR-B03).

7. WHEN both `role` and `email` query parameters are provided THE SYSTEM SHALL apply
   both filters simultaneously (REQ-USR-B03).

8. WHEN a `role` query parameter contains a value outside `attendee`, `speaker`,
   `organizer` THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

9. WHEN no users match the applied filters THE SYSTEM SHALL respond with HTTP 200 and
   an empty `items` array with `total = 0`.

10. WHEN a GET list request returns results THE SYSTEM SHALL conform to the `UserPage`
    schema defined in `contracts/openapi/user-service.yaml`.

---

### REQ-USR-04 — Sostituzione utente (PUT /api/v1/users/{id})

**User story:**  
As a platform client, I want to replace all editable fields of a user in a single
request so that the user profile is updated atomically.

**Acceptance criteria**

1. WHEN a PUT request is received for an existing user with a valid body THE SYSTEM
   SHALL replace all editable fields (`first_name`, `last_name`, `email`, `company`,
   `role`) with the provided values, update `updated_at` to the current UTC timestamp,
   and respond with HTTP 200 and the updated `User` object.

2. WHEN a PUT request is received and the `id` does not match any user THE SYSTEM SHALL
   respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a PUT request body is not valid JSON THE SYSTEM SHALL respond with HTTP 400
   and error code `MALFORMED_JSON`.

4. WHEN a PUT request is received and any required field (`first_name`, `last_name`,
   `email`) is absent or invalid THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, applying the same field-level rules as POST (length, format).

5. WHEN a PUT request is received and `role` is not provided THE SYSTEM SHALL default
   `role` to `attendee` (same default as creation).

6. WHEN a PUT request succeeds THE SYSTEM SHALL NOT modify `id` or `created_at`.

7. WHEN a PUT response is returned THE SYSTEM SHALL conform to the `User` schema in
   `contracts/openapi/user-service.yaml`.

---

### REQ-USR-05 — Aggiornamento parziale utente (PATCH /api/v1/users/{id})

**User story:**  
As a platform client, I want to update one or more fields of a user without providing
the full resource so that I can make targeted changes efficiently.

**Acceptance criteria**

1. WHEN a PATCH request is received for an existing user with a valid partial body THE
   SYSTEM SHALL update only the fields present in the request body, update `updated_at`
   to the current UTC timestamp, and respond with HTTP 200 and the updated `User` object.

2. WHEN a PATCH request is received and the `id` does not match any user THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a PATCH request body is not valid JSON THE SYSTEM SHALL respond with HTTP 400
   and error code `MALFORMED_JSON`.

4. WHEN a PATCH request is received and a provided field value violates a constraint
   (e.g. `first_name` too long, invalid email format, unknown `role`) THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

5. WHEN a PATCH request body contains no recognized fields THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR` (no no-op silent accept).

6. WHEN a PATCH request does not include a given field THE SYSTEM SHALL leave that
   field unchanged.

7. WHEN a PATCH response is returned THE SYSTEM SHALL conform to the `User` schema in
   `contracts/openapi/user-service.yaml`.

---

### REQ-USR-06 — Cancellazione utente (DELETE /api/v1/users/{id})

**User story:**  
As a platform administrator, I want to delete a user so that inactive or erroneous
accounts can be removed from the system.

**Acceptance criteria**

1. WHEN a DELETE request is received for an existing user THE SYSTEM SHALL permanently
   remove the user and respond with HTTP 204 and no response body.

2. WHEN a DELETE request is received and the `id` does not match any user THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a DELETE succeeds and a subsequent GET for the same `id` is made THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

---

### REQ-USR-B03 — Filtri lista per `role` ed `email`

**User story:**  
As a service that depends on user-service (e.g. event-service), I want to query users
by role or email so that I can verify organizer identity or find a specific account
without scanning the entire list.

**Acceptance criteria**

1. WHEN the `role` filter is applied THE SYSTEM SHALL return only users whose `role`
   field exactly matches the given value (REQ-USR-B03).

2. WHEN the `email` filter is applied THE SYSTEM SHALL perform a case-insensitive exact
   match against the stored (lowercase) email (REQ-USR-B03).

3. WHEN both filters are applied simultaneously THE SYSTEM SHALL return only users
   satisfying both conditions (REQ-USR-B03).

---

### REQ-USR-07 — Health check (GET /health)

**User story:**  
As an orchestrator or dependent service, I want a lightweight endpoint to verify that
user-service is alive so that startup probes and resilience tests can operate correctly.

**Acceptance criteria**

1. WHEN a GET request is received on `/health` THE SYSTEM SHALL respond with HTTP 200
   and body `{"status": "ok", "service": "user-service"}` regardless of storage state.

2. WHEN the health check response is returned THE SYSTEM SHALL conform to the `Health`
   schema defined in `contracts/openapi/user-service.yaml`.

---

### REQ-USR-08 — Persistenza multi-backend

**User story:**  
As a deployment operator, I want to switch the storage backend via an environment
variable so that the service can run in-memory for tests, on JSON for lightweight
deployments, and on SQLite for durability, without changing any business logic.

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` (or the variable is absent) THE SYSTEM SHALL keep all
   user data in in-process Python structures; data is lost on restart.

2. WHEN `STORAGE_BACKEND=json` THE SYSTEM SHALL persist user data as a JSON file in
   the directory specified by `DATA_DIR` (default `./data`).

3. WHEN `STORAGE_BACKEND=sqlite` THE SYSTEM SHALL persist user data in a SQLite
   database file in the directory specified by `DATA_DIR` (default `./data`); only the
   standard `sqlite3` library is used.

4. IF the backend is switched from `memory` to `json` or `sqlite` THEN THE SYSTEM SHALL
   apply the same create/read/update/delete behaviour without any modification to
   domain or API logic.

5. WHEN `DATA_DIR` does not exist THE SYSTEM SHALL create it on first write.

---

### REQ-USR-09 — Configurazione via variabili d'ambiente

**User story:**  
As a deployment operator, I want all runtime configuration to be read from environment
variables at startup so that no value is hardcoded and the service is portable across
environments.

**Acceptance criteria**

1. WHEN the service starts THE SYSTEM SHALL read `PORT` from the environment and listen
   on that port; `PORT` is never hardcoded.

2. WHEN the service starts THE SYSTEM SHALL read `STORAGE_BACKEND` (default `memory`)
   and `DATA_DIR` (default `./data`) from the environment once and apply them for the
   entire lifetime of the process.

3. WHEN `PORT` is not set THE SYSTEM SHALL fail to start with a clear error message.

---

### REQ-USR-10 — Formato delle risposte di errore

**User story:**  
As a platform client, I want all error responses to follow a consistent structure so
that I can handle them programmatically without special-casing each endpoint.

**Acceptance criteria**

1. WHEN any error response is returned THE SYSTEM SHALL use the body structure
   `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`.

2. WHEN a 400 response is returned THE SYSTEM SHALL set `code` to `MALFORMED_JSON`.

3. WHEN a 404 response is returned THE SYSTEM SHALL set `code` to `NOT_FOUND`.

4. WHEN a 409 response is returned for a duplicate email THE SYSTEM SHALL set `code` to
   `EMAIL_ALREADY_EXISTS`.

5. WHEN a 422 response is returned for field validation THE SYSTEM SHALL set `code` to
   `VALIDATION_ERROR`.

6. WHEN any error response is returned THE SYSTEM SHALL conform to the `Error` schema
   in `contracts/openapi/user-service.yaml`.

---

## Riepilogo requisiti e copertura endpoint

| Requisito | Endpoint coinvolto | Tipo |
|---|---|---|
| REQ-USR-01 | POST /api/v1/users | Funzionale |
| REQ-USR-B01 | POST, PUT, PATCH /api/v1/users / {id} | Business rule |
| REQ-USR-B02 | POST, PUT, PATCH /api/v1/users / {id} | Business rule |
| REQ-USR-02 | GET /api/v1/users/{id} | Funzionale |
| REQ-USR-03 | GET /api/v1/users | Funzionale |
| REQ-USR-B03 | GET /api/v1/users | Business rule |
| REQ-USR-04 | PUT /api/v1/users/{id} | Funzionale |
| REQ-USR-05 | PATCH /api/v1/users/{id} | Funzionale |
| REQ-USR-06 | DELETE /api/v1/users/{id} | Funzionale |
| REQ-USR-07 | GET /health | Non-funzionale |
| REQ-USR-08 | tutti | Non-funzionale (persistenza) |
| REQ-USR-09 | tutti | Non-funzionale (configurazione) |
| REQ-USR-10 | tutti | Non-funzionale (errori) |
