# Design — registration-service

**Servizio:** `registration-service`
**Contratto di riferimento:** `contracts/openapi/registration-service.yaml`
**Requirements:** `.kiro/specs/registration-service/requirements.md`
**Regole di struttura e piattaforma:** `.kiro/steering/structure.md`, `.kiro/steering/platform-standards.md`, `.kiro/steering/tech.md`

---

## Overview

`registration-service` gestisce le iscrizioni degli utenti agli eventi di TechConf:
creazione, lettura singola, lista paginata con filtri, aggiornamento dello stato
(cancellazione logica), cancellazione fisica del record e statistiche di occupazione
per evento. È l'unico dei servizi obbligatori con **due dipendenze HTTP dirette**:

- **user-service** (`USER_SERVICE_URL`) — per verificare che `user_id` esista
  (REQ-REG-B01);
- **event-service** (`EVENT_SERVICE_URL`) — per verificare che `event_id` esista e sia
  `published` (REQ-REG-B02, REQ-REG-B03), e per leggere `price` e `capacity`
  dell'evento, usati rispettivamente per calcolare `amount` (REQ-REG-B06) e per il
  controllo di capienza e le statistiche (REQ-REG-B05, REQ-REG-B08).

Come per `event-service`, il servizio non accede mai direttamente ai dati di
`user-service` o `event-service`: ogni verifica passa da una chiamata HTTP con timeout
di 2 secondi, incapsulata in un modulo `clients/` dedicato per ciascuna dipendenza. Se
una dipendenza risponde 404, il servizio risponde 422 `REFERENCE_NOT_FOUND`; se la
chiamata va in timeout, la connessione è rifiutata, o la dipendenza risponde 5xx, il
servizio risponde 503 `DEPENDENCY_UNAVAILABLE` (REQ-REG-B09), senza creare o modificare
alcuna iscrizione.

Il servizio espone una REST API JSON su `/api/v1/registrations` e un health check su
`/health`, sempre raggiungibile anche quando `user-service` o `event-service` non sono
disponibili (REQ-REG-F04). Supporta i tre backend di persistenza intercambiabili
(`memory`, `json`, `sqlite`) selezionati a runtime via `STORAGE_BACKEND`, senza che il
cambio di backend richieda modifiche a `domain/` (REQ-REG-F06).

---

## Architecture

Il servizio è organizzato in cinque livelli indipendenti, sullo stesso schema di
`event-service`, ma con **due** client HTTP invece di uno (`user_client.py` e
`event_client.py`), entrambi iniettati in `RegistrationService`:

```
HTTP request
     │
     ▼
┌─────────────────────────────────────────┐
│  api/  (Flask Blueprint)                │  ← parsing, routing, mapping errori→HTTP
│  registrations.py · errors.py           │
└────────────────┬────────────────────────┘
                 │ chiama
                 ▼
┌─────────────────────────────────────────┐
│  domain/  (business logic pura)         │  ← regole REQ-REG-B*, validazione, paginazione,
│  registration_service.py · models.py    │    ordine di valutazione REQ-REG-01 AC7,
│                                          │    controllo capienza, transizione status
└──────┬──────────────────┬───────────────┘
       │ dipende da        │ dipende da interfaccia
       ▼                   ▼
┌───────────────────────┐  ┌─────────────────────────────────────────┐
│  clients/             │  │  repository/  (persistenza)             │  ← memory · json · sqlite
│  user_client.py        │  │  base.py · memory.py · json_repo.py     │
│  event_client.py       │  │  sqlite_repo.py · __init__.py (factory) │
│  (HTTP→user/event-svc) │  └─────────────────────────────────────────┘
└───────────────────────┘

┌─────────────────────────────────────────┐
│  config.py  (configurazione)            │  ← unico punto di lettura env var
└─────────────────────────────────────────┘
```

`domain/registration_service.py` non importa `requests` direttamente: riceve
`repository`, `user_client` ed `event_client` iniettati dal costruttore. Questo
permette di mockare entrambi i client nei test di dominio e di mockare le chiamate HTTP
a basso livello (via `responses`) nei test che esercitano `clients/user_client.py` e
`clients/event_client.py` direttamente.

Struttura cartelle del servizio (conforme a `structure.md`):

```
services/registration-service/
├── app/
│   ├── __main__.py            # entry point: legge PORT, crea l'app Flask, avvia il server
│   ├── config.py               # legge PORT, USER_SERVICE_URL, EVENT_SERVICE_URL,
│   │                            # STORAGE_BACKEND, DATA_DIR una sola volta
│   ├── api/
│   │   ├── __init__.py
│   │   ├── registrations.py    # Blueprint Flask con tutte le route
│   │   └── errors.py           # helper error_response(code, message, status, details)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py            # dataclass Registration + to_dict / from_dict
│   │   └── registration_service.py  # RegistrationService + eccezioni di dominio
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── user_client.py       # wraps GET /api/v1/users/{id} verso user-service
│   │   └── event_client.py      # wraps GET /api/v1/events/{id} verso event-service
│   └── repository/
│       ├── __init__.py          # factory get_repository(backend, data_dir)
│       ├── base.py              # ABC RegistrationRepository
│       ├── memory.py            # MemoryRegistrationRepository
│       ├── json_repo.py         # JsonRegistrationRepository
│       └── sqlite_repo.py       # SqliteRegistrationRepository
├── tests/
│   ├── unit/
│   │   ├── conftest.py
│   │   ├── test_domain.py
│   │   ├── test_user_client.py
│   │   ├── test_event_client.py
│   │   ├── test_api_registrations.py
│   │   └── test_repository.py
│   └── integration/
│       └── test_integration.py   # avvia user-service ed event-service reali come sottoprocessi
└── requirements.txt
```

