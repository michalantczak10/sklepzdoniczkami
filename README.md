# Sklepzdoniczkami

Sklep internetowy oparty na Django: katalog produktów, koszyk, zamówienia,
płatności Stripe, konta klientów i panel administratora.

## Uruchomienie lokalne

Wymagany jest Python 3.12 lub nowszy.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Docker nie jest potrzebny do developmentu. Bez `DATABASE_URL_DEVELOPMENT`
Django używa lokalnego SQLite; aby aplikacja łączyła się ze wspólną bazą Neon
dev, ustaw tę zmienną w niecommitowanym `.env` na dedykowany URL roli
`sklepzdoniczkami_dev_web`. Nie używaj testowego URL-a z uprawnieniem
`CREATEDB` ani credentiali ownera jako połączenia aplikacji. Uzupełnij pozostałe
zmienne z sufiksem `_DEVELOPMENT`, a następnie uruchom:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Polecenie `migrate` w powyższym przykładzie dotyczy lokalnego SQLite.
Rola aplikacyjna Neon ma celowo tylko prawa DML i nie może zmieniać schematu;
testy CI wykonują migracje na osobnej, tymczasowej bazie PostgreSQL. Nie
uruchamiaj migracji na wspólnej bazie Neon przez URL aplikacyjny.

Sklep będzie dostępny pod `http://127.0.0.1:8000/`, a panel administratora pod
`http://127.0.0.1:8000/admin/`. Domyślnie aplikacja używa SQLite; PostgreSQL
można skonfigurować przez `DATABASE_URL_DEVELOPMENT`. Klucze testowe Stripe
pochodzą z panelu Stripe i nie należy ich commitować.

## Testy

Testy Django:

```powershell
python manage.py test sklepzdoniczkami
```

Testy CI i przeglądarkowe wymagają zależności z `requirements-dev.txt`:

```powershell
pip install -r requirements-dev.txt
playwright install chromium
pytest -q
pytest e2e --tracing=retain-on-failure --screenshot=only-on-failure
```

## GitHub Actions

- `ci.yml` uruchamia kontrole Django, testy i testy przeglądarkowe dla pull
  requestów do `main`/`dev` oraz zmian na tych branchach. Testy Django używają
  Neon dev i osobnej, tworzonej dla danego uruchomienia bazy testowej; job
  sprząta ją również po nieudanym teście.
- `db-backup.yml` tworzy codzienny lub ręcznie wywołany zaszyfrowany backup.
  Artefakty są przechowywane przez 90 dni. Docker jest używany wyłącznie na
  runnerze GitHub Actions do uruchomienia `pg_dump`; nie jest wymagany lokalnie.

## Oddzielne środowiska i bazy danych

Neon ma trzy odizolowane środowiska:

| Środowisko | Aplikacja | Baza |
|---|---|---|
| Development i CI | Aplikacja lokalna/CI | `sklepzdoniczkami_dev` |
| Preprod | Render `sklepzdoniczkami-preprod` | `sklepzdoniczkami_preprod` |
| Produkcja | Render `sklepzdoniczkami` | `sklepzdoniczkami_prod` |

Lokalny `.env` może używać dedykowanej roli aplikacyjnej do bazy dev; bez
`DATABASE_URL_DEVELOPMENT` Django korzysta z SQLite. Produkcyjny URL musi
wskazywać dokładnie `sklepzdoniczkami_prod`. Baza produkcyjna Neon była pusta
podczas ostatniej weryfikacji; przed przełączeniem usługi Render potwierdź jej
aktualny URL i wykonaj backup istniejących danych.

