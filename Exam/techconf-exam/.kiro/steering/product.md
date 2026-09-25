# Product — TechConf

## Dominio

TechConf è una piattaforma a microservizi per la gestione delle iscrizioni a conferenze
tecniche (cloud, AI, security) organizzate da una società di eventi.

## Entità principali

- **Utente** — partecipante, speaker o organizzatore della piattaforma.
- **Evento** — una conferenza con un ciclo di vita (`draft` → `published` → `cancelled`),
  una capienza massima e un prezzo.
- **Iscrizione** — collega un utente a un evento pubblicato; rispetta la capienza
  dell'evento e può essere cancellata per liberare un posto.
- **Feedback** *(opzionale)* — valutazione (1–5) lasciata da un utente iscritto a un
  evento già concluso o in corso.
- **Notifica** *(opzionale)* — comunicazione (email/sms/push) inviata a un utente,
  anche in massa (broadcast) a tutti gli iscritti confermati di un evento.

## Servizi e scopo

| Servizio | Scopo | Dipende da |
|---|---|---|
| **user-service** | anagrafica utenti: creazione, lettura, modifica, cancellazione | — |
| **event-service** | gestione eventi e loro ciclo di vita; valida che l'organizzatore esista e abbia ruolo `organizer` | user-service |
| **registration-service** | iscrizioni degli utenti agli eventi; applica le regole di capienza e di stato dell'evento | user-service, event-service |
| **feedback-service** *(bonus)* | raccolta valutazioni degli eventi da parte di chi vi ha partecipato | registration-service, event-service |
| **notification-service** *(bonus)* | invio (simulato) di notifiche singole o broadcast agli iscritti | user-service, registration-service |

## Comunicazione tra servizi

I servizi dialogano **solo via HTTP/REST**, mai tramite accesso diretto ai dati di un
altro servizio. Ogni servizio è responsabile esclusivamente dei propri dati; se ha
bisogno di verificare un'informazione posseduta da un altro servizio (es. che un
`user_id` esista, che un evento sia `published`), lo fa con una chiamata HTTP al
servizio competente, mai duplicando o assumendo quel dato.

## Fuori scope

- Autenticazione/autorizzazione degli utenti (non richiesta dalla traccia).
- Pagamenti reali (il campo `price`/`amount` è puramente informativo).
- Invio reale di email/SMS/push (il notification-service simula l'invio).