---

## Components and Interfaces

### `app/config.py`

Unico punto di lettura delle variabili d'ambiente (REQ-REG-F07). Espone costanti già
risolte importate da tutti gli altri moduli. `PORT` è obbligatorio e causa un errore
esplicito se assente o fuori range (REQ-REG-F07 AC4).

```python
PORT                = int(os.environ["PORT"])                              # obbligatorio, 1-65535
USER_SERVICE_URL    = os.environ.get("USER_SERVICE_URL") or "http://localhost:5001"
EVENT_SERVICE_URL   = os.environ.get("EVENT_SERVICE_URL") or "http://localhost:5002"
STORAGE_BACKEND     = os.environ.get("STORAGE_BACKEND") or "memory"        # memory | json | sqlite
DATA_DIR            = os.environ.get("DATA_DIR") or "./data"
DEPENDENCY_TIMEOUT  = 2  # secondi, mai configurabile via env (fisso da platform-standards.md)
```

Variabili assenti o vuote sono trattate come non impostate e sostituite dal default
documentato (REQ-REG-F07 AC2).

### `app/domain/models.py`

`Registration` è un dataclass Python puro, senza dipendenze da Flask, dal repository o
dai client HTTP.

- `Registration.create(user_id, event_id, amount) -> Registration` — genera `id`
  (UUID v4), `created_at`, `updated_at`, imposta `status = "confirmed"`
  (REQ-REG-01 AC1).
- `registration.to_dict() -> dict` — serializzazione JSON con `amount` a 2 decimali e
  timestamp ISO 8601 UTC.
- `Registration.from_dict(d: dict) -> Registration` — deserializzazione dal backend.

```python
@dataclass
class Registration:
    id: str
    user_id: str
    event_id: str
    amount: Decimal
    status: str            # "confirmed" | "cancelled"
    created_at: datetime
    updated_at: datetime
```

### `app/domain/registration_service.py`

Logica di business iniettata con `repository`, `user_client` ed `event_client` via
costruttore. Non importa Flask né `os.environ`; non chiama `requests` direttamente
(passa sempre per i client).

```python
class RegistrationService:
    def __init__(
        self,
        repository: RegistrationRepository,
        user_client: UserClient,
        event_client: EventClient,
    ): ...
```

| Metodo | Requisiti | Descrizione |
|---|---|---|
| `create_registration(data)` | REQ-REG-01, F01, F02, B01-B06 | valida i campi, verifica utente ed evento, applica le regole di business in ordine, crea e persiste |
| `get_registration(id)` | REQ-REG-02 | recupera per id; solleva `NotFound` se assente o `id` non UUID valido |
| `list_registrations(page, page_size, user_id, event_id, status)` | REQ-REG-03 | filtra (AND su `user_id`/`event_id`/`status`), ordina per `created_at` ascendente, pagina |
| `patch_registration(id, data)` | REQ-REG-04, F01, F02, B07 | applica la transizione di stato consentita |
| `delete_registration(id)` | REQ-REG-05 | rimuove fisicamente il record; libera il posto se era `confirmed` |
| `get_stats(event_id)` | REQ-REG-07, B08, B09 | conta le iscrizioni `confirmed` per l'evento e legge `capacity` da `event-service` |

#### Ordine di valutazione in `create_registration` (REQ-REG-01 AC7)

Le condizioni sono valutate **in sequenza**, arrestandosi alla prima che fallisce, così
come richiesto da REQ-REG-01 AC7:

```python
def create_registration(self, raw_body: str | None) -> Registration:
    data = self._parse_json(raw_body)                 # 1. malformed JSON → 400 MALFORMED_JSON
    self._validate_fields(data)                        # 2. campi/unknown fields → 422 VALIDATION_ERROR (REQ-REG-F01/F02)

    self.user_client.get_user(data["user_id"])          # 3. REQ-REG-B01 → 422 REFERENCE_NOT_FOUND | 503

    event = self.event_client.get_event(data["event_id"])  # 4. REQ-REG-B02 → 422 REFERENCE_NOT_FOUND | 503
    self._check_published(event)                        # 5. REQ-REG-B03 → 422 EVENT_NOT_OPEN

    self._check_not_already_registered(data["user_id"], data["event_id"])  # 6. REQ-REG-B04 → 409 ALREADY_REGISTERED

    with self._capacity_lock(data["event_id"]):          # 7. REQ-REG-B05 → 409 EVENT_FULL (sezione dedicata sotto)
        confirmed_count = self.repository.count_confirmed_by_event(data["event_id"])
        if confirmed_count >= event["capacity"]:
            raise EventFull(data["event_id"])
        registration = Registration.create(
            data["user_id"], data["event_id"], amount=event["price"]  # REQ-REG-B06
        )
        self.repository.save(registration)

    return registration
```

Le chiamate a `user_client.get_user` ed `event_client.get_event` sollevano
direttamente `ReferenceNotFound` o `DependencyUnavailable`: la route non deve
distinguere se l'errore viene dalla dipendenza utente o evento, perché entrambe le
eccezioni portano già il nome del campo (`user_id` / `event_id`) da riportare in
`details`.

