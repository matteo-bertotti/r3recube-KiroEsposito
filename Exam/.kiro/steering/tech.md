# Tech — TechConf

## Linguaggio e runtime

- **Python 3.12**

## Dipendenze runtime

- **Flask** — framework HTTP per ogni microservizio.
- **requests** — client HTTP per le chiamate tra microservizi (con **timeout di 2s**,
  vedi `platform-standards.md`).

## Dipendenze di test

- **pytest** — test runner.
- **pytest-cov** — misura della coverage (soglia minima 80% per servizio, `pytest --cov=app`).
- **responses** — mock delle chiamate HTTP in uscita (`requests`) nei test unitari, per
  simulare le risposte degli altri servizi senza avviarli davvero.

## Persistenza

Variabile d'ambiente **`STORAGE_BACKEND`**, tre valori possibili:

| Valore | Comportamento |
|---|---|
| `memory` (default) | dati tenuti in strutture Python in-process, persi al riavvio |
| `json` | dati salvati come file JSON in `DATA_DIR` (default `./data`) |
| `sqlite` | dati salvati in un database SQLite in `DATA_DIR` (default `./data`) |

Vincolo: **solo librerie standard** (`json`, `sqlite3`) — nessun DBMS esterno da
installare o configurare, nessun ORM di terze parti. Il cambio di backend **non deve
richiedere modifiche alla logica di business**: l'accesso ai dati va isolato dietro
un'interfaccia comune (repository) implementata una volta per ciascun backend.

## Configurazione via variabili d'ambiente

- `PORT` — porta su cui il servizio deve ascoltare (obbligatoria, mai hardcoded).
- `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL` (e, per i servizi
  bonus, `FEEDBACK_SERVICE_URL` / `NOTIFICATION_SERVICE_URL`) — URL degli altri
  servizi, default `http://localhost:<porta di sviluppo>`.
- `STORAGE_BACKEND` — vedi sopra.
- `DATA_DIR` — cartella per i file di persistenza `json`/`sqlite`, esclusa da git.

## Avvio e collaudo

- Ogni servizio è avviato come processo Python indipendente (nessun container), tramite
  il comando dichiarato in `services.yaml` (`cwd` + `command`).
- La suite di collaudo (`tests/integration/`, non modificabile) usa le porte
  15001–15005 in fase di test, quelle 5001–5005 sono per lo sviluppo locale.
