# Design — user-service

**Servizio:** `user-service`  
**Contratto di riferimento:** `contracts/openapi/user-service.yaml`  
**Requirements:** `.kiro/specs/user-service/requirements.md`  
**Regole di struttura e piattaforma:** `.kiro/steering/structure.md`, `.kiro/steering/platform-standards.md`

---

## Overview

`user-service` è l'anagrafica centrale di TechConf: gestisce il ciclo di vita degli
utenti (partecipanti, speaker, organizzatori) ed è l'unica fonte di verità per
l'identità degli utenti nella piattaforma. Non dipende da nessun altro servizio; è
chiamato da `event-service`, `registration-service` e `notification-service`.

Il servizio espone una REST API JSON su `/api/v1/users` e un health check su
`/health`. Supporta tre backend di persistenza intercambiabili (`memory`, `json`,
`sqlite`) selezionati a runtime via variabile d'ambiente, senza modificare la logica
di business.

---

## Architecture

Il servizio è organizzato in quattro livelli indipendenti, ognuno con una
responsabilità unica:

```
HTTP request
     │
     ▼
┌─────────────────────────────────────────┐
│  api/  (Flask Blueprint)                │  ← parsing, routing, mapping errori→HTTP
│  users.py · errors.py                  │
└────────────────┬────────────────────────┘
                 │ chiama
                 ▼
┌─────────────────────────────────────────┐
│  domain/  (business logic pura)         │  ← regole REQ-USR-*, validazione, paginazione
│  user_service.py · models.py            │
└────────────────┬────────────────────────┘
                 │ dipende da interfaccia
                 ▼
┌─────────────────────────────────────────┐
│  repository/  (persistenza)             │  ← memory · json · sqlite
│  base.py · memory.py · json_repo.py     │
│  sqlite_repo.py · __init__.py (factory) │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  config.py  (configurazione)            │  ← unico punto di lettura env var
└─────────────────────────────────────────┘
```

Struttura cartelle del servizio:

```
services/user-service/
├── app/
│   ├── __main__.py          # entry point: legge PORT, crea l'app Flask, avvia il server
│   ├── config.py            # legge PORT, STORAGE_BACKEND, DATA_DIR una sola volta
│   ├── api/
│   │   ├── __init__.py
│   │   ├── users.py         # Blueprint Flask con tutte le route
│   │   └── errors.py        # helper error_response(code, message, status, details)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py        # dataclass User + to_dict / from_dict
│   │   └── user_service.py  # UserService + eccezioni di dominio
│   └── repository/
│       ├── __init__.py      # factory get_repository(backend, data_dir)
│       ├── base.py          # ABC UserRepository
│       ├── memory.py        # MemoryUserRepository
│       ├── json_repo.py     # JsonUserRepository
│       └── sqlite_repo.py   # SqliteUserRepository
├── tests/
│   ├── unit/
│   │   ├── conftest.py
│   │   ├── test_domain.py
│   │   ├── test_api_users.py
│   │   └── test_repository.py
│   └── integration/
│       └── test_integration.py
└── requirements.txt
```

`user-service` non ha una cartella `clients/` perché non chiama nessun altro servizio.

---

## Components and Interfaces

### `app/config.py`

Unico punto di lettura delle variabili d'ambiente. Espone costanti già risolte
importate da tutti gli altri moduli. `PORT` è obbligatorio e causa un errore
esplicito se assente.

```python
PORT            = int(os.environ["PORT"])                        # obbligatorio
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "memory")   # memory | json | sqlite
DATA_DIR        = os.environ.get("DATA_DIR", "./data")
```

### `app/domain/models.py`

`User` è un dataclass Python puro senza dipendenze da Flask o dal backend.

- `User.create(data: dict) -> User` — genera `id` (UUID v4), `created_at`,
  `updated_at`, applica default `role = attendee`, normalizza `email` in minuscolo
  (REQ-USR-B02).
- `user.to_dict() -> dict` — serializzazione JSON con timestamp ISO 8601 UTC.
- `User.from_dict(d: dict) -> User` — deserializzazione dal backend.

### `app/domain/user_service.py`

Logica di business iniettata con il repository via costruttore. Non importa Flask né
`os.environ`.

| Metodo | Requisiti | Descrizione |
|---|---|---|
| `create_user(data)` | REQ-USR-01, B01, B02 | valida campi, controlla unicità email, crea e persiste |
| `get_user(id)` | REQ-USR-02 | recupera per id; solleva `NotFound` se assente |
| `list_users(page, page_size, role, email)` | REQ-USR-03, B03 | filtra e pagina |
| `replace_user(id, data)` | REQ-USR-04, B01, B02 | sostituisce tutti i campi editabili |
| `update_user(id, data)` | REQ-USR-05, B01, B02 | aggiorna solo i campi presenti |
| `delete_user(id)` | REQ-USR-06 | rimuove; solleva `NotFound` se assente |