**Eccezioni di dominio** (catturate nelle route, mai propagate a Flask):

| Eccezione | Status | Code |
|---|---|---|
| `MalformedJson` | 400 | `MALFORMED_JSON` |
| `ValidationError(field, message)` | 422 | `VALIDATION_ERROR` |
| `ReferenceNotFound(field, value)` | 422 | `REFERENCE_NOT_FOUND` |
| `EventNotOpen(event_id, status)` | 422 | `EVENT_NOT_OPEN` |
| `AlreadyRegistered(user_id, event_id)` | 409 | `ALREADY_REGISTERED` |
| `EventFull(event_id)` | 409 | `EVENT_FULL` |
| `InvalidStatusTransition(current, requested)` | 422 | `INVALID_STATUS_TRANSITION` |
| `DependencyUnavailable(service_name)` | 503 | `DEPENDENCY_UNAVAILABLE` |
| `NotFound` | 404 | `NOT_FOUND` |

#### Controllo di capienza sotto concorrenza (REQ-REG-B05 AC4)

Il processo Flask è mono-processo (nessun deploy multi-worker previsto da
`services.yaml`), ma può comunque ricevere richieste concorrenti su thread diversi
(il dev server di Flask può servire richieste in parallelo). La sequenza
"leggi conteggio confermate → confronta con `capacity` → crea" è un classico
check-then-act: senza serializzazione, due richieste concorrenti per l'ultimo posto
potrebbero entrambe leggere `confirmed_count < capacity` e creare due iscrizioni,
violando l'invariante.

Strategia adottata, uguale per tutti i backend e trasparente al resto di `domain/`:

- **Lock in-process per `event_id`** in `RegistrationService`: un
  `threading.Lock` per evento (mantenuto in un dizionario `dict[str, threading.Lock]`
  interno al servizio, creato pigramente e protetto da un lock globale sulla mappa
  stessa) serializza l'intera sezione "conta confermate → confronta → crea" per lo
  stesso `event_id`, indipendentemente dal backend di persistenza:

```python
class RegistrationService:
    def __init__(self, repository, user_client, event_client):
        ...
        self._event_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _capacity_lock(self, event_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._event_locks.setdefault(event_id, threading.Lock())
```

- Questo copre `memory` e `json` (dove non esiste un meccanismo di transazione nativo
  utilizzabile in sicurezza dal solo `json`/`sqlite3` di libreria standard senza
  introdurre un DBMS esterno) con un unico meccanismo semplice, verificabile con un
  test che simula richieste concorrenti (thread) sull'ultimo posto disponibile.
- Per `sqlite`, il lock in-process è comunque la barriera primaria (un solo processo
  Flask accede al file), ma `SqliteRegistrationRepository.save_if_capacity_available`
  esegue in aggiunta l'inserimento dentro una singola transazione SQLite
  (`BEGIN IMMEDIATE` → `SELECT COUNT(*) ... WHERE status='confirmed'` →
  `INSERT` → `COMMIT`), così l'invariante resta valida anche se in futuro il servizio
  venisse eseguito con più processi che condividono lo stesso file SQLite.
- Il lock è a grana fine (per singolo `event_id`), quindi richieste concorrenti su
  eventi diversi non si bloccano a vicenda.

Questa strategia è interna a `domain/` (e all'implementazione SQLite del
repository) e non richiede alcuna modifica alle route o al contratto: soddisfa
REQ-REG-B05 AC4 mantenendo il cambio di backend trasparente per la business logic
(REQ-REG-F06).

### `app/clients/user_client.py`

Punto del servizio che chiama `requests` verso `user-service`. Incapsula URL, timeout
e traduzione degli esiti in eccezioni di dominio (REQ-REG-B01, REQ-REG-B09).

```python
class UserClient:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self._base_url = base_url
        self._timeout = timeout

    def get_user(self, user_id: str) -> dict:
        """Ritorna il dict utente se esiste.

        Solleva:
          ReferenceNotFound     — user-service risponde 404
          DependencyUnavailable — timeout, connessione rifiutata, o 5xx
        """
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/users/{user_id}",
                timeout=self._timeout,
            )
        except (requests.Timeout, requests.ConnectionError):
            raise DependencyUnavailable("user-service")

        if resp.status_code == 404:
            raise ReferenceNotFound("user_id", user_id)
        if 500 <= resp.status_code < 600:
            raise DependencyUnavailable("user-service")
        return resp.json()
```

### `app/clients/event_client.py`

Punto del servizio che chiama `requests` verso `event-service`. Stessa struttura di
`user_client.py`, ma il dict ritornato viene riusato per **più** regole di business
(REQ-REG-B02, REQ-REG-B03, REQ-REG-B05, REQ-REG-B06, REQ-REG-B08): la chiamata
`GET /api/v1/events/{event_id}` viene eseguita **una sola volta per richiesta** e il
risultato passato a `_check_published`, al calcolo di `amount`, e al confronto con
`capacity`, evitando chiamate HTTP ripetute verso `event-service` nello stesso ciclo
di creazione o di calcolo delle statistiche.

