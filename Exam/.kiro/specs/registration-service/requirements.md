# Requirements Document

**Servizio:** `registration-service`
**Base path:** `/api/v1/registrations`
**Porta di sviluppo:** 5003
**Tipo:** obbligatorio
**Contratto OpenAPI:** `contracts/openapi/registration-service.yaml` (fonte di verità dell'interfaccia)

---

## Introduction

Il `registration-service` gestisce le iscrizioni degli utenti agli eventi della
piattaforma TechConf: crea, legge, filtra, aggiorna lo stato e cancella le iscrizioni,
applicando le regole di capienza e di stato dell'evento. Ogni iscrizione collega un
`user_id` a un `event_id`: prima di accettarla, il servizio verifica via HTTP presso
`user-service` che l'utente esista e presso `event-service` che l'evento esista e sia
`published`, leggendo da `event-service` anche il prezzo (`amount`) e la capienza
(`capacity`) necessari alle proprie regole di business. Il `registration-service`
dipende da `user-service` ed `event-service` e non accede mai direttamente ai loro dati;
ogni verifica avviene con una chiamata HTTP al servizio competente.

---

## Glossary

- **SYSTEM / registration-service**: il microservizio descritto in questo documento, in
  ascolto sulla porta indicata dalla variabile d'ambiente `PORT`.
- **user-service**: microservizio dell'anagrafica utenti, raggiungibile all'URL indicato
  dalla variabile d'ambiente `USER_SERVICE_URL` (default `http://localhost:5001`).
- **event-service**: microservizio degli eventi, raggiungibile all'URL indicato dalla
  variabile d'ambiente `EVENT_SERVICE_URL` (default `http://localhost:5002`).
- **Registration**: la risorsa iscrizione gestita dal `registration-service`, che collega
  un `user_id` a un `event_id`.
- **confirmed registration**: una `Registration` il cui campo `status` vale `confirmed`;
  occupa un posto della capienza dell'evento associato.
- **cancelled registration**: una `Registration` il cui campo `status` vale `cancelled`;
  non occupa alcun posto della capienza dell'evento associato.
- **caller / platform client**: qualunque client HTTP (utente umano tramite tool, altro
  servizio, suite di test) che invoca gli endpoint del `registration-service`.
- **EUR**: valuta implicita del campo `amount`, espresso con 2 decimali.

---

## Modello dati

### Risorsa `Registration`

| Campo | Tipo | Obbligatorio in input | Vincoli |
|---|---|---|---|
| `id` | UUID v4 | read-only | generato dal server, mai accettato in input |
| `user_id` | UUID | Sì (in POST) | deve esistere in `user-service` |
| `event_id` | UUID | Sì (in POST) | deve esistere in `event-service` con `status = published` |
| `amount` | decimal | read-only | copiato da `event.price` al momento della creazione, mai accettato dal client, 2 decimali, valuta implicita EUR |
| `status` | enum | read-only in POST | `confirmed` \| `cancelled`; alla creazione sempre `confirmed`; modificabile solo via PATCH |
| `created_at` | datetime ISO 8601 UTC | read-only | generato al momento della creazione |
| `updated_at` | datetime ISO 8601 UTC | read-only | aggiornato ad ogni modifica |

> I campi `id`, `amount`, `created_at`, `updated_at` non sono mai accettati in input, in
> nessun endpoint. Il campo `status` non è accettato in input in POST (è sempre
> `confirmed`) ed è l'unico campo accettato in input in PATCH. Gli schemi
> `RegistrationCreate`, `RegistrationPatch` e `Registration` del contratto OpenAPI hanno
> `additionalProperties: false`: qualunque campo sconosciuto in input deve essere
> rifiutato (vedi REQ-REG-F02).

---

## Requirements

Le seguenti sottosezioni raccolgono le user story e gli acceptance criteria di ogni
requisito del `registration-service`.

---

### REQ-REG-01 — Creazione iscrizione (POST /api/v1/registrations)

**User story:**
As a platform client, I want to register a user to a published event so that the user
secures a seat and is charged the event's price.

**Acceptance criteria**

1. WHEN a POST request is received on `/api/v1/registrations` with a well-formed JSON
   body containing `user_id` and `event_id`, each a string in canonical UUID v4 format,
   and the business rules REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, and
   REQ-REG-B05 are each satisfied when evaluated in that order, THE SYSTEM SHALL create
   the registration, assign a server-generated UUID v4 as `id`, set `amount` to the
   current `price` of the referenced event, set `status` to `confirmed`, set
   `created_at` and `updated_at` to the current UTC timestamp in ISO 8601, and respond
   with HTTP 201.

2. WHEN a registration is created successfully THE SYSTEM SHALL include a `Location`
   header pointing to `/api/v1/registrations/{id}` in the 201 response.

3. WHEN a registration is created successfully THE SYSTEM SHALL return the created
   `Registration` object conforming to the `Registration` schema defined in
   `contracts/openapi/registration-service.yaml`.

4. IF a POST request body is not well-formed JSON, THEN THE SYSTEM SHALL respond with
   HTTP 400 and no registration SHALL be created.

5. IF a POST request omits `user_id`, omits `event_id`, or provides either as a value
   that is not a string in canonical UUID v4 format, THEN THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR`, and no registration SHALL be created.

6. IF a POST request body includes an unknown field or any server-generated field
   (`id`, `amount`, `status`, `created_at`, `updated_at`), THEN THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR`, and no registration SHALL be
   created (REQ-REG-F02).

7. IF a POST request would violate more than one of the conditions in criteria 4, 5, 6,
   REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, or REQ-REG-B05 at the same time,
   THEN THE SYSTEM SHALL evaluate them in the following order and respond according to
   the first condition that fails, without evaluating any subsequent condition: (1)
   malformed JSON body (criterion 4), (2) field-format/unknown-field validation
   (criteria 5 and 6), (3) REQ-REG-B01, (4) REQ-REG-B02, (5) REQ-REG-B03, (6)
   REQ-REG-B04, (7) REQ-REG-B05; and no registration SHALL be created.

---

### REQ-REG-02 — Lettura singola iscrizione (GET /api/v1/registrations/{id})

**User story:**
As a platform client or another service, I want to retrieve a registration by its UUID
so that I can read its details and status.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/registrations/{id}` and a registration with that `id` exists, regardless of its current lifecycle status (`confirmed` or `cancelled`), THE SYSTEM SHALL respond with HTTP 200 and the `Registration` object conforming to the `Registration` schema in `contracts/openapi/registration-service.yaml`.

2. WHEN a GET request is received on `/api/v1/registrations/{id}` and no registration with that `id` exists THE SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a GET request is received and `{id}` does not match the canonical UUID v4 string format (32 hexadecimal digits grouped as 8-4-4-4-12, separated by hyphens, with the version and variant digits fixed per the UUID v4 specification, matched case-insensitively) — including strings that are syntactically valid UUIDs of a different version — THE SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`.

---

### REQ-REG-03 — Lista iscrizioni paginata con filtri (GET /api/v1/registrations)

**User story:**
As a platform client, I want to list registrations with optional filters and pagination
so that I can browse registrations by user, event, or status without fetching the full
dataset.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/registrations` with no query parameters
   THE SYSTEM SHALL respond with HTTP 200 and a paginated response with default
   `page=1` and `page_size=20`.

2. WHEN a GET request is received with valid `page` and `page_size` parameters THE
   SYSTEM SHALL return the corresponding slice of registrations and include `page`,
   `page_size`, and `total` in the response body.

3. IF `page_size` exceeds 100 THEN THE SYSTEM SHALL respond with HTTP 422 and error
   code `VALIDATION_ERROR`.

4. IF `page` is less than 1 or not a positive integer THEN THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR`.

5. IF `page_size` is less than 1 or not a positive integer THEN THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

6. WHEN a GET request includes a `user_id` query parameter that is a valid UUID v4 THE
   SYSTEM SHALL return only registrations whose `user_id` equals the filter value.

7. IF a GET request includes a `user_id` query parameter that is not a valid UUID v4
   THEN THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

8. WHEN a GET request includes an `event_id` query parameter that is a valid UUID v4
   THE SYSTEM SHALL return only registrations whose `event_id` equals the filter value.

9. IF a GET request includes an `event_id` query parameter that is not a valid UUID
   v4 THEN THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

10. WHEN a GET request includes a `status` query parameter with a value in `confirmed`,
    `cancelled` THE SYSTEM SHALL return only registrations whose `status` matches the
    filter.

11. IF a GET request includes a `status` query parameter with a value outside
    `confirmed`, `cancelled` THEN THE SYSTEM SHALL respond with HTTP 422 and error code
    `VALIDATION_ERROR`.

12. WHEN more than one of `user_id`, `event_id`, `status` query parameters are provided
    THE SYSTEM SHALL apply all provided filters simultaneously in AND.

13. WHEN no registrations match the applied filters THE SYSTEM SHALL respond with HTTP
    200 and an empty `items` array with `total = 0`.

14. WHEN a GET list request returns results THE SYSTEM SHALL conform to the
    `RegistrationPage` schema defined in `contracts/openapi/registration-service.yaml`.

15. THE SYSTEM SHALL order registrations returned by the list endpoint by `created_at`
    ascending before applying pagination, so that identical filter and pagination
    parameters always produce the same slice of results.

16. WHEN a `page` value greater than the total number of pages available for the
    applied filters is requested THE SYSTEM SHALL respond with HTTP 200, an empty
    `items` array, and a `total` value equal to the count of registrations matching
    the applied filters.

---

### REQ-REG-04 — Aggiornamento stato iscrizione (PATCH /api/v1/registrations/{id})

**User story:**
As a platform client, I want to cancel an existing registration so that the associated
event seat is freed for other participants.

**Acceptance criteria**

1. WHEN a PATCH request is received for an existing registration with a well-formed body
   containing only `status` and the transition is allowed (REQ-REG-B07), THE SYSTEM
   SHALL update `status`, update `updated_at` to the current UTC timestamp, and respond
   with HTTP 200 and the updated `Registration` object.

2. WHEN a PATCH request is received and the `id` does not match any existing
   registration, or `{id}` is not a valid UUID v4 format, THE SYSTEM SHALL respond with
   HTTP 404 and error code `NOT_FOUND`, and the stored registration SHALL remain
   unchanged.

3. IF a PATCH request body is not well-formed JSON, or the request body is empty, THEN
   THE SYSTEM SHALL respond with HTTP 400 and error code `MALFORMED_JSON`, and the
   stored registration SHALL remain unchanged.

4. IF a PATCH request omits `status`, provides `status` with a value outside
   `confirmed`, `cancelled`, or includes any field other than `status` (unknown field or
   server-generated field), THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, and the stored registration SHALL remain unchanged (REQ-REG-F02).

5. WHEN a PATCH response is returned THE SYSTEM SHALL conform to the `Registration`
   schema in `contracts/openapi/registration-service.yaml`.

6. IF a PATCH request submits a `status` value that violates the allowed transition
   rule defined in REQ-REG-B07 (i.e., the new value equals the current stored `status`,
   or the transition is not `confirmed`→`cancelled`), THEN THE SYSTEM SHALL respond with
   HTTP 422 and error code `INVALID_STATUS_TRANSITION`, and the stored registration
   SHALL remain unchanged.

---

### REQ-REG-05 — Cancellazione iscrizione (DELETE /api/v1/registrations/{id})

**User story:**
As a platform administrator, I want to delete a registration record so that erroneous
or test registrations can be removed from the system.

**Acceptance criteria**

1. WHEN a DELETE request is received for an existing registration, regardless of its
   current `status` (`confirmed` or `cancelled`) and without any authorization or role
   check beyond the existence of `{id}`, THE SYSTEM SHALL permanently remove the
   registration and respond with HTTP 204 and no response body.

2. WHEN a DELETE request is received and the `id` does not match any registration THE
   SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a DELETE request is received and `{id}` is not a valid UUID v4 format THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

4. WHEN a DELETE succeeds and a subsequent GET for the same `id` is made THE SYSTEM SHALL
   respond with HTTP 404 and error code `NOT_FOUND`.

5. WHEN a `confirmed` registration is deleted THE SYSTEM SHALL free the seat it occupied
   for the associated event, so that the deleted registration is excluded from
   subsequent capacity and stats calculations (REQ-REG-B05, REQ-REG-B08).

---

### REQ-REG-06 — Metodo non previsto su risorsa singola (PUT /api/v1/registrations/{id})

**User story:**
As a platform client, I want unsupported methods to be reported predictably so that I
do not mistake them for a valid operation.

**Acceptance criteria**

1. WHEN a PUT request is received on `/api/v1/registrations/{id}`, regardless of
   whether the identifier `{id}` corresponds to an existing registration, THE SYSTEM
   SHALL respond with HTTP status code 405 and SHALL NOT create, modify, or delete any
   registration.

2. WHEN a PUT request is received on `/api/v1/registrations/{id}`, THE SYSTEM SHALL
   include in the response an explicit list of the HTTP methods supported on that path,
   and SHALL structure the response body using the same error format used for the
   other error responses of the service.

---

### REQ-REG-07 — Statistiche di iscrizione per evento (GET /api/v1/registrations/stats)

**User story:**
As an organizer, I want to see how many seats are confirmed and available for an event
so that I can monitor how the event is filling up.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/registrations/stats` with a valid
   `event_id` query parameter referencing an existing event, THE SYSTEM SHALL respond
   with HTTP 200 and a body containing `event_id`, `capacity` (read from
   `event-service`), `confirmed` (the count of registrations for that event whose
   status is `confirmed`), and `available` (`capacity` minus `confirmed`, never
   negative), conforming to the `RegistrationStats` schema in
   `contracts/openapi/registration-service.yaml` (REQ-REG-B08).

2. IF the `event_id` query parameter is missing or is not a valid UUID v4, THEN THE
   SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

3. IF the `event_id` query parameter references an event that does not exist in
   `event-service`, THEN THE SYSTEM SHALL respond with HTTP 404 and error code
   `NOT_FOUND` (REQ-REG-B08).

4. IF the call to `event-service` to resolve the event's `capacity` times out after 2
   seconds, the connection is refused, `event-service` responds with a 5xx status, or
   `event-service` responds with a 2xx status whose body does not contain a valid
   numeric `capacity` field, THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE`, without creating, modifying, or deleting any registration
   data (REQ-REG-B09).

5. IF a request on `/api/v1/registrations/stats` uses an HTTP method other than GET,
   THEN THE SYSTEM SHALL respond with HTTP 405.

---

### REQ-REG-F01 — Validazione dei campi (input)

**User story:**
As a platform client, I want every registration field to be validated on creation and
update so that only well-formed registrations enter the system.

**Acceptance criteria**

1. IF a POST request omits `user_id`, or provides `user_id` that is not a string in
   canonical UUID v4 format, THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, and no registration SHALL be created.

2. IF a POST request omits `event_id`, or provides `event_id` that is not a string in
   canonical UUID v4 format, THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, and no registration SHALL be created.

3. IF a PATCH request omits `status`, or provides `status` with a value outside
   `confirmed`, `cancelled`, THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, and the stored registration SHALL remain unchanged.

4. WHILE the request body is valid JSON representing an object, IF field validation
   fails on one or more fields, THEN THE SYSTEM SHALL include in the error `details`
   object an identification of each offending field, and SHALL NOT create or modify any
   registration.

5. IF multiple field validation rules fail in a single request, THEN THE SYSTEM SHALL
   respond with a single HTTP 422 `VALIDATION_ERROR` response rather than stopping at
   the first failure only.

---

### REQ-REG-F02 — Rifiuto di campi read-only e campi sconosciuti

**User story:**
As a platform client, I want the service to reject inputs that violate the contract so
that the API stays aligned with `contracts/openapi/registration-service.yaml`.

**Acceptance criteria**

1. IF a POST request body contains one or more fields not defined in the
   `RegistrationCreate` schema (unknown fields), THEN THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR` (`additionalProperties: false`), SHALL
   identify each offending field name in the error `details`, and no registration
   SHALL be created.

2. IF a POST request body contains one or more of the server-managed fields `id`,
   `amount`, `status`, `created_at`, or `updated_at`, THEN THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR`, SHALL identify each offending
   field name in the error `details`, and no registration SHALL be created.

3. IF a PATCH request body contains one or more fields not defined in the
   `RegistrationPatch` schema (unknown fields, including `user_id`, `event_id`,
   `amount`, `id`, `created_at`, `updated_at`), THEN THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR` (`additionalProperties: false`), SHALL
   identify each offending field name in the error `details`, and the stored
   registration SHALL remain unchanged.

4. IF a POST or PATCH request body is valid JSON but is not a JSON object (e.g. array,
   string, number, boolean, or null), THEN THE SYSTEM SHALL respond with HTTP 422 and
   error code `VALIDATION_ERROR`.

5. WHEN input validation succeeds, THE SYSTEM SHALL persist and return only the fields
   defined in the `Registration` schema of `contracts/openapi/registration-service.yaml`,
   with no additional properties.

---

### REQ-REG-F03 — JSON malformato e metodi non previsti

**User story:**
As a platform client, I want consistent protocol-level errors so that malformed
requests and unsupported methods are reported predictably.

**Acceptance criteria**

1. IF a POST or PATCH request is received whose body is not syntactically valid JSON,
   or whose body is empty (zero-length), THEN THE SYSTEM SHALL respond with HTTP 400
   and error code `MALFORMED_JSON`, and SHALL NOT create or modify any registration.

2. IF a request uses an HTTP method not defined for the resource path invoked —
   including PUT, DELETE, or PATCH on the collection path `/api/v1/registrations`, and
   POST or PUT on the item path `/api/v1/registrations/{id}` — THEN THE SYSTEM SHALL
   respond with HTTP 405, SHALL identify in the response the complete set of HTTP
   methods allowed on that specific path, and SHALL NOT create, modify, or delete any
   registration.

3. THE SYSTEM SHALL evaluate malformed-JSON detection (criterion 1) before any
   field-level or business-rule validation, for every POST or PATCH request, such that
   a request satisfying criterion 1 always yields HTTP 400 and never HTTP 422,
   regardless of the values of any fields present in the body.

---

### REQ-REG-F04 — Health check (GET /health)

**User story:**
As an orchestrator or dependent service, I want a lightweight endpoint to verify that
registration-service is alive so that startup probes and resilience tests can operate
correctly.

**Acceptance criteria**

1. WHEN a GET request is received on `/health`, THE SYSTEM SHALL respond with HTTP 200
   and body `{"status": "ok", "service": "registration-service"}`, without invoking
   `user-service` or `event-service` as part of producing this response, regardless of
   the configured `STORAGE_BACKEND` value and regardless of whether `user-service` or
   `event-service` are reachable.

2. WHEN the health check response is returned, THE SYSTEM SHALL conform to the `Health`
   schema defined in `contracts/openapi/registration-service.yaml`, with no additional
   properties.

3. WHEN a request uses an HTTP method other than GET or HEAD on `/health`, THE SYSTEM
   SHALL respond with HTTP 405, SHALL include an indication of the methods allowed on
   that path, and SHALL NOT create, modify, or delete any registration or invoke
   `user-service` or `event-service`.

4. WHEN a HEAD request is received on `/health`, THE SYSTEM SHALL respond with HTTP 200
   and the same headers as for an equivalent GET request on `/health`, with an empty
   response body.

---

### REQ-REG-F05 — Formato delle risposte di errore

**User story:**
As a platform client, I want all error responses to follow a consistent structure so
that I can handle them programmatically without special-casing each endpoint.

**Acceptance criteria**

1. WHEN any error response is returned, THE SYSTEM SHALL use the body structure
   `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`, where
   `code` is always present as a non-empty string in upper snake case, `message` is
   always present as a non-empty string describing the error, and `details` is
   optional.

2. WHEN a 400 response is returned, THE SYSTEM SHALL set `code` to `MALFORMED_JSON`.

3. WHEN a 404 response is returned, THE SYSTEM SHALL set `code` to `NOT_FOUND`.

4. WHEN a 422 response is returned for field validation, THE SYSTEM SHALL set `code` to
   `VALIDATION_ERROR` and SHALL include in `details` an identification of the offending
   field(s).

5. WHEN a 422 response is returned because the referenced `user_id` does not exist, THE
   SYSTEM SHALL set `code` to `REFERENCE_NOT_FOUND` (REQ-REG-B01).

6. WHEN a 422 response is returned because the referenced `event_id` does not exist, THE
   SYSTEM SHALL set `code` to `REFERENCE_NOT_FOUND` (REQ-REG-B02).

7. WHEN a 422 response is returned because the referenced event is not `published`, THE
   SYSTEM SHALL set `code` to `EVENT_NOT_OPEN` (REQ-REG-B03).

8. WHEN a 409 response is returned because the user already has a confirmed registration
   for the event, THE SYSTEM SHALL set `code` to `ALREADY_REGISTERED` (REQ-REG-B04).

9. WHEN a 409 response is returned because the event has reached its capacity, THE
   SYSTEM SHALL set `code` to `EVENT_FULL` (REQ-REG-B05).

10. WHEN a 422 response is returned because of a disallowed status transition, THE
    SYSTEM SHALL set `code` to `INVALID_STATUS_TRANSITION` (REQ-REG-B07).

11. WHEN a 503 response is returned because a call to `user-service` or `event-service`
    timed out after 2 seconds, the connection was refused, or the called service
    responded with a status code in the 500–599 range, THE SYSTEM SHALL set `code` to
    `DEPENDENCY_UNAVAILABLE` (REQ-REG-B09).

12. WHEN any error response is returned, THE SYSTEM SHALL conform to the `Error` schema
    in `contracts/openapi/registration-service.yaml`, with no additional properties
    outside `code`, `message`, and `details`.

13. WHEN a 405 response is returned, THE SYSTEM SHALL set `code` to
    `METHOD_NOT_ALLOWED`.

---

### REQ-REG-F06 — Persistenza multi-backend

**User story:**
As a deployment operator, I want to switch the storage backend via an environment
variable so that the service can run in-memory for tests, on JSON for lightweight
deployments, and on SQLite for durability, without changing any business logic.

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` (or the variable is absent), THE SYSTEM SHALL keep all
   registration data in in-process Python structures, and all data SHALL be lost on
   process restart.

2. WHEN `STORAGE_BACKEND=json`, THE SYSTEM SHALL persist registration data as a JSON
   file in the directory specified by `DATA_DIR` (default `./data`) using only the
   standard `json` library, and previously persisted registrations SHALL be readable
   after a process restart.

3. WHEN `STORAGE_BACKEND=sqlite`, THE SYSTEM SHALL persist registration data in a SQLite
   database file in the directory specified by `DATA_DIR` (default `./data`) using only
   the standard `sqlite3` library, and previously persisted registrations SHALL be
   readable after a process restart.

4. WHEN the SYSTEM is restarted with `STORAGE_BACKEND` changed from `memory` to `json`
   or `sqlite` (or vice versa), THE SYSTEM SHALL, for the same sequence of create, read,
   update, and delete requests with the same request bodies, produce identical HTTP
   status codes and identical response bodies (aside from server-generated
   timestamps/IDs) to those produced under `STORAGE_BACKEND=memory`, without requiring
   any change to the request format or to the deployed application code.

5. WHEN a write is requested and the directory specified by `DATA_DIR` does not exist,
   THE SYSTEM SHALL create it before writing.

6. IF `STORAGE_BACKEND` is set to a value other than `memory`, `json`, or `sqlite`, THEN
   THE SYSTEM SHALL fail to start: THE SYSTEM SHALL exit without binding to the
   configured `PORT`, SHALL emit an error message identifying the invalid value, and no
   HTTP request SHALL receive any response from that process.

7. WHEN `STORAGE_BACKEND` is `json` or `sqlite` and a GET-by-`id` or list request is
   received while no data file yet exists in `DATA_DIR` for this service (i.e. no
   registration has ever been created since the directory was last empty), THE SYSTEM
   SHALL respond as if zero registrations exist: HTTP 404 with error code `NOT_FOUND`
   for a GET-by-`id` request, and HTTP 200 with an empty `items` array and `total = 0`
   for a list request, rather than responding with an error caused by the missing file.

---

### REQ-REG-F07 — Configurazione via variabili d'ambiente

**User story:**
As a deployment operator, I want all runtime configuration to be read from environment
variables at startup so that no value is hardcoded and the service is portable across
environments.

**Acceptance criteria**

1. WHEN the service starts, THE SYSTEM SHALL read `PORT` from the environment and listen
   on that port; `PORT` SHALL never be hardcoded.

2. WHEN the service starts, THE SYSTEM SHALL read `USER_SERVICE_URL` (default
   `http://localhost:5001`), `EVENT_SERVICE_URL` (default `http://localhost:5002`),
   `STORAGE_BACKEND` (default `memory`), and `DATA_DIR` (default `./data`) from the
   environment exactly once, treating each of these variables that is unset or set to
   an empty string as absent and applying its documented default value in that case,
   and SHALL apply the resulting values unchanged for the entire lifetime of the
   process.

3. WHEN a call to `user-service` or `event-service` is made, THE SYSTEM SHALL use the
   URL from `USER_SERVICE_URL` or `EVENT_SERVICE_URL` respectively and apply a 2-second
   timeout, never a hardcoded URL.

4. IF `PORT` is not set, or is set to a value that is not an integer in the range
   1–65535, THEN THE SYSTEM SHALL fail to start with an error message identifying `PORT`
   as the cause, and SHALL NOT listen on any port.

5. IF the service fails to start because of an invalid `PORT` (criterion 4 of this
   requirement) or an invalid `STORAGE_BACKEND` value (REQ-REG-F06), THEN THE SYSTEM
   SHALL terminate the process with a non-zero exit status before entering a listening
   state, and SHALL NOT accept any incoming connection on any port.

---

### REQ-REG-B01 — L'utente deve esistere

**User story:**
As a platform administrator, I want every registration to reference an existing user so
that no registration points to a non-existent account.

**Acceptance criteria**

1. WHEN a POST request is received on `/api/v1/registrations` with a `user_id` that is a
   syntactically valid UUID v4 (per REQ-REG-F01), THE SYSTEM SHALL call `GET
   /api/v1/users/{user_id}` on `user-service` at the URL given by `USER_SERVICE_URL`
   (default `http://localhost:5001`) with a 2-second timeout, before evaluating
   REQ-REG-B02 through REQ-REG-B05 and before persisting the registration (REQ-REG-B01).

2. WHEN `user-service` responds with HTTP 200 for the given `user_id`, THE SYSTEM SHALL
   treat the user as existing and proceed with evaluation of the remaining business
   rules (REQ-REG-B02 through REQ-REG-B05) for that registration (REQ-REG-B01).

3. IF `user-service` responds with HTTP 404 for the given `user_id` THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `REFERENCE_NOT_FOUND`, and no
   registration SHALL be created (REQ-REG-B01).

---

### REQ-REG-B02 — L'evento deve esistere

**User story:**
As a platform administrator, I want every registration to reference an existing event
so that no registration points to a non-existent conference.

**Acceptance criteria**

1. WHEN a POST request is received with an `event_id` that has already passed UUID v4
   format validation (REQ-REG-F01), THE SYSTEM SHALL call `GET /api/v1/events/{event_id}`
   on `event-service` at the URL given by `EVENT_SERVICE_URL` (default
   `http://localhost:5002`) with a 2-second timeout, before persisting the registration
   (REQ-REG-B02).

2. IF `event-service` responds with HTTP 404 for the given `event_id` THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `REFERENCE_NOT_FOUND`, and no
   registration SHALL be created (REQ-REG-B02).

3. WHEN `event-service` responds with HTTP 200 and a JSON body representing the event
   for the given `event_id`, THE SYSTEM SHALL treat the event as existing and proceed
   with the remaining registration checks (REQ-REG-B03), without persisting the
   registration at this step (REQ-REG-B02).

---

### REQ-REG-B03 — L'evento deve essere `published`

**User story:**
As an organizer, I want registrations to be accepted only for published events so that
users cannot register to draft or cancelled conferences.

**Acceptance criteria**

1. WHEN a POST request is received, and the user's existence (REQ-REG-B01) and the
   event's existence (REQ-REG-B02) have both been confirmed, and the referenced event's
   `status` (as returned by `event-service`) equals `published`, THE SYSTEM SHALL
   proceed with the remaining business-rule checks (REQ-REG-B04, REQ-REG-B05) for the
   registration (REQ-REG-B03).

2. IF the user's existence (REQ-REG-B01) and the event's existence (REQ-REG-B02) have
   both been confirmed, and the referenced event's `status` (as returned by
   `event-service`) is not `published` (i.e. `draft` or `cancelled`), THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `EVENT_NOT_OPEN`, and no registration
   SHALL be created, without evaluating the checks in REQ-REG-B04 or REQ-REG-B05
   (REQ-REG-B03).

