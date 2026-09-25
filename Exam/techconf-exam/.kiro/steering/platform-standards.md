# Platform Standards — vincolanti per tutti i servizi

Queste regole si applicano identiche a **tutti** i microservizi di TechConf (obbligatori
e opzionali). Sono la fonte di verità per ogni `requirements.md` e `design.md`.

## Avvio del servizio

- Un file `services.yaml` nella root del repository dichiara, per ogni servizio
  implementato, la cartella di lavoro (`cwd`) e il comando di avvio (`command`).
- La suite di collaudo legge `services.yaml` e, all'avvio di ogni servizio, passa le
  variabili d'ambiente `PORT` e `*_SERVICE_URL`.
- Ogni servizio **deve** ascoltare sulla porta indicata da `PORT` — mai una porta fissa
  nel codice.

## Base path e formato

- Base path: `/api/v1/<risorsa>` (es. `/api/v1/users`).
- Formato dati: **JSON**, campi in **snake_case**.

## Identificativi e timestamp

- `id`: **UUID v4**, generato dal server. Non è mai accettato in input dal client.
- Timestamp: **ISO 8601 UTC** (es. `2026-10-15T09:30:00Z`).
- Ogni risorsa espone `created_at` e `updated_at` (read-only, generati/aggiornati dal
  server).

## Date e importi

- Date in formato `YYYY-MM-DD`.
- Importi numerici con **2 decimali** (es. `149.00`), valuta implicita **EUR**.

## Paginazione

Query string: `?page=1&page_size=20` (`page_size` massimo 100).

Risposta:
```json
{"items": [...], "page": 1, "page_size": 20, "total": 57}
```

## Formato degli errori

Sempre:
```json
{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}
```

## Status code

| Codice | Quando |
|---|---|
| 201 | creazione (con header `Location`) |
| 200 | lettura o modifica riuscita |
| 204 | cancellazione riuscita |
| 400 | JSON malformato |
| 404 | risorsa non trovata → codice errore `NOT_FOUND` |
| 405 | metodo HTTP non previsto sulla risorsa |
| 409 | conflitto (es. duplicato, capienza esaurita) |
| 422 | `VALIDATION_ERROR` / `REFERENCE_NOT_FOUND` / violazione di una regola di business |
| 503 | `DEPENDENCY_UNAVAILABLE` — dipendenza esterna irraggiungibile |

## Chiamate tra servizi

- L'URL di ogni servizio dipendenza viene **sempre** letto da variabile d'ambiente
  (`USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL`, ecc.), **mai**
  scritto nel codice. Default: `http://localhost:<porta di sviluppo>`.
- Timeout per ogni chiamata HTTP verso un altro servizio: **2 secondi**.
- Se il servizio chiamato risponde **404** → il servizio chiamante risponde **422**
  `REFERENCE_NOT_FOUND`.
- Se la chiamata va in **timeout**, la connessione è **rifiutata**, o il servizio
  chiamato risponde con un **5xx** → il servizio chiamante risponde **503**
  `DEPENDENCY_UNAVAILABLE`.

## Health check

`GET /health` → `200 {"status": "ok", "service": "<nome-servizio>"}`

## Persistenza

- Variabile `STORAGE_BACKEND`: `memory` (default) · `json` · `sqlite`.
- Con `json`/`sqlite`, i file di dati vanno in `DATA_DIR` (default `./data`),
  **esclusa da git**.
- Solo librerie standard (`json`, `sqlite3`): **nessun DBMS esterno** da installare o
  configurare.
- Il cambio di backend **non deve mai richiedere modifiche alla logica di business**.

## Dipendenze Python

- Runtime: `flask`, `requests`.
- Test: `pytest`, `pytest-cov`, `responses`.
