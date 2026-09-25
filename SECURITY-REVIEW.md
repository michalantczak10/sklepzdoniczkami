# Przegląd backupu i odtwarzania

Workflow backupu szyfruje zrzut bazy algorytmem AES-256-CBC z PBKDF2, a
następnie zapisuje HMAC-SHA256 i identyfikator klucza HMAC w artefakcie.
Workflow restore weryfikuje HMAC przed odszyfrowaniem formatu CBC.

## Wymagane zabezpieczenia operacyjne

- `DATABASE_URL`, `DATABASE_URL_STAGING`, `BACKUP_ENCRYPTION_KEY` i
  `BACKUP_HMAC_KEY` przechowuj jako sekrety GitHub Actions, nie w repozytorium.
- Backupy są artefaktami GitHub Actions z retencją 90 dni; nie zastępują
  długoterminowej, niezależnej kopii zapasowej.
- `restore-staging.yml` nadpisuje zawartość wskazanej bazy staging. Przed
  ręcznym uruchomieniem sprawdź `DATABASE_URL_STAGING`.
- Nie uruchamiaj testów ani workflowów na produkcyjnej bazie, jeśli wykonują
  zapisy lub odtwarzanie.