---

### REQ-REG-B04 — Divieto di doppia iscrizione confermata

**User story:**
As an organizer, I want to prevent a user from holding two confirmed registrations for
the same event so that seats are not wasted on duplicate bookings.

**Acceptance criteria**

1. WHEN a POST request is received for a `user_id` and `event_id` pair, and no existing
   registration for that same `user_id` and `event_id` has `status = confirmed`, THE
   SYSTEM SHALL proceed with the remaining business-rule checks for the registration
   (REQ-REG-B04).

2. IF an existing registration for the same `user_id` and `event_id` already has
   `status = confirmed`, THEN THE SYSTEM SHALL respond with HTTP 409 and error code
   `ALREADY_REGISTERED`, and no registration SHALL be created (REQ-REG-B04).

3. WHEN a user's prior registration for an event has `status = cancelled`, THE SYSTEM
   SHALL allow that same user to create a new confirmed registration for the same event
   as a separate record with its own server-generated `id`, without modifying the prior
   cancelled registration, subject to the remaining business rules (REQ-REG-B04).

---

### REQ-REG-B05 — Capienza evento

**User story:**
As an organizer, I want registrations to stop when the event is full, so that we never
exceed the venue capacity.

**Acceptance criteria**

1. WHEN a registration is requested, all checks in REQ-REG-B01 through REQ-REG-B04 have
   already passed, AND the confirmed registrations for the event are fewer than
   `event.capacity` (as returned by `event-service` at the time of the request), THE
   registration-service SHALL create it with status `confirmed` (REQ-REG-B05).

