# Backup produkcyjnej bazy i środowisko preprod

Workflow backupu szyfruje zrzut bazy algorytmem AES-256-CBC z PBKDF2, a
następnie zapisuje HMAC-SHA256 i identyfikator klucza HMAC w artefakcie.
Nie ma workflowu odtwarzającego backup produkcyjny na preprod: tam trafiają
wyłącznie syntetyczne rekordy katalogu tworzone przez `seed_preprod_data`.

## Wymagane zabezpieczenia operacyjne

- `DATABASE_URL_PRODUCTION_BACKUP` przechowuj jako sekret środowiska GitHub
  `production`; workflow backupu używa roli read-only, a nie poświadczeń
  aplikacji. Istniejące klucze `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY`
  pozostają repozytoryjnymi sekretami, aby zachować możliwość odczytu
  historycznych artefaktów; rotuj je dopiero po migracji tych kopii.
- Sekrety CI bazy deweloperskiej przechowuj wyłącznie w środowisku GitHub
  `development`, ograniczonym do branchy `main` i `dev`. Pull requesty używają
  pustego środowiska `ci-pr` i SQLite, więc nie otrzymują poświadczeń Neon.
- Przed zrzutem workflow wymaga bazy `sklepzdoniczkami_prod` oraz tabel
  `django_migrations` i `sklepzdoniczkami_product`; pusty lub błędnie wskazany
  cel backupu lub inny endpoint Neon kończy się błędem zamiast tworzyć
  pozornie prawidłowy artefakt. `PRODUCTION_DATABASE_HOST` w środowisku
  `production` musi wskazywać dedykowany endpoint branchu `prod`.
- Produkcja i preprod muszą wskazywać odrębne bazy Neon. Preprod wymaga bazy
  `sklepzdoniczkami_preprod`, a produkcja `sklepzdoniczkami_prod`; aplikacja
  odrzuci URL do bazy o innej nazwie.
- Nie kopiuj produkcyjnych zrzutów do preprod; nie używaj tam starych URL-i ani
  danych z poprzedniego środowiska staging.
- Backupy są artefaktami GitHub Actions z retencją 90 dni; nie zastępują
  długoterminowej, niezależnej kopii zapasowej.
- Nie uruchamiaj testów ani workflowów na produkcyjnej bazie, jeśli wykonują
  zapisy lub odtwarzanie.
