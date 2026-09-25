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
```

Uzupełnij `.env` wartościami dla lokalnego środowiska, a następnie uruchom:

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
- `restore-staging.yml` przywraca wybrany lub najnowszy backup do stagingu.
  Workflow można uruchomić ręcznie; harmonogram uruchamia go co miesiąc.

## Oddzielne środowiska i bazy danych

Projekt ma dwa niezależne serwisy Render opisane w `render.yaml`:

| Środowisko | Render | Baza Neon | Stripe |
|---|---|---|---|
| Produkcja | `sklepzdoniczkami` | Własny produkcyjny `DATABASE_URL` | Klucze produkcyjne |
| Staging/development | `sklepzdoniczkami-staging` | Osobny stagingowy `DATABASE_URL` | Klucze testowe (`sk_test_...`, `pk_test_...`) |

Po synchronizacji Blueprint w Renderze uzupełnij `DATABASE_URL` osobno w
ustawieniach każdego serwisu. Obie wartości muszą pochodzić z różnych baz lub
branchy Neon. Zalecane jest utworzenie oddzielnych projektów Neon dla produkcji
i developmentu; minimum to dwa osobne branche z odrębnymi connection stringami.
Nie wpisuj produkcyjnego URL-a do lokalnego `.env` ani stagingowego serwisu.
Po synchronizacji nowego serwisu stagingowego w Renderze ustaw ręcznie jego
nowe sekrety w Render Dashboard. Dla stagingu użyj kluczy Stripe w trybie
testowym; aplikacja odrzuci klucze `sk_live_` i `pk_live_`.

Lokalnie ustaw `APP_ENV=development`, `DEBUG=True` i developerski `DATABASE_URL`
w `.env`. Jeśli URL nie jest ustawiony, Django używa lokalnego SQLite. Django
odmawia uruchomienia stagingu/produkcji bez `DATABASE_URL`, jawnego
`DJANGO_SECRET_KEY`, `DEBUG=False` i jawnego `ALLOWED_HOSTS`.

W GitHub Settings → Environments utwórz środowiska `production` i `staging`
(workflowy odwołują się do tych nazw). Dodaj sekrety:

- jako **repository secret** `DATABASE_URL_PRODUCTION` — baza produkcyjna,
  potrzebna do backupu i sprawdzenia celu restore;
- jako **staging environment secret** `DATABASE_URL_STAGING` — odrębna baza
  stagingowa, cel restore;
- jako repository secrets `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY` — klucze
  backupu.

Do czasu dodania nowych sekretów backup i restore zachowują zgodność wsteczną:
`DATABASE_URL` repozytorium jest traktowany jako produkcyjny, a
`DATABASE_URL_STAGING` może pozostać repository secret. Po przeniesieniu
`DATABASE_URL_STAGING` do środowiska staging usuń jego starą kopię z poziomu
repozytorium.
Restore sprawdza host i nazwę bazy, odmawia odtworzenia, jeśli rozpoznaje ten sam
cel, a po przywróceniu anonimizuje dane klientów, wyłącza hasła użytkowników
oraz usuwa identyfikatory płatności, logi admina i sesje na stagingu.

Pamiętaj, że restore najpierw przenosi kopię produkcyjnych danych do stagingu,
zanim wykona anonimizację. Jeśli nie akceptujesz nawet krótkotrwałego
przetwarzania takich danych na stagingu, nie uruchamiaj tego workflowu; zamiast
tego używaj stagingowych danych testowych.