2. IF the confirmed registrations for the event are equal to or greater than
   `event.capacity` THEN THE registration-service SHALL respond 409 with error code
   `EVENT_FULL`, and no registration SHALL be created (REQ-REG-B05).

3. WHEN a confirmed registration is cancelled THE registration-service SHALL free one
   seat, so that a subsequent registration request for the same event can succeed if the
   confirmed count is again below `event.capacity` (REQ-REG-B05).

4. THE registration-service SHALL guarantee that, regardless of how many registration
   requests for the same event are processed concurrently, the number of registrations
   with `status = confirmed` for that event never exceeds `event.capacity` at any point
   in time; at most one of two or more simultaneous requests contending for the last
   available seat SHALL succeed, and every other contending request SHALL receive the
   409 `EVENT_FULL` response defined in criterion 2 (REQ-REG-B05).

---

### REQ-REG-B06 — `amount` copiato dal prezzo dell'evento

**User story:**
As a platform client, I want the registration amount to reflect the event's price at
the time of registration so that the charged amount is accurate and consistent.

**Acceptance criteria**

1. WHEN a registration is created, THE SYSTEM SHALL set `amount` to the exact `price`
   value returned by `event-service` in the same response used to validate the
   referenced `event_id` (REQ-REG-B02), copying it verbatim without rounding or
   truncation, expressed with exactly 2 decimal places and implicit currency EUR
   (REQ-REG-B06).

