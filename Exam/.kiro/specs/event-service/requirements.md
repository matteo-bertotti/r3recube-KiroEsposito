# Requirements Document

**Servizio:** `event-service`  
**Base path:** `/api/v1/events`  
**Porta di sviluppo:** 5002  
**Tipo:** obbligatorio  
**Contratto OpenAPI:** `contracts/openapi/event-service.yaml` (fonte di verità dell'interfaccia)

---

## Introduction

L'`event-service` gestisce le conferenze della piattaforma TechConf: la loro anagrafica,
il ciclo di vita (`draft` → `published` → `cancelled`) e la capienza. Ogni evento è
associato a un organizzatore: prima di accettare un evento, il servizio verifica via
HTTP presso `user-service` che l'`organizer_id` esista e abbia ruolo `organizer`.
L'`event-service` dipende da `user-service` e non accede mai direttamente ai dati di un
altro servizio; ogni verifica sull'utente avviene con una chiamata HTTP a
`user-service`.

---

## Glossary

- **SYSTEM / event-service**: il microservizio descritto in questo documento, in ascolto
  sulla porta indicata dalla variabile d'ambiente `PORT`.
- **user-service**: microservizio dell'anagrafica utenti, raggiungibile all'URL indicato
  dalla variabile d'ambiente `USER_SERVICE_URL` (default `http://localhost:5001`).
- **Event**: la risorsa conferenza gestita dall'`event-service`.
- **organizer**: utente il cui campo `role` presso `user-service` vale `organizer`.
- **caller / platform client**: qualunque client HTTP (utente umano tramite tool, altro
  servizio, suite di test) che invoca gli endpoint dell'`event-service`.
- **EUR**: valuta implicita di tutti gli importi (`price`), espressa con 2 decimali.

---

## Modello dati

### Risorsa `Event`

| Campo | Tipo | Obbligatorio | Vincoli |
|---|---|---|---|
| `id` | UUID v4 | read-only | generato dal server, mai accettato in input |
| `title` | string | Sì | 3–120 caratteri |
| `description` | string | No | max 2000 caratteri; nullable |
| `organizer_id` | UUID | Sì | deve esistere in `user-service` con `role = organizer` |
| `venue` | string | Sì | max 100 caratteri (es. `"Auditorium Roma"`) |
| `city` | string | Sì | max 60 caratteri |
| `start_date` | date | Sì | formato `YYYY-MM-DD` |
| `end_date` | date | Sì | formato `YYYY-MM-DD`; deve essere `>= start_date` |
| `capacity` | integer | Sì | 1–10000 |
| `price` | decimal | Sì | `>= 0.00`, 2 decimali, valuta implicita EUR |
| `status` | enum | No | `draft` \| `published` \| `cancelled`; default `draft` |
| `created_at` | datetime ISO 8601 UTC | read-only | generato al momento della creazione |
| `updated_at` | datetime ISO 8601 UTC | read-only | aggiornato ad ogni modifica |

> I campi `id`, `created_at`, `updated_at` non sono mai accettati in input. Gli schemi
> `EventCreate`, `EventUpdate` ed `Event` del contratto OpenAPI hanno
> `additionalProperties: false`: qualunque campo sconosciuto in input deve essere
> rifiutato (vedi REQ-EVT-F02).

---

## Requirements

Le seguenti sottosezioni raccolgono le user story e gli acceptance criteria di ogni
requisito dell'`event-service`.

---

### REQ-EVT-01 — Creazione evento (POST /api/v1/events)

**User story:**  
As a platform client, I want to create a new conference event so that attendees can
later register for it.

**Acceptance criteria**

1. WHEN a POST request is received on `/api/v1/events` with a well-formed JSON body
   containing all required fields (`title`, `organizer_id`, `venue`, `city`,
   `start_date`, `end_date`, `capacity`, `price`), each satisfying its field constraints
   (`title` 3–120 caratteri; `venue` ≤100 caratteri; `city` ≤60 caratteri;
   `organizer_id` UUID v4; `start_date` ed `end_date` in formato `YYYY-MM-DD` con
   `start_date` ≤ `end_date`; `capacity` intero da 1 a 10000; `price` numero ≥ 0 con 2
   decimali, valuta EUR), THE SYSTEM SHALL create the event, assign a server-generated
   UUID v4 as `id`, set `created_at` and `updated_at` to the current UTC timestamp in
   ISO 8601, and respond with HTTP 201.

2. WHEN a POST request is received without a `status` field THE SYSTEM SHALL default
   `status` to `draft` (REQ-EVT-F10).

3. WHEN an event is created successfully THE SYSTEM SHALL include a `Location` header
   pointing to `/api/v1/events/{id}` in the 201 response.

4. WHEN an event is created successfully THE SYSTEM SHALL return the created `Event`
   object conforming to the `Event` schema defined in
   `contracts/openapi/event-service.yaml`.

5. WHEN a POST request omits the optional `description` field THE SYSTEM SHALL store
   `description` as `null` (REQ-EVT-F03).

6. IF a POST request body is not well-formed JSON, THEN THE SYSTEM SHALL respond with
   HTTP 400 and no event SHALL be created.

7. IF a POST request omits a required field, violates a field constraint, or includes an
   unknown field or a server-generated field (`id`, `created_at`, `updated_at`), THEN
   THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`, and no event
   SHALL be created.

---

### REQ-EVT-02 — Lettura singolo evento (GET /api/v1/events/{id})

**User story:**  
As a platform client or another service, I want to retrieve an event by its UUID so
that I can read its details and lifecycle status.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/events/{id}` and the event exists THE
   SYSTEM SHALL respond with HTTP 200 and the `Event` object conforming to the `Event`
   schema in `contracts/openapi/event-service.yaml`.

2. WHEN a GET request is received on `/api/v1/events/{id}` and no event with that `id`
   exists THE SYSTEM SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a GET request is received and `{id}` is not a valid UUID v4 format THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

---

### REQ-EVT-03 — Lista eventi paginata con filtri (GET /api/v1/events)

**User story:**  
As a platform client, I want to list events with optional filters and pagination so
that I can browse conferences by status or city without fetching the full dataset.

**Acceptance criteria**

1. WHEN a GET request is received on `/api/v1/events` with no query parameters THE
   SYSTEM SHALL respond with HTTP 200 and a paginated response with default `page=1`
   and `page_size=20`.

2. WHEN a GET request is received with valid `page` and `page_size` parameters THE
   SYSTEM SHALL return the corresponding slice of events and include `page`, `page_size`,
   and `total` in the response body.

3. WHEN `page_size` exceeds 100 THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

4. WHEN `page` is less than 1 or not a positive integer THE SYSTEM SHALL respond with
   HTTP 422 and error code `VALIDATION_ERROR`.

5. WHEN `page_size` is less than 1 or not a positive integer THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR`.

6. WHEN a GET request includes a `status` query parameter with a value in `draft`,
   `published`, `cancelled` THE SYSTEM SHALL return only events whose `status` matches
   the filter (REQ-EVT-B06).

7. WHEN a GET request includes a `status` query parameter with a value outside `draft`,
   `published`, `cancelled` THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

8. WHEN a GET request includes a `city` query parameter THE SYSTEM SHALL return only
   events whose `city` è uguale al valore del filtro con confronto esatto e
   case-sensitive (REQ-EVT-B06).

9. WHEN both `status` and `city` query parameters are provided THE SYSTEM SHALL apply
   both filters simultaneously in AND (REQ-EVT-B06).

10. WHEN no events match the applied filters THE SYSTEM SHALL respond with HTTP 200 and
    an empty `items` array with `total = 0`.

11. WHEN a GET list request returns results THE SYSTEM SHALL conform to the `EventPage`
    schema defined in `contracts/openapi/event-service.yaml`.

---

### REQ-EVT-04 — Sostituzione evento (PUT /api/v1/events/{id})

**User story:**  
As a platform client, I want to replace all editable fields of an event in a single
request so that the event definition is updated atomically.

**Acceptance criteria**

1. WHEN a PUT request is received for an existing event with a well-formed body
   containing all required fields, each satisfying its field constraints (le stesse di
   REQ-EVT-01: `title` 3–120 caratteri; `venue` ≤100; `city` ≤60; `description` ≤2000 o
   `null`; `organizer_id` UUID v4; `start_date`/`end_date` `YYYY-MM-DD` con `start_date`
   ≤ `end_date`; `capacity` intero 1–10000; `price` ≥ 0), THE SYSTEM SHALL replace all
   editable fields (`title`, `description`, `organizer_id`, `venue`, `city`,
   `start_date`, `end_date`, `capacity`, `price`, `status`), update `updated_at` to the
   current UTC timestamp, and respond with HTTP 200 and the updated `Event` object.

2. WHEN a PUT request is received and the `id` does not match any event THE SYSTEM SHALL
   respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a PUT request is received and any required field is absent or invalid THE SYSTEM
   SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`, applying the same
   field-level rules as POST (REQ-EVT-F01 … REQ-EVT-F10), and the stored event SHALL
   remain unchanged.

4. WHEN a PUT request succeeds THE SYSTEM SHALL leave `id` and `created_at` unchanged.

5. WHEN a PUT request changes `status` THE SYSTEM SHALL enforce the allowed status
   transitions (REQ-EVT-B04).

6. WHEN a PUT request provides or changes `organizer_id` THE SYSTEM SHALL validate the
   organizer against `user-service` (REQ-EVT-B01, REQ-EVT-B02).

7. WHEN a PUT response is returned THE SYSTEM SHALL conform to the `Event` schema in
   `contracts/openapi/event-service.yaml`.

8. IF a PUT request body is not well-formed JSON or includes an unknown field or a
   server-generated field (`id`, `created_at`, `updated_at`), THEN THE SYSTEM SHALL
   respond without modifying the stored event (HTTP 400 for malformed JSON, HTTP 422 con
   codice `VALIDATION_ERROR` per campi non ammessi).

9. IF the organizer validation call to `user-service` risponde 404, THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `REFERENCE_NOT_FOUND`; IF tale chiamata va
   in timeout dopo 2 secondi, la connessione è rifiutata, o `user-service` risponde 5xx,
   THEN THE SYSTEM SHALL respond with HTTP 503 and error code `DEPENDENCY_UNAVAILABLE`
   senza modificare l'evento (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).

---

### REQ-EVT-05 — Aggiornamento parziale evento (PATCH /api/v1/events/{id})

**User story:**  
As a platform client, I want to update one or more fields of an event without providing
the full resource so that I can make targeted changes efficiently.

**Acceptance criteria**

1. WHEN a PATCH request is received for an existing event with a well-formed partial
   body whose provided fields satisfy their field constraints (le stesse di REQ-EVT-01)
   THE SYSTEM SHALL update only the fields present in the request body, update
   `updated_at` to the current UTC timestamp, and respond with HTTP 200 and the updated
   `Event` object.

2. WHEN a PATCH request is received and the `id` does not match any event THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a PATCH request is received and a provided field value violates a field
   constraint THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`,
   applying the same field-level rules as POST (REQ-EVT-F01 … REQ-EVT-F10), and the
   stored event SHALL remain unchanged.

4. WHEN a PATCH request does not include a given field THE SYSTEM SHALL leave that field
   unchanged.

5. WHEN a PATCH request changes `status` THE SYSTEM SHALL enforce the allowed status
   transitions (REQ-EVT-B04).

6. WHEN a PATCH request provides a new `organizer_id` THE SYSTEM SHALL validate the
   organizer against `user-service` (REQ-EVT-B01, REQ-EVT-B02).

7. WHEN a PATCH response is returned THE SYSTEM SHALL conform to the `Event` schema in
   `contracts/openapi/event-service.yaml`.

8. IF a PATCH request body is not well-formed JSON or includes an unknown field or a
   server-generated field (`id`, `created_at`, `updated_at`), THEN THE SYSTEM SHALL
   respond without modifying the stored event (HTTP 400 for malformed JSON, HTTP 422 con
   codice `VALIDATION_ERROR` per campi non ammessi).

9. IF the organizer validation call to `user-service` risponde 404, THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `REFERENCE_NOT_FOUND`; IF tale chiamata va
   in timeout dopo 2 secondi, la connessione è rifiutata, o `user-service` risponde 5xx,
   THEN THE SYSTEM SHALL respond with HTTP 503 and error code `DEPENDENCY_UNAVAILABLE`
   senza modificare l'evento (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).

---

### REQ-EVT-06 — Cancellazione evento (DELETE /api/v1/events/{id})

**User story:**  
As a platform administrator, I want to delete an event so that erroneous or obsolete
conferences can be removed from the system.

**Acceptance criteria**

1. WHEN a DELETE request is received for an existing event THE SYSTEM SHALL permanently
   remove the event and respond with HTTP 204 and no response body.

2. WHEN a DELETE request is received and the `id` does not match any event THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

3. WHEN a DELETE request is received and `{id}` is not a valid UUID v4 format THE SYSTEM
   SHALL respond with HTTP 404 and error code `NOT_FOUND`.

4. WHEN a DELETE succeeds and a subsequent GET for the same `id` is made THE SYSTEM SHALL
   respond with HTTP 404 and error code `NOT_FOUND`.

---

### REQ-EVT-F01 — Validazione dei campi (input)

**User story:**  
As a platform client, I want every event field to be validated on creation and update
so that only well-formed events enter the system.

**Acceptance criteria**

1. WHEN a POST or PUT request omits `title`, or provides `title` shorter than 3
   characters or longer than 120 characters, THE SYSTEM SHALL respond with HTTP 422 and
   error code `VALIDATION_ERROR`.

2. WHEN a PATCH request provides `title` and its value is shorter than 3 characters or
   longer than 120 characters, THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

3. WHEN a POST, PUT, or PATCH request provides `description` as a string longer than 2000
   characters, THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`.

4. WHEN a POST or PUT request omits `venue`, or any request provides `venue` longer than
   100 characters or not a string, THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

5. WHEN a POST or PUT request omits `city`, or any request provides `city` longer than 60
   characters or not a string, THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

6. WHEN a POST or PUT request omits `organizer_id`, or any request provides
   `organizer_id` that is not a string in canonical UUID v4 format, THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

7. WHEN a POST or PUT request omits `start_date`, or any request provides `start_date`
   that is not a string matching the `YYYY-MM-DD` calendar-date format, THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

8. WHEN a POST or PUT request omits `end_date`, or any request provides `end_date` that
   is not a string matching the `YYYY-MM-DD` calendar-date format, THE SYSTEM SHALL
   respond with HTTP 422 and error code `VALIDATION_ERROR`.

9. WHEN a POST or PUT request omits `capacity`, or any request provides `capacity` that
   is not an integer or is outside the inclusive range 1–10000, THE SYSTEM SHALL respond
   with HTTP 422 and error code `VALIDATION_ERROR`.

10. WHEN a POST or PUT request omits `price`, or any request provides `price` that is not
    a number, is less than `0.00`, or has more than 2 decimal places, THE SYSTEM SHALL
    respond with HTTP 422 and error code `VALIDATION_ERROR`.

11. WHEN a POST, PUT, or PATCH request provides `status` with a value outside `draft`,
    `published`, `cancelled`, THE SYSTEM SHALL respond with HTTP 422 and error code
    `VALIDATION_ERROR` (REQ-EVT-F10).

12. WHILE the request body is valid JSON representing an object, WHEN field validation
    fails on one or more fields, THE SYSTEM SHALL include in the error `details` object
    an identification of each offending field, and SHALL NOT create or modify any event.

13. WHEN multiple field validation rules fail in a single request, THE SYSTEM SHALL
    respond with a single HTTP 422 `VALIDATION_ERROR` response rather than stopping at
    the first failure only.

---

### REQ-EVT-F02 — Rifiuto di campi read-only e campi sconosciuti

**User story:**  
As a platform client, I want the service to reject inputs that violate the contract so
that the API stays aligned with `contracts/openapi/event-service.yaml`.

**Acceptance criteria**

1. WHEN a POST, PUT, or PATCH request body contains a field not defined in the
   `EventCreate`/`EventUpdate` schema (unknown field), THE SYSTEM SHALL respond with HTTP
   422 and error code `VALIDATION_ERROR` (`additionalProperties: false`), and SHALL NOT
   create or modify any event.

2. WHEN a POST, PUT, or PATCH request body contains any of the server-managed fields
   `id`, `created_at`, or `updated_at`, THE SYSTEM SHALL respond with HTTP 422 and error
   code `VALIDATION_ERROR`, and SHALL NOT create or modify any event.

3. WHEN a POST, PUT, or PATCH request body is valid JSON but is not a JSON object (e.g.
   array, string, number, boolean, or null), THE SYSTEM SHALL respond with HTTP 422 and
   error code `VALIDATION_ERROR`.

4. WHEN input validation succeeds, THE SYSTEM SHALL persist and return only the fields
   defined in the `Event` schema of `contracts/openapi/event-service.yaml`, with no
   additional properties.

---

### REQ-EVT-F03 — Campo `description` opzionale e nullable

**User story:**  
As a platform client, I want `description` to be optional so that I can create an event
without a description and add one later.

**Acceptance criteria**

1. WHEN a POST or PUT request omits `description`, THE SYSTEM SHALL store and return
   `description` as `null`.

2. WHEN a POST, PUT, or PATCH request provides `description` as an explicit `null`, THE
   SYSTEM SHALL accept it and store `description` as `null`.

3. WHEN a POST, PUT, or PATCH request provides `description` as a string of at most 2000
   characters, THE SYSTEM SHALL store and return the provided value unchanged.

4. WHEN a PATCH request omits `description`, THE SYSTEM SHALL leave the currently stored
   `description` value unchanged.

---

### REQ-EVT-F10 — Enum e default di `status`

**User story:**  
As a platform client, I want a well-defined default and allowed values for `status` so
that the event lifecycle starts in a predictable state.

**Acceptance criteria**

1. WHEN a POST request omits `status`, THE SYSTEM SHALL default `status` to `draft`.

2. WHEN a POST, PUT, or PATCH request provides `status` with a value in `draft`,
   `published`, `cancelled`, THE SYSTEM SHALL accept the value subject to the transition
   rules (REQ-EVT-B04).

3. WHEN a POST, PUT, or PATCH request provides `status` with a value outside `draft`,
   `published`, `cancelled`, THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`.

4. WHEN a PATCH request omits `status`, THE SYSTEM SHALL leave the currently stored
   `status` value unchanged.

---

### REQ-EVT-B01 — L'organizzatore deve esistere

**User story:**  
As a platform administrator, I want every event to reference an existing user as its
organizer so that no event points to a non-existent account.

**Acceptance criteria**

1. WHEN a POST request is received THE SYSTEM SHALL call
   `GET /api/v1/users/{organizer_id}` on `user-service` at the URL given by
   `USER_SERVICE_URL` (default `http://localhost:5001`) with a 2-second timeout, and
   complete this validation successfully before persisting the event (REQ-EVT-B01).

2. WHEN a PUT or PATCH request sets `organizer_id` to a value different from the
   currently stored value THE SYSTEM SHALL call `GET /api/v1/users/{organizer_id}` on
   `user-service` at the URL given by `USER_SERVICE_URL` (default `http://localhost:5001`)
   with a 2-second timeout, and complete this validation successfully before persisting
   the event (REQ-EVT-B01).

3. WHEN a PUT or PATCH request does not set or change `organizer_id` THE SYSTEM SHALL NOT
   call `user-service` for organizer validation (REQ-EVT-B01).

4. IF `user-service` responds with HTTP 404 for the given `organizer_id` THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `REFERENCE_NOT_FOUND`, and SHALL leave the
   stored event unchanged (REQ-EVT-B01).

---

### REQ-EVT-B02 — L'organizzatore deve avere ruolo `organizer`

**User story:**  
As a platform administrator, I want event organizers to actually hold the organizer
role so that only authorized users can own conferences.

**Acceptance criteria**

1. IF `user-service` returns HTTP 200 for the given `organizer_id` and the returned
   user's `role` field has a value other than `organizer` THEN THE SYSTEM SHALL respond
   with HTTP 422 and error code `INVALID_ORGANIZER`, and SHALL leave the stored event
   unchanged (REQ-EVT-B02).

2. WHEN `user-service` returns HTTP 200 for the given `organizer_id` and the returned
   user's `role` field equals `organizer` THE SYSTEM SHALL proceed with creating or
   updating the event (REQ-EVT-B02).

---

### REQ-EVT-B03 — Coerenza delle date (`end_date >= start_date`)

**User story:**  
As a platform client, I want the event end date to be on or after the start date so that
every event has a valid duration.

**Acceptance criteria**

1. IF a POST or PUT request produces an event whose resulting `end_date` is earlier than
   its resulting `start_date` THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `VALIDATION_ERROR`, and SHALL NOT create or modify the event (REQ-EVT-B03).

2. IF a PATCH request provides `start_date`, `end_date`, or both, and the effective
   `end_date` (the incoming value if present, otherwise the stored value) is earlier than
   the effective `start_date` (the incoming value if present, otherwise the stored value)
   THEN THE SYSTEM SHALL respond with HTTP 422 and error code `VALIDATION_ERROR`, and
   SHALL leave the stored event unchanged (REQ-EVT-B03).

3. WHEN a POST, PUT, or PATCH request produces an event whose effective `end_date` equals
   or is later than its effective `start_date` THE SYSTEM SHALL accept the dates
   (REQ-EVT-B03).

---

### REQ-EVT-B04 — Transizioni di stato consentite

**User story:**  
As a platform administrator, I want the event lifecycle to follow a defined set of
transitions so that events cannot move into inconsistent states.

**Acceptance criteria**

1. WHEN a PUT or PATCH request changes `status` from `draft` to `published`, from
   `draft` to `cancelled`, or from `published` to `cancelled` THE SYSTEM SHALL accept
   the transition (REQ-EVT-B04).

2. WHEN a PUT or PATCH request submits a `status` value equal to the event's current
   stored `status` THE SYSTEM SHALL accept the request without applying a transition
   (REQ-EVT-B04).

3. IF a PUT or PATCH request changes `status` from a stored value of `cancelled` to any
   other value THEN THE SYSTEM SHALL respond with HTTP 422 and error code
   `INVALID_STATUS_TRANSITION`, treating `cancelled` as a terminal state, and SHALL leave
   the stored event unchanged (REQ-EVT-B04).

4. IF a PUT or PATCH request changes `status` to any transition other than
   `draft`→`published`, `draft`→`cancelled`, or `published`→`cancelled` THEN THE SYSTEM
   SHALL respond with HTTP 422 and error code `INVALID_STATUS_TRANSITION`, and SHALL
   leave the stored event unchanged (REQ-EVT-B04).

---

### REQ-EVT-B05 — Dipendenza `user-service` irraggiungibile

**User story:**  
As a platform client, I want a clear failure when the organizer cannot be validated so
that transient dependency problems are distinguishable from validation errors.

**Acceptance criteria**

1. IF a call to `user-service` for organizer validation does not return a response
   within the 2-second timeout THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE`, and SHALL leave the stored event unchanged (REQ-EVT-B05).

2. IF a call to `user-service` for organizer validation fails because the connection is
   refused THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE`, and SHALL leave the stored event unchanged (REQ-EVT-B05).

3. IF a call to `user-service` for organizer validation returns any status code in the
   range 500–599 THEN THE SYSTEM SHALL respond with HTTP 503 and error code
   `DEPENDENCY_UNAVAILABLE`, and SHALL leave the stored event unchanged (REQ-EVT-B05).

---

### REQ-EVT-B06 — Filtri lista per `status` e `city`

**User story:**  
As a platform client, I want to filter events by status and city so that I can find the
conferences relevant to me without scanning the entire list.

**Acceptance criteria**

1. WHEN a `status` filter with a value in `draft`, `published`, `cancelled` is applied
   THE SYSTEM SHALL return only events whose `status` field is exactly equal to the given
   value (case-sensitive) and SHALL exclude every event whose `status` differs
   (REQ-EVT-B06).

2. WHEN a `city` filter is applied THE SYSTEM SHALL return only events whose `city` field
   is exactly equal to the given value, compared case-insensitively, and SHALL exclude
   every event whose `city` does not match (REQ-EVT-B06).

3. WHEN both the `status` and `city` filters are applied simultaneously THE SYSTEM SHALL
   return only events that satisfy both conditions and SHALL apply the filters before
   pagination so that `page`, `page_size`, and `total` reflect the filtered set
   (REQ-EVT-B06).

4. WHEN a `status` filter, a `city` filter, or both are applied and no stored event
   satisfies the applied condition(s) THE SYSTEM SHALL respond with HTTP 200, an empty
   `items` array, and `total = 0` (REQ-EVT-B06).

---

### REQ-EVT-F04 — JSON malformato e metodi non previsti

**User story:**  
As a platform client, I want consistent protocol-level errors so that malformed requests
and unsupported methods are reported predictably.

**Acceptance criteria**

1. WHEN a POST, PUT, or PATCH request body is not valid JSON, or the request body is
   empty, THE SYSTEM SHALL respond with HTTP 400 and error code `MALFORMED_JSON`, and
   SHALL NOT create or modify any event.

2. WHEN a request uses an HTTP method not defined for a resource path (e.g. PUT on
   `/api/v1/events`, POST on `/api/v1/events/{id}`), THE SYSTEM SHALL respond with HTTP
   405 and SHALL include an indication of the methods allowed on that path.

3. WHEN a request body is valid JSON, THE SYSTEM SHALL evaluate malformed-JSON handling
   before field-level validation, so that a malformed body always yields HTTP 400 rather
   than HTTP 422.

---

### REQ-EVT-F05 — Health check (GET /health)

**User story:**  
As an orchestrator or dependent service, I want a lightweight endpoint to verify that
event-service is alive so that startup probes and resilience tests can operate correctly.

**Acceptance criteria**

1. WHEN a GET request is received on `/health`, THE SYSTEM SHALL respond with HTTP 200
   and body `{"status": "ok", "service": "event-service"}` regardless of storage state
   and regardless of whether `user-service` is reachable.

2. WHEN the health check response is returned, THE SYSTEM SHALL conform to the `Health`
   schema defined in `contracts/openapi/event-service.yaml`, with no additional
   properties.

3. WHEN a request uses an HTTP method other than GET (or HEAD) on `/health`, THE SYSTEM
   SHALL respond with HTTP 405.

---

### REQ-EVT-F06 — Formato delle risposte di errore

**User story:**  
As a platform client, I want all error responses to follow a consistent structure so
that I can handle them programmatically without special-casing each endpoint.

**Acceptance criteria**

1. WHEN any error response is returned, THE SYSTEM SHALL use the body structure
   `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`, where `code`
   and `message` are always present and `details` is optional.

2. WHEN a 400 response is returned, THE SYSTEM SHALL set `code` to `MALFORMED_JSON`.

3. WHEN a 404 response is returned, THE SYSTEM SHALL set `code` to `NOT_FOUND`.

4. WHEN a 422 response is returned for field validation, THE SYSTEM SHALL set `code` to
   `VALIDATION_ERROR` and SHALL include in `details` an identification of the offending
   field(s).

5. WHEN a 422 response is returned because the referenced organizer does not exist, THE
   SYSTEM SHALL set `code` to `REFERENCE_NOT_FOUND` (REQ-EVT-B01).

6. WHEN a 422 response is returned because the referenced organizer lacks role
   `organizer`, THE SYSTEM SHALL set `code` to `INVALID_ORGANIZER` (REQ-EVT-B02).

7. WHEN a 422 response is returned because of a disallowed status transition, THE SYSTEM
   SHALL set `code` to `INVALID_STATUS_TRANSITION` (REQ-EVT-B04).

8. WHEN a 503 response is returned because `user-service` is unreachable, THE SYSTEM
   SHALL set `code` to `DEPENDENCY_UNAVAILABLE` (REQ-EVT-B05).

9. WHEN any error response is returned, THE SYSTEM SHALL conform to the `Error` schema in
   `contracts/openapi/event-service.yaml`, with no additional properties outside `code`,
   `message`, and `details`.

---

### REQ-EVT-F07 — Persistenza multi-backend

**User story:**  
As a deployment operator, I want to switch the storage backend via an environment
variable so that the service can run in-memory for tests, on JSON for lightweight
deployments, and on SQLite for durability, without changing any business logic.

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` (or the variable is absent), THE SYSTEM SHALL keep all
   event data in in-process Python structures, and all data SHALL be lost on process
   restart.

2. WHEN `STORAGE_BACKEND=json`, THE SYSTEM SHALL persist event data as a JSON file in the
   directory specified by `DATA_DIR` (default `./data`) using only the standard `json`
   library, and previously persisted events SHALL be readable after a process restart.

3. WHEN `STORAGE_BACKEND=sqlite`, THE SYSTEM SHALL persist event data in a SQLite
   database file in the directory specified by `DATA_DIR` (default `./data`) using only
   the standard `sqlite3` library, and previously persisted events SHALL be readable
   after a process restart.

4. IF the backend is switched from `memory` to `json` or `sqlite`, THEN THE SYSTEM SHALL
   apply identical create/read/update/delete behaviour observable at the API without any
   modification to domain or API logic.

5. WHEN a write is requested and the directory specified by `DATA_DIR` does not exist,
   THE SYSTEM SHALL create it before writing.

6. IF `STORAGE_BACKEND` is set to a value other than `memory`, `json`, or `sqlite`, THEN
   THE SYSTEM SHALL fail to start with an error message identifying the invalid value.

---

### REQ-EVT-F08 — Configurazione via variabili d'ambiente

**User story:**  
As a deployment operator, I want all runtime configuration to be read from environment
variables at startup so that no value is hardcoded and the service is portable across
environments.

**Acceptance criteria**

1. WHEN the service starts, THE SYSTEM SHALL read `PORT` from the environment and listen
   on that port; `PORT` SHALL never be hardcoded.

2. WHEN the service starts, THE SYSTEM SHALL read `USER_SERVICE_URL` (default
   `http://localhost:5001`), `STORAGE_BACKEND` (default `memory`), and `DATA_DIR`
   (default `./data`) from the environment exactly once and apply them unchanged for the
   entire lifetime of the process.

3. WHEN a call to `user-service` is made, THE SYSTEM SHALL use the URL from
   `USER_SERVICE_URL` and apply a 2-second timeout, never a hardcoded URL.

4. IF `PORT` is not set, or is set to a value that is not an integer in the range
   1–65535, THEN THE SYSTEM SHALL fail to start with an error message identifying `PORT`
   as the cause, and SHALL NOT listen on any port.

---

## Riepilogo requisiti e copertura endpoint

| Requisito | Endpoint / ambito | Tipo |
|---|---|---|
| REQ-EVT-01 | POST /api/v1/events | Funzionale |
| REQ-EVT-02 | GET /api/v1/events/{id} | Funzionale |
| REQ-EVT-03 | GET /api/v1/events | Funzionale |
| REQ-EVT-04 | PUT /api/v1/events/{id} | Funzionale |
| REQ-EVT-05 | PATCH /api/v1/events/{id} | Funzionale |
| REQ-EVT-06 | DELETE /api/v1/events/{id} | Funzionale |
| REQ-EVT-F01 | POST, PUT, PATCH (validazione campi) | Funzionale |
| REQ-EVT-F02 | POST, PUT, PATCH (campi read-only / sconosciuti) | Funzionale |
| REQ-EVT-F03 | POST, PUT, PATCH (`description`) | Funzionale |
| REQ-EVT-F10 | POST, PUT, PATCH (`status` enum/default) | Funzionale |
| REQ-EVT-B01 | POST, PUT, PATCH (organizzatore esiste) | Business rule |
| REQ-EVT-B02 | POST, PUT, PATCH (ruolo organizer) | Business rule |
| REQ-EVT-B03 | POST, PUT, PATCH (date coerenti) | Business rule |
| REQ-EVT-B04 | PUT, PATCH (transizioni di stato) | Business rule |
| REQ-EVT-B05 | POST, PUT, PATCH (dipendenza irraggiungibile) | Business rule |
| REQ-EVT-B06 | GET /api/v1/events (filtri) | Business rule |
| REQ-EVT-F04 | tutte le risorse (400 / 405) | Funzionale |
| REQ-EVT-F05 | GET /health | Non-funzionale |
| REQ-EVT-F06 | tutti | Non-funzionale (errori) |
| REQ-EVT-F07 | tutti | Non-funzionale (persistenza) |
| REQ-EVT-F08 | tutti | Non-funzionale (configurazione) |
