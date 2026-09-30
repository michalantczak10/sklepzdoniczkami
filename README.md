# Sklepzdoniczkami

Sklep internetowy oparty na Django: katalog produktów, koszyk, zamówienia,
płatności Stripe, konta klientów i panel administratora.

## Architektura projektu

Decyzje dotyczące baz danych, branchy, wdrożeń, CI i review opisuje
[plan architektury](ARCHITECTURE-PLAN.md).

## Uruchomienie lokalne

Wymagany jest Python 3.11 lub nowszy.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d db
```

`docker compose up -d db` uruchamia lokalny PostgreSQL dla developmentu,
dostępny z hosta na porcie `5434`; `.env.example` zawiera zgodny URL i lokalne
poświadczenia przykładowej bazy. Kontener aplikacji łączy się z bazą przez
wewnętrzny adres Docker `db:5432`. Uzupełnij `.env` zmiennymi z sufiksem
`_DEVELOPMENT`, a następnie uruchom:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Konfigurację Compose można sprawdzić bez uruchamiania kontenerów poleceniem
`docker compose config --quiet`. W CI walidacja uruchamia się automatycznie.

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
  Artefakty są przechowywane przez 90 dni.

## Oddzielne środowiska i bazy danych

Projekt ma trzy odizolowane środowiska:

| Środowisko | Aplikacja | Baza | Dane i płatności |
|---|---|---|---|
| Development | Aplikacja lokalna/CI | Neon `sklepzdoniczkami_dev` | Testowe |
| Preprod | Render `sklepzdoniczkami-preprod` | Neon `sklepzdoniczkami_preprod` | Katalog syntetyczny, płatności testowe lub wyłączone |
| Produkcja | Render `sklepzdoniczkami` | Neon `sklepzdoniczkami_prod` | Prawdziwe zamówienia, klucze Stripe live |

Render service slugs używają myślników. Nazwy baz PostgreSQL dla środowisk
używają podkreślenia i sufiksu (`_dev`, `_preprod`, `_prod`). Jeśli istniejąca
baza produkcyjna nadal nazywa się `sklepzdoniczkami`, trzeba ją przemianować na
`sklepzdoniczkami_prod` przed wdrożeniem tej konfiguracji. Nowa konfiguracja
odrzuca produkcyjny URL, jeżeli jego nazwa bazy nie zgadza się z tą wartością.
Najpierw wykonaj i zweryfikuj backup, zatrzymaj aplikację, zmień nazwę bazy w
Neon, a dopiero potem zaktualizuj sekrety i wznów wdrożenie.

Po synchronizacji Blueprint ustaw w Renderze `DATABASE_URL_PREPROD` i
`DATABASE_URL_PRODUCTION` na odpowiednie osobne bazy Neon. Preprod i produkcja
muszą wskazywać **różne bazy Neon**; najlepiej
utworzyć dla każdej osobny projekt i ograniczyć dostęp do produkcyjnej bazy.
Utwórz nową bazę o nazwie `sklepzdoniczkami_preprod` w oddzielnym projekcie Neon
dla preprod — nie używaj starego URL-a stagingowego, bo mógł zawierać kopię danych
produkcyjnych. Aplikacja preprod odmawia startu, jeśli nazwa bazy z URL-a nie
jest dokładnie `sklepzdoniczkami_preprod`; analogicznie produkcja wymaga
`sklepzdoniczkami_prod`.
Lokalny `.env` ma wskazywać tylko lokalny PostgreSQL, nigdy Neon production.
Preprod automatycznie tworzy kilka fikcyjnych kategorii i produktów podczas
wdrożenia. Nie kopiuje bazy ani danych użytkowników/zamówień z produkcji.
Preprod może działać bez Stripe: płatność kartą jest wtedy ukryta, a przelew i
pobranie pozostają dostępne. Po skonfigurowaniu Stripe należy ustawić komplet
kluczy testowych i sekret webhooka (`whsec_`); Django odrzuca tam klucze
`sk_live_` i `pk_live_`. Produkcja akceptuje wyłącznie komplet kluczy live i
sekret webhooka. Jeśli konfiguracja Stripe jest niepełna albo nie pasuje do
środowiska, aplikacja nie uruchomi się; jeśli wszystkie klucze są pominięte,
płatność kartą zostanie wyłączona.

Sekrety aplikacji mają konsekwentny sufiks środowiska: `_DEVELOPMENT`,
`_PREPROD` albo `_PRODUCTION`. Dotyczy to `DATABASE_URL`, `DJANGO_SECRET_KEY`
oraz trzech kluczy Stripe. Nazwy baz (nie sekretów) to odpowiednio
`DATABASE_NAME_DEVELOPMENT`, `DATABASE_NAME_PREPROD` i
`DATABASE_NAME_PRODUCTION`. Ustawienia wspólne, takie jak `APP_ENV`, `DEBUG`,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` i `SITE_NAME`, pozostają bez sufiksu.
Lokalny `.env` ustaw zgodnie z `.env.example`; bez lokalnego
`DATABASE_URL_DEVELOPMENT` Django używa SQLite. Django odmawia uruchomienia
preprod/produkcji bez odpowiednich środowiskowych URL-i i klucza Django,
nazwy bazy, `DEBUG=False` i jawnego `ALLOWED_HOSTS`.

GitHub Actions potrzebuje sekretów:

- `DATABASE_URL_DEVELOPMENT_RO` i `DATABASE_NAME_DEVELOPMENT` do bezpiecznego
  sprawdzenia dostępu do Neon dev.
- `DATABASE_URL_DEVELOPMENT_TEST` to dedykowana rola CI z prawem tworzenia
  bazy testowej; nie używaj jej w aplikacji. CI tworzy osobną nazwę bazy dla
  każdego uruchomienia i usuwa ją po testach.
- `DATABASE_URL_PRODUCTION_BACKUP`, `BACKUP_ENCRYPTION_KEY` i
  `BACKUP_HMAC_KEY` do backupu produkcji. URL backupu używa osobnej roli
  `sklepzdoniczkami_prod_backup`, a nie poświadczeń aplikacji.

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