2. IF a POST request body includes an `amount` field, regardless of its value, THEN THE
   SYSTEM SHALL reject the entire request with HTTP 422 and error code
   `VALIDATION_ERROR` as specified in REQ-REG-F02, and SHALL NOT create any registration
   or apply the client-supplied value (REQ-REG-B06).

3. WHEN a registration is read, listed, or returned in any response, THE SYSTEM SHALL
   return the `amount` value that was captured at creation time, unchanged by later
   modifications to the event's `price` (REQ-REG-B06).

---

### REQ-REG-B07 — Transizione di stato consentita

**User story:**
As a platform client, I want registration status changes to follow a defined rule so
that registrations cannot move into inconsistent states.

**Acceptance criteria**

1. WHEN a PATCH request changes `status` from `confirmed` to `cancelled` THE SYSTEM
   SHALL accept the transition, update the registration, and exclude it from the
   confirmed count used by the capacity check (REQ-REG-B05) and by the stats endpoint
   (REQ-REG-B08) from that point forward (REQ-REG-B07).

2. IF a PATCH request submits a `status` value equal to the registration's current
   stored `status`, THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `INVALID_STATUS_TRANSITION`, and the stored registration SHALL remain unchanged
   (REQ-REG-B07).

3. IF a PATCH request submits a `status` value that is a member of the enum
   `confirmed`, `cancelled` and changes `status` from `cancelled` to `confirmed`, THEN
   THE SYSTEM SHALL respond with HTTP 422 and error code `INVALID_STATUS_TRANSITION`,
   treating `cancelled` as a terminal state, and the stored registration SHALL remain
   unchanged (REQ-REG-B07).

