# Sklepzdoniczkami

Sklep internetowy oparty na Django: katalog produktów, koszyk, zamówienia,
płatności Stripe, konta klientów i panel administratora.

## Uruchomienie lokalne

Wymagany jest Python 3.11 lub nowszy.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d db
```

`docker compose up -d db` uruchamia lokalny PostgreSQL dla developmentu.
Uzupełnij `.env` lokalnymi wartościami, a następnie uruchom:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Sklep będzie dostępny pod `http://127.0.0.1:8000/`, a panel administratora pod
`http://127.0.0.1:8000/admin/`. Domyślnie aplikacja używa SQLite; PostgreSQL
można skonfigurować przez `DATABASE_URL`. Klucze testowe Stripe pochodzą z
panelu Stripe i nie należy ich commitować.

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
  requestów oraz zmian na `main`.
- `db-backup.yml` tworzy codzienny lub ręcznie wywołany zaszyfrowany backup.
  Artefakty są przechowywane przez 90 dni.

## Oddzielne środowiska i bazy danych

Projekt ma trzy odizolowane środowiska:

| Środowisko | Aplikacja | Baza | Dane i płatności |
|---|---|---|---|
| Lokalny development | Na komputerze | `sklepzdoniczkami-dev` (lokalny PostgreSQL z Docker Compose lub domyślny SQLite) | Lokalne/testowe |
| Preprod | Render `sklepzdoniczkami-preprod` | Neon `sklepzdoniczkami-preprod` | Katalog syntetyczny, płatności testowe lub wyłączone |
| Produkcja | Render `sklepzdoniczkami` | Produkcyjna baza Neon | Prawdziwe zamówienia, klucze Stripe live |

Nazwy baz środowiskowych używają myślnika i sufiksu środowiska (`-dev`,
`-preprod`); produkcyjna baza zachowuje krótką nazwę kanoniczną
`sklepzdoniczkami`.

Po synchronizacji Blueprint ustaw w Renderze `DATABASE_URL` osobno dla obu
usług. Preprod i produkcja muszą wskazywać **różne bazy Neon**; najlepiej
utworzyć dla każdej osobny projekt i ograniczyć dostęp do produkcyjnej bazy.
Utwórz nową bazę o nazwie `sklepzdoniczkami-preprod` w oddzielnym projekcie Neon
dla preprod — nie używaj starego URL-a stagingowego, bo mógł zawierać kopię danych
produkcyjnych. Aplikacja preprod odmawia startu, jeśli nazwa bazy z URL-a nie
jest dokładnie `sklepzdoniczkami-preprod`.
Lokalny `.env` ma wskazywać tylko lokalny PostgreSQL, nigdy Neon production.
Preprod automatycznie tworzy kilka fikcyjnych kategorii i produktów podczas
wdrożenia. Nie kopiuje bazy ani danych użytkowników/zamówień z produkcji.
Preprod może działać bez Stripe: płatność kartą jest wtedy ukryta, a przelew i
pobranie pozostają dostępne. Po skonfigurowaniu Stripe należy ustawić komplet
kluczy testowych; Django odrzuca tam klucze `sk_live_` i `pk_live_`.

Lokalnie ustaw `APP_ENV=development`, `DEBUG=True` i lokalny `DATABASE_URL` w
`.env`. Jeśli URL nie jest ustawiony, Django używa lokalnego SQLite. Django
odmawia uruchomienia preprod/produkcji bez `DATABASE_URL`, jawnego
`DJANGO_SECRET_KEY`, `DEBUG=False` i jawnego `ALLOWED_HOSTS`.

GitHub Actions potrzebuje sekretów:

- `DATABASE_URL_PRODUCTION` — produkcyjna baza dla backupu; ustaw jako sekret
  środowiska GitHub `production`.
- `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY` — szyfrowanie i uwierzytelnianie
  backupów. Są obecnie sekretami repozytorium; nie ustawiaj ich ponownie jako
  zmiennych Render ani Neon.

Nie ma automatycznego workflowu przywracającego produkcyjną bazę na preprod.
Tym samym dane klientów nie są kopiowane do środowiska przedprodukcyjnego.
Po utworzeniu nowego serwisu sprawdź w Renderze, czy stary
`sklepzdoniczkami-staging` już nie jest potrzebny; usuń go wraz z jego zmiennymi
środowiskowymi dopiero po upewnieniu się, że produkcyjna usługa pozostała
nienaruszona. Nie używaj jego starej bazy jako nowej bazy preprod.
