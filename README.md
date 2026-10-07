# Sklepzdoniczkami

Sklep internetowy oparty na Django: katalog produktów, koszyk, zamówienia,
płatności Stripe, konta klientów i panel administratora.

## Obecna produkcja

Sklep działa na VPS OVH (`141.94.224.49`) pod `sklepzdoniczkami.pl`.
Ubuntu uruchamia Django/Gunicorn przez systemd, PostgreSQL działa lokalnie na
VPS, a Caddy zapewnia reverse proxy i HTTPS. DNS domeny jest obsługiwany przez
OVH. Render i Neon nie są używane przez aktualną produkcję.

Produkcyjna baza została uruchomiona od nowa i jest pusta — nie zaimportowano
produktów ani historii klientów i zamówień. Konto administratora `michal`
istnieje. Stripe i poczta e-mail nie są skonfigurowane, więc przed przyjmowaniem
płatności lub wysyłaniem wiadomości trzeba skonfigurować tych dostawców.

Konfiguracja serwera, obsługa usług i stan kopii zapasowych są opisane w
[runbooku VPS](docs/self-hosting-recovery.md). Nie ma obecnie automatycznych,
niezależnych kopii zapasowych VPS; skonfiguruj i przetestuj je przed dodaniem
ważnych danych sklepu.

## Uruchomienie lokalne

Wymagany jest Python 3.11 lub nowszy.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Lokalny PostgreSQL dla developmentu jest dostępny wyłącznie na komputerze pod
`127.0.0.1:5434`. `.env.example` zawiera przykładową konfigurację lokalną.
Nie używaj przykładowego hasła PostgreSQL w innym środowisku ani nie commituj
`.env`. Przy zmianie hasła bazy zaktualizuj również `DATABASE_URL_DEVELOPMENT`;
nie usuwaj wolumenu, aby zmienić hasło, bo zawiera dane lokalne.

Sklep będzie dostępny pod `http://127.0.0.1:8000/`, a panel administratora pod
`http://127.0.0.1:8000/admin/`. Bez `DATABASE_URL_DEVELOPMENT` Django używa
SQLite. Lokalne uruchomienie nie łączy się z produkcyjną bazą.

## Testy

```powershell
pip install -r requirements-dev.txt
pytest -q --ds=config.settings_test
playwright install chromium
pytest e2e --tracing=retain-on-failure --screenshot=only-on-failure
```

GitHub Actions uruchamia kontrole i testy na SQLite. CI nie wymaga sekretów
dostępu do zewnętrznej bazy.

## Inne instrukcje

- [Runbook produkcji i odzyskiwania na VPS](docs/self-hosting-recovery.md)
- [Opcjonalne lokalne uruchomienie na Windows](docs/windows-self-hosting.md)