```python
class EventClient:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self._base_url = base_url
        self._timeout = timeout

    def get_event(self, event_id: str) -> dict:
        """Ritorna il dict evento (con almeno status, price, capacity) se esiste.

        Solleva:
          ReferenceNotFound     — event-service risponde 404
          DependencyUnavailable — timeout, connessione rifiutata, 5xx,
                                   oppure risposta 2xx senza un campo `capacity`
                                   numerico valido (REQ-REG-07 AC4)
        """
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/events/{event_id}",
                timeout=self._timeout,
            )
        except (requests.Timeout, requests.ConnectionError):
            raise DependencyUnavailable("event-service")

        if resp.status_code == 404:
            raise ReferenceNotFound("event_id", event_id)
        if 500 <= resp.status_code < 600:
            raise DependencyUnavailable("event-service")

        event = resp.json()
        if not isinstance(event.get("capacity"), int):
            raise DependencyUnavailable("event-service")
        return event
```

`RegistrationService._check_published(event)` verifica `event["status"] == "published"`
e solleva `EventNotOpen` in caso contrario (REQ-REG-B03), mantenendo la regola di
business fuori dal client, così come in `event-service` la verifica del ruolo
`organizer` resta fuori da `user_client.py`.

Nei test unitari (`tests/unit/test_user_client.py`, `test_event_client.py` e
`test_domain.py`), le chiamate HTTP verso `user-service`/`event-service` sono mockate
con la libreria `responses` (vedi `tech.md`), così l'intera suite unitaria è eseguibile
senza avviare i servizi reali.

### `app/api/registrations.py`

Blueprint Flask. Ogni route:
1. Parsa il corpo JSON — body assente, vuoto o non valido → 400 `MALFORMED_JSON`
   (REQ-REG-F03), valutato **prima** della validazione di campo.
2. Chiama il metodo corrispondente di `RegistrationService`.
3. Cattura le eccezioni di dominio e le mappa al codice HTTP + formato errore standard
   (REQ-REG-F05).
4. Ritorna `jsonify(registration.to_dict()), 201/200/204`.

Mapping route → dominio:

| Metodo HTTP | Path | Metodo `RegistrationService` |
|---|---|---|
| POST | `/api/v1/registrations` | `create_registration` |
| GET | `/api/v1/registrations` | `list_registrations` |
| GET | `/api/v1/registrations/stats` | `get_stats` |
| GET | `/api/v1/registrations/<id>` | `get_registration` |
| PUT | `/api/v1/registrations/<id>` | — (nessuna chiamata al dominio: 405 diretto, REQ-REG-06) |
| PATCH | `/api/v1/registrations/<id>` | `patch_registration` |
| DELETE | `/api/v1/registrations/<id>` | `delete_registration` |
| GET | `/health` | risposta inline `{"status": "ok", "service": "registration-service"}` |

La route `/api/v1/registrations/stats` è registrata **prima** della route
parametrica `/api/v1/registrations/<id>` per evitare che Flask interpreti `stats`
come un valore di `{id}` (non essendo un UUID v4 valido, sarebbe comunque risolto come
404 da `get_registration`, ma l'ordine esplicito rende l'intento chiaro e coerente con
REQ-REG-07).

Il metodo PUT su `/api/v1/registrations/<id>` risponde sempre 405 con l'header `Allow`
contenente l'elenco dei metodi supportati sul path (`GET, PATCH, DELETE`), senza
invocare `RegistrationService` (REQ-REG-06).

### `app/api/errors.py`

Identico per struttura a `event-service`/`user-service`:

```python
def error_response(code: str, message: str, status: int, details: dict = None) -> Response
```

Costruisce il body standard `{"error": {"code": ..., "message": ..., "details": ...}}`
e ritorna un oggetto `Response` Flask con `Content-Type: application/json`
(REQ-REG-F05).

### `app/repository/base.py` — `RegistrationRepository` (ABC)

```python
class RegistrationRepository(ABC):
    def save(self, registration: Registration) -> None: ...
    def find_by_id(self, id: str) -> Registration | None: ...
    def list(
        self,
        user_id: str | None,
        event_id: str | None,
        status: str | None,
    ) -> list[Registration]: ...
    def delete(self, id: str) -> bool: ...                       # False se non esiste
    def count_confirmed_by_event(self, event_id: str) -> int: ...
    def has_confirmed_for(self, user_id: str, event_id: str) -> bool: ...
```

`has_confirmed_for` supporta direttamente REQ-REG-B04 (divieto di doppia iscrizione
confermata) senza che `domain/` debba caricare e scandire in memoria l'intera lista
delle iscrizioni per l'evento. `count_confirmed_by_event` supporta sia il controllo di
capienza (REQ-REG-B05) sia le statistiche (REQ-REG-B08).

L'ordinamento per `created_at` ascendente richiesto da REQ-REG-03 AC15 è applicato
dall'implementazione di `list()` di ciascun backend, in modo che il contratto
osservabile (ordine stabile prima della paginazione) sia identico tra i tre backend.

### `MemoryRegistrationRepository`

Dizionario `dict[str, Registration]` in-process. Nessuna dipendenza esterna.

### `JsonRegistrationRepository`

Legge/scrive `{DATA_DIR}/registrations.json`. Il file contiene
`{"registrations": [...]}`. Ogni scrittura ricarica e riscrive l'intero file. Crea
`DATA_DIR` se non esiste (REQ-REG-F06 AC5). Se il file non esiste ancora, tutte le
letture si comportano come se zero iscrizioni fossero presenti (REQ-REG-F06 AC7).

### `SqliteRegistrationRepository`

Database `{DATA_DIR}/registrations.db` con schema creato al primo avvio. Solo
`sqlite3` dalla libreria standard.

