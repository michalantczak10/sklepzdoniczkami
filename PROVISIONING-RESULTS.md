# Wyniki automatycznego provisioningu Neon (podsumowanie)

Data: 2026-09-29 16:16:56

Co sprawdzono:
- .env: NEON_API_KEY znaleziony; STRIPE_SECRET_KEY_DEVELOPMENT znaleziony i zweryfikowany (Stripe API OK);
- DATABASE_URL_DEVELOPMENT był zmaskowany/niekompletny — brak możliwości połączenia;
- psql nie jest zainstalowane w tym środowisku, więc GRANTy nie mogły być zastosowane.

Działania wykonane automatycznie:
- Utworzono role na branchu `dev`: `sklepzdoniczkami_dev_ro`, `sklepzdoniczkami_dev_migrate` (hasła nie są zapisywane w repo).
- Próbowano wygenerować tymczasowy credential właściciela, lecz Neon API nie zwróciło plaintext connection_string / compute endpoint był nieaktywny — nie udało się zbudować pełnego DATABASE_URL.

Co wymaga ręcznej akcji (kolejność):
1. W Neon Console: aktywować compute dla branchu `dev` (udostępni host/endpoint).
2. W Neon Console: utworzyć (lub wyeksportować) credential właściciela i przekleić/ustawić pełny connection string (DATABASE_URL_DEVELOPMENT) w .env albo jako GitHub Secret.
3. Na maszynie z `psql`: uruchomić `neon_hardening.ps1` aby zastosować GRANTy (lub wykonać GRANTy ręcznie).

Uwagi:
- Nie modyfikowano istniejących sekretów produkcyjnych.
- Pełna automatyzacja wymaga NEON API z prawami admina lub aktywnego compute endpoint.

Chętnie dokończę automat po aktywacji compute lub po otrzymaniu (bezpiecznie) admin NEON API key — daj znać jak chcesz dalej.

---
Update 2026-09-29 20:24:38:
- PR comments added (neon-provisioner, tests-runner, secrets-sync).
- NEON_API_KEY synced to GitHub Secrets (if present).
- tmp-cred-* credentials cleanup attempted on dev branch.
- Tried to create owner credential to obtain connection_string; plaintext owner connection_string NOT returned — compute likely inactive. Please activate compute in Neon Console.

Update 2026-09-29 20:34:09:
- Attempted to create credentials for roles: sklepzdoniczkami_dev_migrate, sklepzdoniczkami_dev_ro.
- Migrate role: no plaintext returned via API; manual action (Console/admin) may be required.
- Read-only role: no plaintext returned via API; manual action may be required.


Update 2026-09-29 20:36:27:
- SQL-created roles (if allowed) and applied GRANTs where permitted. New roles attempt: 
  - sklepzdoniczkami_dev_migrate -> role: sklepzdoniczkami_dev_migrate_auto_a09aca27 (grants: True)
  - sklepzdoniczkami_dev_ro -> role: sklepzdoniczkami_dev_ro_auto_dd19df6a (grants: True)


Update 2026-09-29 20:47:26:
- Local test run using config.settings_test (SQLite): 44 passed, 6 warnings.
- Note: Neon blocks CREATE DATABASE for managed roles; to run tests against Neon you must pre-create a test database or enable compute / provide admin NEON API key.

## Aktualny stan zweryfikowany 2026-09-29

- Neon API potwierdza, że branch `dev` jest `ready`, a compute endpoint jest `active`.
- Stary sekret CI używał roli `sklepzdoniczkami_dev_migrate_auto_*`, która nie
  mogła odczytać tabeli `django_migrations`; `makemigrations --check` kończył się
  więc błędem uprawnień. Uprawnienia SELECT do obecnych tabel i sekwencji oraz
  domyślne SELECT dla obiektów tworzonych przez właściciela aplikacji zostały
  przyznane rolom diagnostyczną/read-only.
- Właścicielem istniejącej schemy i tabel dev jest `sklepzdoniczkami_dev_app`,
  nie rola owner. Zaktualizowano `DATABASE_URL_DEVELOPMENT` do nowej roli
  `sklepzdoniczkami_dev_web`, która ma tylko DML na schemie public; CREATE TABLE
  jest odrzucane. Sekret CI i lokalny `.env` nie używają już szerokich uprawnień
  roli właściciela.
- Utworzono osobną rolę `sklepzdoniczkami_dev_test` z `CREATEDB` bez
  `CREATEROLE`/superusera. Jej connection string zapisano wyłącznie w sekrecie
  `DATABASE_URL_DEVELOPMENT_TEST`; nie należy używać go jako URL aplikacji.
- Django może wskazać unikalną nazwę testowej bazy przez
  `DJANGO_TEST_DATABASE_NAME`; CI usuwa tę konkretną bazę również po awarii testów.
- Pełny zestaw testów przeszedł na Neon PostgreSQL: 44 passed, 6 warnings,
  2 subtests passed. `makemigrations --check --dry-run` zgłosił `No changes detected`.
- CI backupu wcześniej łączył się ze starym hostem i rolą `neondb_owner`, więc
  uwierzytelnienie nie działało. Utworzono `sklepzdoniczkami_prod_backup` bez
  CREATEDB/CREATEROLE/REPLICATION/superuser, przyznano mu dostęp przez
  `pg_read_all_data` i zapisano połączenie w `DATABASE_URL_PRODUCTION_BACKUP`.
  Połączenie i ograniczone uprawnienia sprawdzono. Ręczny test workflow z
  branchu PR został zablokowany ochroną GitHub Environment `production`;
  backup workflow wymaga dozwolonego brancha. Baza Neon `prod` była bez tabel
  publicznych, więc nie potwierdzono zawartości backupu ani zgodności z
  aktualnym URL-em działającej usługi.
- Na branchu `prod` endpoint może być `idle`; Neon automatycznie go uruchamia
  przy połączeniu. Baza `sklepzdoniczkami_prod` nie miała tabel publicznych,
  a zgodność jej URL-a z usługą live nie była potwierdzona. Backup workflow
  odrzuca teraz pustą bazę i brak wymaganych tabel zamiast tworzyć pozornie
  poprawny artefakt; skonfiguruj URL do właściwej, zmigrowanej bazy produkcyjnej.
- CI uruchomione z PR po zmianach przeszło: testy Django na Neon PostgreSQL,
  kontrola migracji i Playwright E2E (również po przełączeniu sekretu aplikacji
  na ograniczoną rolę `sklepzdoniczkami_dev_web`).