4. THE SYSTEM SHALL evaluate the `status` enum-membership check (REQ-REG-F01) before the
   transition rule in criteria 2 and 3 of this requirement, so that a `status` value
   outside `confirmed`, `cancelled` always yields the `VALIDATION_ERROR` response of
   REQ-REG-F01 rather than `INVALID_STATUS_TRANSITION` (REQ-REG-B07).

---

### REQ-REG-B08 — Statistiche per evento

**User story:**
As an organizer, I want accurate seat statistics for an event so that I can track
demand and remaining capacity.

**Acceptance criteria**

1. WHEN a request for stats on an existing `event_id` is received, THE SYSTEM SHALL
   respond with `{event_id, capacity, confirmed, available}`, where `capacity` is read
   from `event-service`, `confirmed` is the count of registrations for that event with
   `status = confirmed`, and `available` equals `capacity` minus `confirmed`
   (REQ-REG-B08).

2. IF the `event_id` provided does not correspond to any event known to `event-service`,
   THEN THE SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`
   (REQ-REG-B08).

3. WHEN `confirmed` equals `capacity` for an event, THE SYSTEM SHALL report `available`
   as `0`, never as a negative number (REQ-REG-B08).

---

### REQ-REG-B09 — Dipendenze `user-service` / `event-service` irraggiungibili

**User story:**
As a platform client, I want a clear failure when a referenced user or event cannot be
validated so that transient dependency problems are distinguishable from validation
errors.

**Acceptance criteria**

1. IF a call to `user-service` for user validation does not return a response within
   the 2-second timeout, fails because the connection is refused, or returns any status
   code in the range 500–599, THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE`, and no registration SHALL be created (REQ-REG-B09).

