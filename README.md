# Sklepzdoniczkami

Prosty sklep internetowy zbudowany w Django. Projekt obejmuje katalog produktów, koszyk, zamówienia, użytkowników, płatności Stripe oraz podstawowe widoki storefrontu.

## Funkcje

- katalog produktów z wyszukiwaniem
- kategorie produktów
- strona produktu
- koszyk sesyjny
- formularz zamówienia
- obsługa płatności kartą przez Stripe Checkout
- logowanie i rejestracja użytkownika
- profil z historią zamówień
- panel administratora Django

## Stack technologiczny

- Python 3.11+
- Django 6.1.1
- SQLite (domyślnie)
- Stripe Python SDK
- python-dotenv

## Wymagania

- Python 3.11+
- Git
- dostęp do sieci przy instalacji zależności

## Szybki start

1. Sklonuj repozytorium:

```bash
git clone https://github.com/michalantczak10/sklepzdoniczkami.git sklepzdoniczkami
cd sklepzdoniczkami
```

2. Utwórz środowisko wirtualne:

```bash
python -m venv .venv
```

Na Windows:

```bash
.venv\Scripts\activate
```

Na macOS/Linux:

```bash
source .venv/bin/activate
```

3. Zainstaluj zależności:

```bash
pip install -r requirements.txt
```

4. Skopiuj konfigurację środowiska:

```bash
copy .env.example .env
```

Uzupełnij wartości w pliku `.env`:

```env
DJANGO_SECRET_KEY=twoj-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
STRIPE_SECRET_KEY=sk_test_twoj_klucz
STRIPE_PUBLIC_KEY=pk_test_twoj_klucz
STRIPE_WEBHOOK_SECRET=whsec_twoj_secret
```

5. Zastosuj migracje:

```bash
python manage.py migrate
```

6. Utwórz superużytkownika:

```bash
python manage.py createsuperuser
```

7. Uruchom serwer deweloperski:

```bash
python manage.py runserver
```

Aplikacja będzie dostępna pod adresem:

```text
http://127.0.0.1:8000/
```

Panel administratora:

```text
http://127.0.0.1:8000/admin/
```

## Testy

Uruchom testy:

```bash
python manage.py test sklepzdoniczkami
```

`pytest` also runs the Django tests in `sklepzdoniczkami/`. The browser tests are kept
separate because they require a locally installed browser; run them with the
command below.

## Testy E2E

Testy przeglądarkowe używają Playwrighta i osobnej bazy testowej tworzonej przez
pytest-django na podstawie lokalnej konfiguracji Django.

Zainstaluj zależności developerskie:

```bash
pip install -r requirements-dev.txt
playwright install chromium
```

Uruchom testy E2E:

```bash
pytest e2e --tracing=retain-on-failure --screenshot=only-on-failure
```

Przy błędzie Playwright zapisuje artefakty diagnostyczne zgodnie z konfiguracją
uruchomienia. Testy należy wykonywać lokalnie lub na stagingu, nigdy na produkcji.

## Struktura projektu

```text
sklepzdoniczkami/
├── config/                 # ustawienia Django i URL
├── sklepzdoniczkami/       # aplikacja sklepu
│   ├── migrations/
│   ├── templates/
│   ├── admin.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── .env.example            # przykładowe zmienne środowiskowe
├── .gitignore
├── db.sqlite3              # lokalna baza SQLite
├── manage.py
├── README.md
├── requirements.txt
└── ...
```

## Uwagi dotyczące środowiska

- Domyślnie projekt używa bazy SQLite, co jest wygodne do rozwoju lokalnego.
- W środowisku produkcyjnym warto zastąpić SQLite na PostgreSQL i ustawić `DEBUG=False`.
- Klucze Stripe powinny być pobrane z panelu Stripe i ustawione w zmiennych środowiskowych.

## Następne kroki

Po uruchomieniu projektu można rozwijać dalej takie elementy jak:

- opinie i recenzje produktów
- promocje i kupony
- newsletter
- wyszukiwanie i filtry SEO
- integracja z dostawcą wysyłki
- pełna obsługa zamówień w panelu admina

## Procedura testowego restore bazy (staging)