```sql
CREATE TABLE IF NOT EXISTS registrations (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    amount        TEXT NOT NULL,     -- stringa a 2 decimali, per evitare arrotondamenti float
    status        TEXT NOT NULL DEFAULT 'confirmed',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_registrations_event ON registrations(event_id, status);
CREATE INDEX IF NOT EXISTS idx_registrations_user_event ON registrations(user_id, event_id);
```

`count_confirmed_by_event` e `has_confirmed_for` sono implementati come `SELECT COUNT(*)`
con `WHERE event_id = ? AND status = 'confirmed'` (rispettivamente con l'aggiunta di
`AND user_id = ?`), sfruttando gli indici sopra. La variante usata da
`create_registration` sotto lock (`save_if_capacity_available`, vedi sezione
concorrenza) esegue conteggio e insert nella stessa transazione `BEGIN IMMEDIATE`.

### Factory `repository/__init__.py`

```python
def get_repository(backend: str, data_dir: str) -> RegistrationRepository:
    if backend == "json":   return JsonRegistrationRepository(data_dir)
    if backend == "sqlite": return SqliteRegistrationRepository(data_dir)
    if backend == "memory": return MemoryRegistrationRepository()
    raise ValueError(f"invalid STORAGE_BACKEND: {backend!r}")
```

Invocata una sola volta in `__main__.py`; il risultato, insieme a un'istanza di
`UserClient(USER_SERVICE_URL)` e a un'istanza di `EventClient(EVENT_SERVICE_URL)`,
viene iniettato in `RegistrationService`. Un valore di `STORAGE_BACKEND` non valido fa
terminare il processo prima del binding sulla porta (REQ-REG-F06 AC6).

---

## Data Models

### `Registration` (dataclass)

| Campo | Tipo Python | Note |
|---|---|---|
| `id` | `str` (UUID v4) | generato dal server con `uuid.uuid4()`, mai accettato in input |
| `user_id` | `str` (UUID v4) | validato via `user_client` prima della persistenza (REQ-REG-B01) |
| `event_id` | `str` (UUID v4) | validato via `event_client` prima della persistenza (REQ-REG-B02, B03) |
| `amount` | `Decimal` | copiato da `event.price` al momento della creazione; 2 decimali, EUR implicita; immutabile dopo la creazione (REQ-REG-B06) |
| `status` | `str` | `confirmed` \| `cancelled`; sempre `confirmed` alla creazione; modificabile solo via PATCH (REQ-REG-B07) |
| `created_at` | `datetime` (UTC) | immutabile dopo la creazione |
| `updated_at` | `datetime` (UTC) | aggiornato ad ogni PATCH riuscito |

`amount` è gestito come `Decimal` internamente per evitare errori di arrotondamento in
virgola mobile, e serializzato in JSON come numero con esattamente 2 decimali, copiato
verbatim dal `price` restituito da `event-service` nella stessa risposta usata per
validare `event_id` (REQ-REG-B06 AC1).

### Risposta paginata `RegistrationPage`

```json
{
  "items": [ { ...Registration... } ],
  "page": 1,
  "page_size": 20,
  "total": 57
}
```

Filtraggio e ordinamento applicati **prima** della paginazione (REQ-REG-03 AC12, AC15):

```
filtered = [r for r in all_registrations if matches(r, user_id, event_id, status)]
filtered.sort(key=lambda r: r.created_at)
total    = len(filtered)
offset   = (page - 1) * page_size
items    = filtered[offset : offset + page_size]
```

Vincoli: `page >= 1`, `1 <= page_size <= 100`; violazioni → `ValidationError`
(REQ-REG-03 AC3-5).

### `RegistrationStats`

```json
{
  "event_id": "e5b1...",
  "capacity": 200,
  "confirmed": 150,
  "available": 50
}
```

`capacity` è letto da `event-service` tramite `event_client.get_event(event_id)`,
`confirmed` da `repository.count_confirmed_by_event(event_id)`, `available` calcolato
come `max(capacity - confirmed, 0)` per non restituire mai un valore negativo
(REQ-REG-B08 AC3).

### Schema SQLite

Vedere sezione `SqliteRegistrationRepository` sopra. `amount` è salvato come `TEXT`
(stringa decimale) per preservare esattamente 2 decimali; tutti gli altri campi sono
`TEXT`; i timestamp sono stringhe ISO 8601 UTC.

---

## Error Handling

