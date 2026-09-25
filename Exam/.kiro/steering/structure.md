# Structure — organizzazione del codice

> Bozza di partenza generata a partire dalle domande guida del §7 della traccia.
> **Da rivedere e adattare prima di considerarla definitiva**: queste scelte sono
> valutate come parte della spec, quindi vanno motivate con le proprie parole e
> rispettate in modo coerente in tutti i servizi che verranno implementati.

## Repository e confini dei servizi

- **Un unico repository** (il fork di `techconf-exam`) con **una cartella per
  servizio** sotto `services/`, coerente con `services.example.yaml`:
  ```
  services/
    user-service/
    event-service/
    registration-service/
    feedback-service/        # opzionale
    notification-service/    # opzionale
  ```
- Vantaggio di un repo unico: un solo `git log` mostra l'intera sequenza
  spec → task → codice richiesta dalla traccia, e la suite di collaudo (che gira dalla
  root) trova tutto senza configurazione aggiuntiva. Svantaggio: i servizi non sono
  versionati/rilasciabili in modo indipendente — accettabile per un esame a servizio
  singolo/individuale, meno per un contesto multi-team reale.
- Il confine tra servizi è reso esplicito dalla cartella: ogni `services/<nome>-service/`
  è **autocontenuta** (proprio codice applicativo, propri test, proprie dipendenze).
  Aggiungere feedback-service o notification-service significa aggiungere una nuova
  cartella allo stesso livello, senza toccare le altre.
- **Un servizio non importa mai codice di un altro servizio.** Il confine è imposto
  organizzativamente (nessun path di import che attraversi `services/*/`) e, se serve,
  verificabile con un linter/hook che blocca import cross-service.

## Codice condiviso e duplicazione

- Il formato degli errori, la paginazione e la validazione sono **regole**, definite
  una volta in `platform-standards.md` (steering) e **reimplementate in ciascun
  servizio**, non centralizzate in una libreria condivisa importata a runtime.
  Motivo: evitare che i 3–5 servizi dipendano da un pacchetto interno comune, cosa che
  introdurrebbe accoppiamento di versione e renderebbe più difficile lo sviluppo da
  parte di team diversi in futuro. Il costo è una piccola duplicazione di codice
  (poche decine di righe per servizio), accettabile alla scala di questo progetto.
- Il **client HTTP verso gli altri servizi** è invece incapsulato in un modulo dedicato
  dentro ciascun servizio (es. `clients/user_client.py`), non condiviso tra servizi:
  ogni servizio conosce solo i client verso le proprie dipendenze dichiarate nella
  tabella del §2.

## Struttura interna di un servizio

Ogni `services/<nome>-service/` separa quattro responsabilità:

```
services/user-service/
  app/
    api/          # route Flask, parsing/validazione della request, mapping errori → status code
    domain/        # regole di business (REQ-*-B*), indipendenti da Flask e dal backend dati
    repository/    # accesso ai dati, un'implementazione per backend (memory/json/sqlite)
    clients/       # chiamate HTTP verso altri servizi (solo dove previsto, es. event → user)
  tests/
    unit/
    integration/
  requirements.txt
```

- Le regole `REQ-*-B*` vivono in `domain/`, mai nelle route: le route chiamano il
  dominio e traducono il risultato (o l'eccezione) in status code/JSON.
- Il passaggio `memory` → `json` → `sqlite` non tocca `domain/` perché tutti i backend
  implementano la stessa interfaccia di repository (stessi metodi, stessa firma); solo
  `repository/` cambia.
- Le chiamate agli altri servizi passano sempre da `clients/`, mai da `requests`
  chiamato direttamente nelle route o nel dominio: questo è ciò che permette di
  mockarle con `responses` nei test unitari senza avviare i servizi reali.

## Configurazione e avvio

- Ogni servizio legge `PORT`, `*_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR` in **un
  solo punto** (es. `app/config.py`), letto una volta all'avvio; il resto del codice
  riceve questi valori già risolti, non rilegge le variabili d'ambiente sparse nel
  codice.
- Comando di avvio uguale per tutti i servizi in `services.yaml`: `python -m app`,
  con `cwd: services/<nome>-service`.
- Un **file di dipendenze per servizio** (`requirements.txt` dentro ogni cartella),
  non un unico ambiente condiviso: se in futuro un servizio avesse bisogno di una
  versione diversa di una libreria, non blocca gli altri.

## Test

- Test unitari e di integrazione **vicino al codice del servizio**
  (`services/<nome>-service/tests/`), non in una cartella centrale: chi lavora su un
  servizio trova subito i suoi test, e `pytest services/<nome>-service/tests` esegue
  solo quelli.
- I test di integrazione **propri** (diversi dalla suite di collaudo del docente) usano
  una fixture pytest che avvia i servizi reali coinvolti su porte libere (es. con
  `subprocess.Popen`) prima dei test e li termina alla fine della sessione.
- Comando singolo per i test di un servizio: `pytest services/<nome>-service/tests
  --cov=app`. Per l'intera piattaforma: uno script/task che itera su ogni cartella
  `services/*/` (es. `Makefile` o script Python nella root).

## Spec e tracciabilità

- **Una spec Kiro per servizio** (`.kiro/specs/<nome>-service/`), non per singola
  funzionalità: coincide con il confine di deploy/avvio (`services.yaml`) e con la
  cartella del codice, rendendo immediato passare da spec a codice e viceversa.
- Da un requisito come `REQ-REG-B05` si risale al codice cercando l'ID nei commenti/
  docstring del modulo `domain/` corrispondente e nel nome del test unitario
  (`test_req_reg_b05_*` o marker `@pytest.mark.req("REQ-REG-B05")`).
- `structure.md` (questo file) contiene le regole valide per **tutto il repository**
  (come sono organizzate le cartelle, dove vive cosa); `design.md` di ogni servizio
  contiene le decisioni **specifiche di quel servizio** (es. quali campi valida,
  quali client HTTP usa, quali casi d'errore gestisce) assumendo come dato questo file.

## Dati e Git

- I file di dati generati dai backend `json`/`sqlite` finiscono in
  `services/<nome>-service/data/` (da `DATA_DIR`), **esclusa da `.gitignore`** a
  livello di root (`services/*/data/`).
- Commit convenzionali nell'ordine richiesto dalla traccia: `spec(<svc>): requirements`
  → `spec(<svc>): design` → `spec(<svc>): tasks` → una serie di `feat(<svc>): <task>
  [T-NN]` (uno per task eseguito), così la sequenza spec → task → codice è leggibile
  direttamente dal `git log` senza bisogno di altra documentazione.
