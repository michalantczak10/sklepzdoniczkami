# Backup produkcyjnej bazy i środowisko preprod

Workflow backupu szyfruje zrzut bazy algorytmem AES-256-CBC z PBKDF2, a
następnie zapisuje HMAC-SHA256 i identyfikator klucza HMAC w artefakcie.
Nie ma workflowu odtwarzającego backup produkcyjny na preprod: tam trafiają
wyłącznie syntetyczne rekordy katalogu tworzone przez `seed_preprod_data`.

## Wymagane zabezpieczenia operacyjne

- `DATABASE_URL_PRODUCTION_BACKUP`, `BACKUP_ENCRYPTION_KEY` i
  `BACKUP_HMAC_KEY` przechowuj jako sekrety środowiska GitHub `production`;
  workflow backupu używa roli read-only, a nie poświadczeń aplikacji.
- Produkcja i preprod muszą wskazywać odrębne bazy Neon. Preprod wymaga bazy
  `sklepzdoniczkami_preprod`, a produkcja `sklepzdoniczkami_prod`; aplikacja
  odrzuci URL do bazy o innej nazwie.
- Render preprod używa wyłącznie `DATABASE_URL_PREPROD` jako roli
  `sklepzdoniczkami_preprod_web_limited`. `DATABASE_URL_PREPROD_MIGRATE` jako
  `sklepzdoniczkami_preprod_migrate_limited` przechowuj w GitHub Environment
  `preprod`, ograniczonym deployment branch do `dev`, i udostępniaj wyłącznie
  jobowi migracji na push do `dev`; nigdy procesowi web ani pull-requestom.
  Nie zapisuj URL-i w Git.
- Nie kopiuj produkcyjnych zrzutów do preprod; nie używaj tam starych URL-i ani
  danych z poprzedniego środowiska staging.
- Backupy są artefaktami GitHub Actions z retencją 90 dni; nie zastępują
  długoterminowej, niezależnej kopii zapasowej.
- Nie uruchamiaj testów ani workflowów na produkcyjnej bazie, jeśli wykonują
  zapisy lub odtwarzanie.