Tutti gli errori seguono il formato standard della piattaforma (REQ-REG-F05):

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "descrizione leggibile",
    "details": {}
  }
}
```

| Situazione | Status | `code` | Requisiti |
|---|---|---|---|
| JSON malformato o body vuoto nel POST/PATCH | 400 | `MALFORMED_JSON` | REQ-REG-F03, F05 |
| Campo obbligatorio mancante, formato non valido, campo sconosciuto o campo read-only in input | 422 | `VALIDATION_ERROR` | REQ-REG-F01, F02, F05 |
| `page`/`page_size` fuori range, o filtro `user_id`/`event_id`/`status` non valido | 422 | `VALIDATION_ERROR` | REQ-REG-03, F05 |
| `user_id` inesistente su `user-service` (404) | 422 | `REFERENCE_NOT_FOUND` | REQ-REG-B01, F05 |
| `event_id` inesistente su `event-service` (404) | 422 | `REFERENCE_NOT_FOUND` | REQ-REG-B02, F05 |
| Evento esistente ma non `published` | 422 | `EVENT_NOT_OPEN` | REQ-REG-B03, F05 |
| Utente già con una iscrizione `confirmed` per lo stesso evento | 409 | `ALREADY_REGISTERED` | REQ-REG-B04, F05 |
| Evento alla (o sopra la) capienza massima | 409 | `EVENT_FULL` | REQ-REG-B05, F05 |
| Transizione di `status` non consentita (stesso valore, o `cancelled → confirmed`) | 422 | `INVALID_STATUS_TRANSITION` | REQ-REG-B07, F05 |
| Iscrizione non trovata per `id`, o `id` non in formato UUID v4 | 404 | `NOT_FOUND` | REQ-REG-02, 04, 05, F05 |
| `event_id` inesistente su `/stats` | 404 | `NOT_FOUND` | REQ-REG-07, B08, F05 |
| Metodo HTTP non previsto sulla risorsa (incluso PUT su `/api/v1/registrations/{id}`) | 405 | `METHOD_NOT_ALLOWED` | REQ-REG-06, F03, F05 |
| Timeout (2s), connessione rifiutata, o risposta 5xx da `user-service`/`event-service` (inclusa risposta 2xx senza `capacity` numerico su `/stats`) | 503 | `DEPENDENCY_UNAVAILABLE` | REQ-REG-B09, F05 |

**Validazione dei campi** (in `domain/registration_service.py`, non nelle route):

| Campo | Regola |
|---|---|
| `user_id` (POST) | obbligatorio; stringa in formato UUID v4 canonico |
| `event_id` (POST) | obbligatorio; stringa in formato UUID v4 canonico |
| `status` (PATCH) | obbligatorio; valore in `{confirmed, cancelled}`; unico campo accettato |
| campi non definiti dallo schema (`RegistrationCreate`/`RegistrationPatch`) | rifiutati con `VALIDATION_ERROR` e identificazione del campo in `details` (REQ-REG-F02) |
| campi server-generated (`id`, `amount`, `status` in POST, `created_at`, `updated_at`) | sempre rifiutati se presenti in input (REQ-REG-F02) |

Ogni violazione di campo viene raccolta in un unico oggetto `details` per rispondere
con un solo 422 anche quando più campi falliscono contemporaneamente (REQ-REG-F01 AC5),
non fermandosi al primo errore. La malformed-JSON detection (criterio REQ-REG-F03 AC1)
è invece valutata **prima** di qualunque validazione di campo o regola di business
(REQ-REG-01 AC7, REQ-REG-F03 AC3).

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: La capienza dell'evento non viene mai superata, anche in concorrenza
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

Per qualunque evento con capienza `C` e qualunque sequenza (anche concorrente) di
richieste di creazione di iscrizioni per quell'evento, il numero di iscrizioni con
`status = confirmed` per quell'evento non supera mai `C` in nessun istante osservabile;
tra due o più richieste concorrenti che contendono l'ultimo posto disponibile, al più
una ottiene HTTP 201 e tutte le altre ottengono HTTP 409 `EVENT_FULL` (REQ-REG-B05
AC1-AC4).

### Property 2: Divieto di doppia iscrizione confermata
**Validates: Requirements 4.1, 4.2, 4.3**

Per qualunque coppia `(user_id, event_id)`, se esiste già una iscrizione con quella
coppia e `status = confirmed`, allora ogni ulteriore richiesta di creazione con la
stessa coppia viene rifiutata con HTTP 409 `ALREADY_REGISTERED` senza creare alcun
nuovo record; se invece la registrazione precedente per quella coppia ha
`status = cancelled`, una nuova richiesta con la stessa coppia può essere accettata
come record distinto, senza modificare il record cancellato (REQ-REG-B04 AC1-AC3).

### Property 3: `amount` è immutabile e coerente con il prezzo dell'evento al momento dell'iscrizione
**Validates: Requirements 6.1, 6.3**

Per qualunque iscrizione creata con successo, il valore di `amount` restituito in ogni
lettura successiva (GET singolo, lista, PATCH) è sempre identico al `price` restituito
da `event-service` nella risposta usata per validare `event_id` al momento della
creazione, indipendentemente da eventuali modifiche successive al `price` dell'evento
su `event-service` (REQ-REG-B06 AC1, AC3).

### Property 4: Le transizioni di stato seguono solo `confirmed → cancelled` e `cancelled` è terminale
**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

Per qualunque stato corrente `S` e qualunque stato richiesto `S'` in
`{confirmed, cancelled}`, la transizione `S → S'` viene accettata se e solo se
`S == "confirmed"` e `S' == "cancelled"`; per qualunque iscrizione il cui stato
corrente è `cancelled`, nessuna richiesta PATCH verso un valore diverso viene mai
accettata, e nessuna richiesta PATCH con `S' == S` viene mai accettata (REQ-REG-B07
AC1-AC4).

### Property 5: Le statistiche sono sempre coerenti con `confirmed` e `capacity`
**Validates: Requirements 8.1, 8.2, 8.3**

Per qualunque evento esistente e qualunque stato del sistema, la risposta di
`/api/v1/registrations/stats` soddisfa sempre
`available == max(capacity - confirmed, 0)` e `confirmed` è sempre uguale al numero di
iscrizioni con `status = confirmed` per quell'evento presenti nel repository nello
stesso istante; `available` non è mai negativo (REQ-REG-B08 AC1-AC3).

### Property 6: Dipendenze irraggiungibili producono sempre 503 senza effetti collaterali
**Validates: Requirements 9.1, 9.2, 9.3**