Preprod korzysta z gałęzi Neon `preprod` utworzonej z dev i z odrębnej,
początkowo pustej bazy. Wypełnia ją wyłącznie idempotentny katalog
syntetycznych produktów; nie kopiuj do niej backupów ani danych produkcyjnych.
Rola `sklepzdoniczkami_preprod_web_limited` ma prawa DML, a
`sklepzdoniczkami_preprod_migrate_limited` jest właścicielem tej bazy i służy
tylko do migracji. Obie role nie mają uprawnień administratora Neon ani praw
tworzenia baz lub ról. Render otrzymuje wyłącznie `DATABASE_URL_PREPROD` dla
ograniczonej roli web. Migracje wykonuje CI po testach i E2E, na push do `dev`,
korzystając z sekretu `DATABASE_URL_PREPROD_MIGRATE` w GitHub Environment
`preprod`. URL migracyjny nie może być dostępny procesowi web w Renderze.
Środowisko GitHub `preprod` ma dodatkowo regułę deployment branch ograniczoną
do `dev`, więc pull request z innej gałęzi nie otrzyma tego sekretu.
`sync: false` nie aktualizuje istniejących sekretów przy kolejnej synchronizacji
Blueprintu.

Zmiany trafiają przez pull request do gałęzi GitHub `dev`; CI uruchamia testy,
a Render wdraża preprod z `dev` dopiero po przejściu kontroli. Po smoke testach
preprod promuj sprawdzony kod przez pull request `dev` → `main`. Automatyczne
wdrożenia produkcji są wyłączone; po scaleniu wdrażaj w Renderze ręcznie commit
z `main`. Stripe na preprod używa wyłącznie kompletu kluczy testowych; gdy ich
nie ustawiono, płatność kartą jest wyłączona.

Sekrety aplikacji używają sufiksów `_DEVELOPMENT`, `_PREPROD` lub
`_PRODUCTION`. Dotyczy to `DATABASE_URL`, `DJANGO_SECRET_KEY` i kluczy Stripe.
Nazwy baz to `DATABASE_NAME_DEVELOPMENT`, `DATABASE_NAME_PREPROD` i
`DATABASE_NAME_PRODUCTION`. Ustawienia wspólne, takie jak `APP_ENV`, `DEBUG`,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` i `SITE_NAME`, pozostają bez sufiksu.
Produkcja wymaga jawnych URL-i, klucza Django, nazwy bazy, `DEBUG=False` oraz
`ALLOWED_HOSTS`. Stripe jest wyłączony, jeśli wszystkie klucze są pominięte;
jeśli są skonfigurowane, muszą być kompletne i pasować do środowiska.

GitHub Actions potrzebuje sekretów:

- `DATABASE_URL_DEVELOPMENT_RO` i `DATABASE_NAME_DEVELOPMENT` do bezpiecznego
  sprawdzenia dostępu do Neon dev.
- `DATABASE_URL_DEVELOPMENT_TEST` to dedykowana rola CI z prawem tworzenia
  bazy testowej; nie używaj jej w aplikacji. CI tworzy osobną nazwę bazy dla
  każdego uruchomienia i usuwa ją po testach.
- `DATABASE_URL_PRODUCTION_BACKUP`, `BACKUP_ENCRYPTION_KEY` i
  `BACKUP_HMAC_KEY` do backupu produkcji. URL backupu używa osobnej roli
  `sklepzdoniczkami_prod_backup`, a nie poświadczeń aplikacji.

`DATABASE_URL_PREPROD` jest sekretem Rendera. `DATABASE_URL_PREPROD_MIGRATE`
jest sekretem GitHub Environment `preprod` i trafia wyłącznie do joba migracji
uruchamianego po zaufanym pushu na `dev`, nigdy do pull-requestów ani procesu
web. Nie umieszczaj żadnego z tych URL-i w repozytorium.

Nie używaj `DATABASE_URL_DEVELOPMENT_TEST` jako połączenia sklepu ani nie
kopiuj sekretów production do CI testowego. GitHub nie pozwala odczytać
wartości istniejących sekretów; rotuj je przez Neon/GitHub, a nie przez
drukowanie ich w logach.

Nie ma automatycznego workflowu przywracającego produkcyjną bazę na preprod.
Tym samym dane klientów nie są kopiowane do środowiska przedprodukcyjnego.
Po utworzeniu nowego serwisu sprawdź w Renderze, czy stary
`sklepzdoniczkami-staging` już nie jest potrzebny; usuń go wraz z jego zmiennymi
środowiskowymi dopiero po upewnieniu się, że produkcyjna usługa pozostała
nienaruszona. Nie używaj jego starej bazy jako nowej bazy preprod.