**Eccezioni di dominio** (catturate nelle route, mai propagate a Flask):

| Eccezione | Status | Code |
|---|---|---|
| `ValidationError(field, message)` | 422 | `VALIDATION_ERROR` |
| `EmailAlreadyExists` | 409 | `EMAIL_ALREADY_EXISTS` |
| `NotFound` | 404 | `NOT_FOUND` |

### `app/api/users.py`

Blueprint Flask. Ogni route:
1. Parsa il corpo JSON — `BadRequest` di Flask → 400 `MALFORMED_JSON`.
2. Chiama il metodo corrispondente di `UserService`.
3. Cattura le eccezioni di dominio e le mappa al codice HTTP + formato errore standard.
4. Ritorna `jsonify(user.to_dict()), 201/200/204`.

Mapping route → dominio:

| Metodo HTTP | Path | Metodo `UserService` |
|---|---|---|
| POST | `/api/v1/users` | `create_user` |
| GET | `/api/v1/users` | `list_users` |
| GET | `/api/v1/users/<id>` | `get_user` |
| PUT | `/api/v1/users/<id>` | `replace_user` |
| PATCH | `/api/v1/users/<id>` | `update_user` |
| DELETE | `/api/v1/users/<id>` | `delete_user` |
| GET | `/health` | risposta inline |

### `app/api/errors.py`

```python
def error_response(code: str, message: str, status: int, details: dict = None) -> Response
```

Costruisce il body standard `{"error": {"code": ..., "message": ..., "details": ...}}`
e ritorna un oggetto `Response` Flask con `Content-Type: application/json`.

### `app/repository/base.py` — `UserRepository` (ABC)

```python
class UserRepository(ABC):
    def save(self, user: User) -> None: ...
    def find_by_id(self, id: str) -> User | None: ...
    def find_by_email(self, email: str) -> User | None: ...   # email già in minuscolo
    def list(self, role: str | None, email: str | None) -> list[User]: ...
    def delete(self, id: str) -> bool: ...                    # False se non esiste
```

### `MemoryUserRepository`

Dizionario `dict[str, User]` in-process. Nessuna dipendenza esterna.

### `JsonUserRepository`

Legge/scrive `{DATA_DIR}/users.json`. Il file contiene `{"users": [...]}`.
Ogni scrittura ricarica e riscrive l'intero file. Crea `DATA_DIR` se non esiste.

### `SqliteUserRepository`

Database `{DATA_DIR}/users.db` con schema creato al primo avvio. Solo `sqlite3` dalla
libreria standard.

```sql
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    company     TEXT,
    role        TEXT NOT NULL DEFAULT 'attendee',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

### Factory `repository/__init__.py`

```python
def get_repository(backend: str, data_dir: str) -> UserRepository:
    if backend == "json":   return JsonUserRepository(data_dir)
    if backend == "sqlite": return SqliteUserRepository(data_dir)
    return MemoryUserRepository()
```

Invocata una sola volta in `__main__.py`; il risultato viene iniettato in
`UserService`.

---

## Data Models

### `User` (dataclass)

| Campo | Tipo Python | Note |
|---|---|---|
| `id` | `str` (UUID v4) | generato dal server con `uuid.uuid4()` |
| `first_name` | `str` | 1–50 caratteri |
| `last_name` | `str` | 1–50 caratteri |
| `email` | `str` | formato email valido; sempre in minuscolo |
| `company` | `str \| None` | max 100 caratteri; opzionale |
| `role` | `str` | `attendee` \| `speaker` \| `organizer`; default `attendee` |
| `created_at` | `datetime` (UTC) | immutabile dopo la creazione |
| `updated_at` | `datetime` (UTC) | aggiornato ad ogni modifica |

Serializzazione JSON: `to_dict()` formatta i timestamp come `"2026-10-15T09:30:00Z"`
(ISO 8601 UTC con suffisso `Z`).

### Risposta paginata `UserPage`

```json
{
  "items": [ { ...User... } ],
  "page": 1,
  "page_size": 20,
  "total": 57
}
```

Paginazione applicata dopo il filtraggio:

```
total  = len(filtered)
offset = (page - 1) * page_size
items  = filtered[offset : offset + page_size]
```

Vincoli: `page >= 1`, `1 <= page_size <= 100`; violazioni → `ValidationError`.

### Schema SQLite

Vedere sezione `SqliteUserRepository` sopra. Tutti i valori sono `TEXT`; i timestamp
sono stringhe ISO 8601 UTC.

---

## Error Handling

Tutti gli errori seguono il formato standard della piattaforma:

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "descrizione leggibile",
    "details": {}
  }
}
```

| Situazione | Status | `code` |
|---|---|---|
| JSON malformato nel body | 400 | `MALFORMED_JSON` |
| Campo obbligatorio mancante o valore non valido | 422 | `VALIDATION_ERROR` |
| Email già esistente (case-insensitive) | 409 | `EMAIL_ALREADY_EXISTS` |
| Risorsa non trovata per `id` | 404 | `NOT_FOUND` |

