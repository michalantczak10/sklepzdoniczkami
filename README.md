# Sklep internetowy

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
git clone https://github.com/michalantczak10/sklep_internetowy.git
cd sklep_internetowy
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
python manage.py test shop
```

## Struktura projektu

```text
sklep_internetowy/
├── config/                 # ustawienia Django i URL
├── shop/                   # aplikacja sklepu
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
