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
dostępny wyłącznie z tego komputera pod `127.0.0.1:5434`. `.env.example`
zawiera zgodny `DATABASE_URL_DEVELOPMENT` i lokalne hasło przykładowej bazy.
Jeśli wcześniej utworzono `.env`, skopiuj do niego te dwie wartości ręcznie,
nie nadpisując pozostałych sekretów i ustawień. Przy zmianie hasła PostgreSQL
zaktualizuj również hasło w URL-u; sama zmiana `POSTGRES_PASSWORD` nie zmienia
hasła w już zainicjalizowanym wolumenie. W takim przypadku zmień hasło roli
poleceniem `\password sklepzdoniczkami` w sesji `psql` uruchomionej przez
`docker compose exec db psql -U sklepzdoniczkami -d postgres`. Nie usuwaj
wolumenu, aby zmienić hasło — zawiera lokalne dane. Nie używaj tego lokalnego
hasła w innych środowiskach. Następnie uzupełnij `.env` zmiennymi z sufiksem
`_DEVELOPMENT` i uruchom aplikację Django na hoście:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Konfigurację Compose można sprawdzić bez uruchamiania kontenerów poleceniem
`docker compose config --quiet`. CI wykonuje tę walidację automatycznie.

Sklep będzie dostępny pod `http://127.0.0.1:8000/`, a panel administratora pod
`http://127.0.0.1:8000/admin/`. Jeśli `DATABASE_URL_DEVELOPMENT` nie jest
ustawione, Django użyje SQLite. Klucze testowe Stripe pochodzą z panelu Stripe
i nie należy ich commitować.

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
  requestów do `main`/`dev` oraz pushy na tych branchach. Testy PR używają
  SQLite (`config.settings_test`) i nie otrzymują sekretów Neon. Testy po
  pushu używają Neon dev oraz osobnej bazy testowej dla danego uruchomienia;
  job sprząta ją również po nieudanym teście.
- `db-backup.yml` tworzy codzienny lub ręcznie wywołany zaszyfrowany backup.
  Artefakty są przechowywane przez 90 dni.
- `bootstrap-production-admin.yml` pozwala jednorazowo utworzyć pierwszego
  administratora produkcji. Read-only preflight można uruchomić z `main`;
  pierwsze utworzenie wymaga tymczasowego sekretu w GitHub Environment
  `production` (zostało już wykonane).
- `production-preview-catalog.yml` dodaje na wyraźne żądanie katalog
  demonstracyjny do produkcji. Uruchamiaj go dopiero po wdrożeniu nowego kodu
  na Renderze; tworzone produkty mają stan 0, więc nie można ich kupić.

## Pierwszy administrator produkcji

Pierwsze konto administratora produkcji zostało utworzone 2026-10-01
workflowem
[36903517437](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36903517437).
Jednorazowy sekret `INITIAL_ADMIN_PASSWORD` został po tym usunięty z GitHub
Environment `production`. Tryb `preflight-only` pozostaje dostępny do
odczytowego sprawdzenia połączenia i uprawnień. Nie uruchamiaj trybu tworzenia
ponownie — workflow nie służy do resetowania hasła ani tworzenia kolejnych
administratorów.

Workflow sprawdza przypięty host, bazę `sklepzdoniczkami_prod` i ograniczoną
rolę runtime, używając istniejącego sekretu `DATABASE_URL_PRODUCTION_WEB`
w GitHub Environment `production`; nie kopiuj URL-a bazy do lokalnego `.env`
ani do pola wejściowego workflow. Odmówi działania poza produkcją, gdy istnieje
już superuser, gdy hasło jest słabe albo dane logowania nie przechodzą
walidacji. Nie zmienia konfiguracji Stripe ani Rendera i nie uruchamia
płatności.

## Oddzielne środowiska i bazy danych

Projekt ma trzy odizolowane środowiska:

| Środowisko | Aplikacja | Baza | Dane i płatności |
|---|---|---|---|
| Development | Host Django / CI | Lokalny PostgreSQL; push: Neon dev; PR: SQLite | Testowe |
| Preprod | Render `sklepzdoniczkami-preprod` | Neon `sklepzdoniczkami_preprod` | Katalog syntetyczny, Stripe test mode |
| Produkcja | Render `sklepzdoniczkami` | Neon `sklepzdoniczkami_prod` | Prawdziwe zamówienia, klucze Stripe live |

Preprod ma skonfigurowane klucze Stripe test i osobny webhook. Podpisane
zdarzenie webhook bez płatności oraz pełny zakup testowy zostały sprawdzone
2026-10-03. Stripe potwierdził także, że rzeczywiste zdarzenie
`checkout.session.completed` dla tego zakupu zostało dostarczone do aktywnych
endpointów webhook. Wykorzystano standardową testową kartę Stripe; płatność nie
obciążyła żadnej prawdziwej karty. Testowe zamówienie pozostawiono na preprod
jako potwierdzenie przepływu — nie realizować go. Nie używaj kluczy live do
testów.

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
Ten sam syntetyczny katalog może być dodany do produkcji przez ręczny workflow
`Add production preview catalogue`, uruchomiony z `main` po wdrożeniu strony.
Produkty mają widoczny dopisek „test”, przykładowe ceny i opisy, a ich stan
magazynowy wynosi 0; są wyłącznie do podglądu i nie można złożyć na nie
zamówienia. Workflow odmawia nadpisania istniejących danych o tych samych
slugach. Zdjęcia pochodzą z wersjonowanych plików statycznych aplikacji, nie
z plików `media/` ani z produkcyjnej bazy preprod.
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
