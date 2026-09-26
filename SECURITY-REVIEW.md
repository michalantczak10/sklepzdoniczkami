# Backup produkcyjnej bazy i środowisko preprod

Workflow backupu szyfruje zrzut bazy algorytmem AES-256-CBC z PBKDF2, a
następnie zapisuje HMAC-SHA256 i identyfikator klucza HMAC w artefakcie.
Nie ma workflowu odtwarzającego backup produkcyjny na preprod: tam trafiają
wyłącznie syntetyczne rekordy katalogu tworzone przez `seed_preprod_data`.

## Wymagane zabezpieczenia operacyjne

- `DATABASE_URL_PRODUCTION` przechowuj w sekrecie środowiska GitHub
  `production`; `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY` są sekretami
  repozytorium używanymi tylko przez workflow backupu.
- Produkcja i preprod muszą wskazywać odrębne bazy Neon. Preprod wymaga bazy
  `sklepzdoniczkami_preprod` i aplikacja odrzuci URL do bazy o innej nazwie.
- Nie kopiuj produkcyjnych zrzutów do preprod; nie używaj tam starych URL-i ani
  danych z poprzedniego środowiska staging.
- Backupy są artefaktami GitHub Actions z retencją 90 dni; nie zastępują
  długoterminowej, niezależnej kopii zapasowej.
- Nie uruchamiaj testów ani workflowów na produkcyjnej bazie, jeśli wykonują
  zapisy lub odtwarzanie.