Per qualunque fallimento della chiamata a `user-service` o `event-service` durante la
creazione, l'aggiornamento di stato, o il calcolo delle statistiche (timeout dopo 2
secondi, connessione rifiutata, risposta con status in 500–599, o — solo per
`event-service` su `/stats` — risposta 2xx senza un campo `capacity` numerico valido),
la risposta è sempre HTTP 503 con codice `DEPENDENCY_UNAVAILABLE` e nessuna iscrizione
viene creata, modificata o cancellata come effetto di quella richiesta (REQ-REG-B09
AC1-AC3).

### Property 7: Intercambiabilità dei backend
**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

Per qualunque sequenza di operazioni CRUD equivalenti (create, read, update, delete),
lo stesso comportamento osservabile via API (stessi status code e stessi corpi di
risposta, a parte `id`/timestamp generati dal server) si ottiene indipendentemente dal
backend (`memory`, `json`, `sqlite`) configurato tramite `STORAGE_BACKEND` (REQ-REG-F06
AC1-AC4). Garantita dai test parametrizzati in `test_repository.py`.

---

## Testing Strategy

### Unit test (`tests/unit/`)

**`test_domain.py`** — testa `RegistrationService` in isolamento con
`MemoryRegistrationRepository` e stub/fake di `UserClient` ed `EventClient` (nessuna
chiamata HTTP reale):
- creazione valida (utente esistente, evento `published`, capienza disponibile) → 201,
  `amount` coerente con `price` dell'evento stub, `status = confirmed` (REQ-REG-01) →
  `@pytest.mark.req("REQ-REG-01")`
- utente inesistente (stub che solleva `ReferenceNotFound`) → 422
  `REFERENCE_NOT_FOUND` (REQ-REG-B01) → `@pytest.mark.req("REQ-REG-B01")`
- evento inesistente → 422 `REFERENCE_NOT_FOUND` (REQ-REG-B02) →
  `@pytest.mark.req("REQ-REG-B02")`
- evento `draft`/`cancelled` → 422 `EVENT_NOT_OPEN` (REQ-REG-B03) →
  `@pytest.mark.req("REQ-REG-B03")`
- doppia iscrizione confermata → 409 `ALREADY_REGISTERED`; iscrizione dopo una
  cancellazione precedente per la stessa coppia → accettata come record distinto
  (REQ-REG-B04) → `@pytest.mark.req("REQ-REG-B04")`
- **property test sulla capienza (Property 1)**: usando una libreria di
  property-based testing per Python (`hypothesis`), per capienze `C` generate
  casualmente (1–20) e un numero di richieste concorrenti generato casualmente
  (`C` a `C+10`), lanciate su più thread contro lo stesso `MemoryRegistrationRepository`
  con `event_client` stub a capienza `C`, il test asserisce che il numero finale di
  iscrizioni `confirmed` sia esattamente `min(richieste, C)` e che ogni richiesta
  eccedente riceva `EventFull`; minimo 100 iterazioni — tag **Feature:
  registration-service, Property 1: la capienza dell'evento non viene mai superata,
  anche in concorrenza** → `@pytest.mark.req("REQ-REG-B05")`
- **property test sulle transizioni di stato (Property 4)**: lo spazio degli stati è
  finito (`{confirmed, cancelled}`), quindi la copertura universale richiesta dalla
  Property 4 è ottenuta per **enumerazione esaustiva** con `@pytest.mark.parametrize`
  su tutte le 4 coppie del prodotto cartesiano `{confirmed, cancelled} ×
  {confirmed, cancelled}`, senza necessità di una libreria generativa: per ciascuna
  coppia `(current, requested)` il test asserisce che la transizione è accettata se e
  solo se `(current, requested) == ("confirmed", "cancelled")` (REQ-REG-B07) → tag
  **Feature: registration-service, Property 4: le transizioni di stato seguono solo
  confirmed→cancelled e cancelled è terminale**
- **property test su `amount` immutabile (Property 3)**: con `hypothesis`, per prezzi
  evento generati casualmente (0.00–9999.99, 2 decimali) e sequenze generate
  casualmente di letture/aggiornamenti di stato successivi alla creazione, il test
  asserisce che `amount` osservato in ogni lettura resta identico al `price` letto al
  momento della creazione, anche modificando il `price` restituito dallo stub di
  `EventClient` dopo la creazione; minimo 100 iterazioni — tag **Feature:
  registration-service, Property 3: amount è immutabile e coerente con il prezzo
  dell'evento al momento dell'iscrizione** → `@pytest.mark.req("REQ-REG-B06")`
- **property test sulle statistiche (Property 5)**: con `hypothesis`, per capienze e
  numeri di iscrizioni `confirmed`/`cancelled` generati casualmente, il test asserisce
  `available == max(capacity - confirmed, 0)` e che `available` non sia mai negativo;
  minimo 100 iterazioni — tag **Feature: registration-service, Property 5: le
  statistiche sono sempre coerenti con confirmed e capacity** →
  `@pytest.mark.req("REQ-REG-B08")`
- dipendenza irraggiungibile (stub che solleva `DependencyUnavailable`) durante
  creazione, patch (n/a, PATCH non chiama le dipendenze) e stats → 503
  `DEPENDENCY_UNAVAILABLE` senza effetti collaterali (Property 6) (REQ-REG-B09) →
  `@pytest.mark.req("REQ-REG-B09")`
- paginazione: offset e slice corretti dopo ordinamento per `created_at`; `page_size
  > 100` → `ValidationError` (REQ-REG-03)