**Validazione dei campi** (in `domain/user_service.py`, non nelle route):

| Campo | Regola |
|---|---|
| `first_name` | obbligatorio; 1 ≤ len ≤ 50 |
| `last_name` | obbligatorio; 1 ≤ len ≤ 50 |
| `email` | obbligatorio; regex formato email; normalizzato in minuscolo |
| `company` | opzionale; se presente len ≤ 100; accetta `null` |
| `role` | opzionale; se presente in `{attendee, speaker, organizer}`; default `attendee` |

Per PATCH: solo i campi presenti nel body vengono validati; i campi assenti restano
immutati. Un body senza campi riconosciuti → `ValidationError`.

Per PUT: `role` assente nel body → default `attendee` (stesso comportamento di POST).

---

## Correctness Properties

Le seguenti proprietà devono reggere in qualsiasi stato del sistema:

### Property 1: Email univoca
**Validates: Requirements 1.1, 1.2**

Non possono esistere due `User` con lo stesso `email` (confronto case-insensitive, REQ-USR-B01).
Garantita dal controllo in `UserService` prima di `repo.save()` e dal vincolo `UNIQUE`
nella colonna SQLite.

### Property 2: Email sempre in minuscolo
**Validates: Requirements 1.3, 1.4**

Il campo `email` di ogni `User` in storage è sempre minuscolo (REQ-USR-B02). `User.create` e i
metodi di update normalizzano prima di salvare.

### Property 3: Immutabilità di `id` e `created_at`
**Validates: Requirements 4.6, 5.6**

PUT e PATCH non modificano mai `id` o `created_at`; `replace_user` e `update_user`
li preservano dal record esistente (REQ-USR-04, REQ-USR-05).

### Property 4: `updated_at` aggiornato ad ogni modifica
**Validates: Requirements 4.1, 5.1**

Dopo ogni modifica `updated_at >= created_at`. Il valore è aggiornato al momento
dell'operazione (REQ-USR-04, REQ-USR-05).

### Property 5: Intercambiabilità dei backend
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

Lo stesso comportamento CRUD osservabile con `memory`, `json` e `sqlite` (REQ-USR-08).
Garantita dai test parametrizzati in `test_repository.py`.

### Property 6: Porta sempre da variabile d'ambiente
**Validates: Requirements 9.1, 9.3**

Il servizio ascolta esattamente sulla porta passata da `PORT`; nessun valore è hardcoded (REQ-USR-09).

---

## Testing Strategy

### Unit test (`tests/unit/`)

**`test_domain.py`** — testa `UserService` in isolamento con `MemoryUserRepository`:
- creazione valida → UUID generato, `created_at` / `updated_at` presenti, `role` default
- email normalizzata in minuscolo (REQ-USR-B02) → `@pytest.mark.req("REQ-USR-B02")`
- email duplicata → `EmailAlreadyExists` (REQ-USR-B01) → `@pytest.mark.req("REQ-USR-B01")`
- campi mancanti o fuori lunghezza → `ValidationError`
- filtro `role` e `email` (REQ-USR-B03) → `@pytest.mark.req("REQ-USR-B03")`
- paginazione: offset e slice corretti; page_size > 100 → `ValidationError`
- PATCH: solo i campi forniti vengono aggiornati
- PUT: `role` assente → default `attendee`
- DELETE: secondo delete → `NotFound`

**`test_repository.py`** — testa tutti e tre i backend con `tmp_path`. Test
parametrizzati su `[MemoryUserRepository, JsonUserRepository(tmp_path),
SqliteUserRepository(tmp_path)]`. Per ogni backend: `save` → `find_by_id`,
`find_by_email`, `list` con filtri, `delete`, unicità email.

**`test_api_users.py`** — testa le route Flask con `app.test_client()` (backend
memory):
- almeno 1 chiamata a `assert_matches_contract` per endpoint (contratto OpenAPI)
- header `Location` su 201
- 400 su JSON malformato
- 422 su campo mancante / valore non valido / page_size > 100
- 409 su email duplicata
- 404 su `id` inesistente
- filtri `role` e `email` su GET lista

**Coverage target:** ≥ 80% su `app/` con `pytest --cov=app`.

### Integration test (`tests/integration/`)

`test_integration.py` avvia `user-service` come sottoprocesso (`subprocess.Popen`)
su porta 19001 con `STORAGE_BACKEND=memory`, aspetta l'health check, poi esegue:
- POST + GET (smoke)
- PUT + PATCH + verifica `updated_at` aggiornato
- DELETE + GET → 404
- POST con email duplicata → 409

Il processo viene terminato nella fixture `autouse` di scope `session`.

### Comando singolo per tutti i test del servizio

```bash
pytest services/user-service/tests --cov=app
```