2. IF a call to `event-service` for event validation, price lookup, or capacity lookup
   does not return a response within the 2-second timeout, fails because the connection
   is refused, or returns any status code in the range 500–599, THEN THE SYSTEM SHALL
   respond with HTTP 503 and error code `DEPENDENCY_UNAVAILABLE`, and no registration
   SHALL be created or modified (REQ-REG-B09).

3. IF a call to `event-service` made while computing stats for `GET
   /api/v1/registrations/stats` does not return a response within the 2-second timeout,
   fails because the connection is refused, or returns any status code in the range
   500–599, THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE` (REQ-REG-B09).

---

## Riepilogo requisiti e copertura endpoint

| Requisito | Endpoint / ambito | Tipo |
|---|---|---|
| REQ-REG-01 | POST /api/v1/registrations | Funzionale |
| REQ-REG-02 | GET /api/v1/registrations/{id} | Funzionale |
| REQ-REG-03 | GET /api/v1/registrations | Funzionale |
| REQ-REG-04 | PATCH /api/v1/registrations/{id} | Funzionale |
| REQ-REG-05 | DELETE /api/v1/registrations/{id} | Funzionale |
| REQ-REG-06 | PUT /api/v1/registrations/{id} (405) | Funzionale |
| REQ-REG-07 | GET /api/v1/registrations/stats | Funzionale |
| REQ-REG-F01 | POST, PATCH (validazione campi) | Funzionale |
| REQ-REG-F02 | POST, PATCH (campi read-only / sconosciuti) | Funzionale |
| REQ-REG-F03 | tutte le risorse (400 / 405) | Funzionale |
| REQ-REG-F04 | GET /health | Non-funzionale |
| REQ-REG-F05 | tutti | Non-funzionale (errori) |
| REQ-REG-F06 | tutti | Non-funzionale (persistenza) |
| REQ-REG-F07 | tutti | Non-funzionale (configurazione) |
| REQ-REG-B01 | POST (utente esiste) | Business rule |
| REQ-REG-B02 | POST (evento esiste) | Business rule |
| REQ-REG-B03 | POST (evento published) | Business rule |
| REQ-REG-B04 | POST (doppia iscrizione confirmed) | Business rule |
| REQ-REG-B05 | POST, PATCH (capienza evento) | Business rule |
| REQ-REG-B06 | POST (amount da event.price) | Business rule |
| REQ-REG-B07 | PATCH (transizione di stato) | Business rule |
| REQ-REG-B08 | GET /api/v1/registrations/stats | Business rule |
| REQ-REG-B09 | POST, PATCH, GET /stats (dipendenze irraggiungibili) | Business rule |