- filtri combinati `user_id`/`event_id`/`status` in AND (REQ-REG-03)
- DELETE: seconda delete → `NotFound`; delete di iscrizione `confirmed` libera un
  posto per una successiva creazione (REQ-REG-05, B05 AC3)

**`test_user_client.py`** — testa `UserClient` in isolamento usando `responses` per
mockare le chiamate HTTP verso `user-service` (nessuna istanza reale avviata, come
richiesto da `tech.md`):
- 200 → dict utente ritornato
- 404 → `ReferenceNotFound`
- timeout (`responses.add(..., body=Timeout)`) → `DependencyUnavailable`
- `ConnectionError` simulato → `DependencyUnavailable`
- 500/502/503 → `DependencyUnavailable`

**`test_event_client.py`** — stessa struttura di `test_user_client.py`, applicata a
`EventClient` verso `event-service`:
- 200 con `capacity` numerico → dict evento ritornato
- 200 senza `capacity` valido → `DependencyUnavailable` (REQ-REG-07 AC4)
- 404 → `ReferenceNotFound`
- timeout / `ConnectionError` / 5xx → `DependencyUnavailable`

**`test_repository.py`** — testa tutti e tre i backend con `tmp_path`. Test
parametrizzati su `[MemoryRegistrationRepository, JsonRegistrationRepository(tmp_path),
SqliteRegistrationRepository(tmp_path)]`. Per ogni backend: `save` → `find_by_id`,
`list` con filtri `user_id`/`event_id`/`status`, `count_confirmed_by_event`,
`has_confirmed_for`, `delete`. Per la Property 7 (intercambiabilità dei backend) un
test pytest applica la stessa sequenza fissa e scritta a mano di operazioni CRUD (es.
`save` di 3 iscrizioni con `user_id`/`event_id`/`status` diversi, `list` con filtro
`event_id`, `list` con filtro `status`, `count_confirmed_by_event` su uno degli
eventi, `delete` di una iscrizione, `find_by_id` sull'iscrizione eliminata) a ciascuno
dei tre backend in turno, e asserisce che il risultato osservabile sia identico per
tutti e tre; il test è parametrizzato con `@pytest.mark.parametrize` su 2 sequenze
fisse distinte per ampliare la copertura senza ricorrere a una libreria generativa
(REQ-REG-F06) — tag **Feature: registration-service, Property 7: intercambiabilità
dei backend**.

**`test_api_registrations.py`** — testa le route Flask con `app.test_client()`
(backend memory, `UserClient` ed `EventClient` mockati con `responses`):
- almeno 1 chiamata a `assert_matches_contract` per endpoint (contratto OpenAPI,
  `contracts/validator.py`), inclusi `GET /api/v1/registrations/stats` e
  `PUT /api/v1/registrations/{id}`
- header `Location` su 201
- 400 su JSON malformato
- 422 su campo mancante / formato non valido / campo sconosciuto / campo read-only
- 422 `REFERENCE_NOT_FOUND` con `user-service` mockato a 404
- 422 `REFERENCE_NOT_FOUND` con `event-service` mockato a 404
- 422 `EVENT_NOT_OPEN` con `event-service` mockato a 200 e `status != published`
- 409 `ALREADY_REGISTERED` su doppia iscrizione confermata
- 409 `EVENT_FULL` con capienza esaurita
- 422 `INVALID_STATUS_TRANSITION` su transizione non consentita in PATCH
- 503 `DEPENDENCY_UNAVAILABLE` con `user-service`/`event-service` mockati in
  timeout/5xx (creazione e `/stats`)
- 404 su `id` inesistente o non-UUID (GET, PATCH, DELETE)
- 404 su `event_id` inesistente su `/stats`
- 405 su `PUT /api/v1/registrations/{id}` e su metodi non previsti sulla collection
- 200 con `RegistrationStats` coerente su `/stats`
- filtri `user_id`/`event_id`/`status` combinati su GET lista

**Coverage target:** ≥ 80% su `app/` con `pytest --cov=app`.

### Integration test (`tests/integration/`)

Come `event-service`, la suite di integrazione **propria** di `registration-service`
avvia entrambe le dipendenze reali come sottoprocessi (`subprocess.Popen`, fixture
`autouse` di scope `session`) — `user-service` ed `event-service` — oltre a
`registration-service` stesso, tutti su porte libere e con `STORAGE_BACKEND=memory`,
per verificare il comportamento end-to-end senza mock (Exam.MD §6.3):

- **caso positivo**: crea un utente reale su `user-service`, crea un organizzatore e
  un evento `published` con capienza ≥ 1 su `event-service`, poi crea una
  registrazione con quel `user_id`/`event_id` su `registration-service` → 201,
  `amount` coerente con il `price` dell'evento, e la registrazione è successivamente
  leggibile con GET e conteggiata in `/stats`.
- **caso `REFERENCE_NOT_FOUND`**: crea una registrazione con un `event_id` (UUID v4)
  inesistente su `event-service` → 422 `REFERENCE_NOT_FOUND`.
- **caso `DEPENDENCY_UNAVAILABLE`**: termina il sottoprocesso di `event-service` (o
  non lo avvia per quel test) e tenta di creare una registrazione → 503
  `DEPENDENCY_UNAVAILABLE`.

I processi vengono terminati nella fixture `autouse` di scope `session` al termine
della sessione di test.

### Comando singolo per tutti i test del servizio

```bash
pytest services/registration-service/tests --cov=app
```