Aby włączyć upload do S3 z workflow db-backup.yml, ustaw w repo Secrets:
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- BACKUP_S3_BUCKET
- (opcjonalnie) AWS_REGION

Workflow prześle paczkę tylko gdy te sekrety będą ustawione.

## Procedura testowego restore bazy (staging)

### Synchronizacja po przepisywaniu historii (force-push)

Jeśli repo przeszło przepisywanie historii (np. usunięto wrażliwe pliki), każdy współpracownik powinien zsynchronizować lokalne kopie:

1. Zachowaj lokalne zmiany (opcjonalnie):

```bash
git branch save-local-$(date +%s)
# lub stwórz patch
git format-patch origin/main..HEAD
```

2. Zsynchronizuj z nowym origin:

```bash
git fetch origin
git reset --hard origin/main
```

Uwaga: `git reset --hard` usunie lokalne, niezacommitowane zmiany. Jeśli masz pracę, zachowaj ją przed resetem.


Krótka instrukcja jak przetestować przywracanie backupu do staging i sprawdzić integralność:


### Czyszczenie lokalnych artefaktów

Podczas debugowania backupów workflow tworzy lokalne katalogi z artefaktami. Użyj dostarczonego skryptu do szybkiego posprzątania środowiska:

```bash
# uruchom z katalogu repo
scripts/cleanup_artifacts.sh
```

Skrypt usuwa katalogi artifacts/ i tymczasowe pobrane artefakty z C:\\temp, a także typowe pliki backupowe w katalogu repo.


1. Przywracanie (wykorzystanie istniejącego workflow):
   - Workflow `restore-staging.yml` pobiera najnowszy zaszyfrowany artefakt backupu, odszyfrowuje go (sekret BACKUP_ENCRYPTION_KEY) i uruchamia pg_restore wewnątrz obrazu postgres:18.
   - Upewnij się, że secret `DATABASE_URL_STAGING` wskazuje poprawną bazę staging (Neon) i że runner ma dostęp (sieć/autoryzacja).

2. Sanity checks po restore (ręcznie lub przez workflow):
   - Policz rekordy w kluczowych tabelach:
     - SELECT count(*) FROM sklepzdoniczkami_product;
     - SELECT count(*) FROM sklepzdoniczkami_order;
     - SELECT count(*) FROM sklepzdoniczkami_orderitem;
     - SELECT count(*) FROM auth_user;
   - Sprawdź, że tabele i sekwencje zostały utworzone i sekwencje ustawione (pg_restore wypisuje "SEQUENCE SET ...").

3. Co zrobić, gdy brak danych:
   - Sprawdź rozmiar artefaktu backupu (artifact w GitHub Actions) — czy backup.dump ma oczekiwany rozmiar.
   - Pobierz artefakt lokalnie i uruchom: `pg_restore --list backup.dump` by zobaczyć listę obiektów i upewnić się, że są tam oczekiwane tabele.
   - Potwierdź, że pg_restore użyto zgodnej wersji binarek (używamy postgres:18 w workflow). Problem z wersjami powoduje błędy lub brak zgodności.
   - Zweryfikuj, że DATABASE_URL_STAGING wskazuje właściwą bazę (nie omyłkowo inny projekt/neon).

4. Automatyczne testy (zalecane):
   - Zaplanuj okresowy test restore (np. co 30 dni) jako workflow cron uruchamiający przywracanie do wydzielonej bazy testowej i wykonujący sanity checks.
   - Upewnij się, że baza testowa jest bezpieczna i rotowana, oraz że koszty transferu danych są akceptowalne.

5. Bezpieczeństwo i retention:
   - Artefakty GitHub mają ograniczoną retencję — rozważ długoterminowe przechowywanie backupów w S3/Backblaze z szyfrowaniem klienta.
   - Rotuj klucz szyfrujący BACKUP_ENCRYPTION_KEY i ogranicz dostęp do sekretów w GitHub.

Jeśli chcesz, mogę:
- Dodać sekcję z poleceniami (psql) i przykładowymi SELECTami jako skrypt w repo (do uruchomienia lokalnie),
- Albo dodać przykład workflow cron, który wykona testowe restore co 30 dni.
