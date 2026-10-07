# Produkcja na VPS OVH

Ten runbook opisuje aktualną produkcję i podstawowe czynności administracyjne.
Nie zawiera danych logowania ani sekretów.

## Aktualny stan

- VPS: `vps-13bc3512.vps.ovh.net`, Ubuntu 26.04 LTS, IPv4 `141.94.224.49`.
- Kod: `/opt/sklepzdoniczkami`.
- Django/Gunicorn: usługa systemd `sklepzdoniczkami.service`, nasłuchuje
  lokalnie na `127.0.0.1:8000`.
- Baza: PostgreSQL 18 na VPS, baza produkcyjna `sklepzdoniczkami_prod`.
- Reverse proxy i HTTPS: Caddy; konfiguracja `/etc/caddy/Caddyfile`.
- Firewall dopuszcza publicznie tylko TCP 22, 80 i 443.
- Rekordy A `@` i `www` w OVH wskazują na `141.94.224.49`.
- Produkcyjna baza jest pusta poza kontem administratora `michal`; nie
  zaimportowano produktów, klientów ani zamówień.
- Stripe i SMTP nie są skonfigurowane. Sklep nie jest gotowy do płatności
  Stripe ani wysyłania poczty.

Aktualna produkcja korzysta z VPS i lokalnego PostgreSQL. Nie jest zależna od
zewnętrznej bazy danych ani platformy aplikacyjnej.

## Dostęp i konfiguracja

Połącz się z VPS jako `ubuntu` przez SSH. Nie umieszczaj prywatnego klucza,
hasła administratora ani zawartości `/etc/sklepzdoniczkami/app.env` w Git,
logach lub rozmowie.

Hasło konta `michal` zostało zapisane lokalnie poza repozytorium w pliku
`%LOCALAPPDATA%\Sklepzdoniczkami\vps-production-admin.txt`. Zapisz je
w menedżerze haseł, a następnie usuń plik. Nie ma go w repozytorium.

Panel administratora: <https://sklepzdoniczkami.pl/admin/>.

## Sprawdzanie usług

```bash
sudo systemctl status sklepzdoniczkami.service
sudo systemctl status postgresql
sudo systemctl status caddy
sudo journalctl -u sklepzdoniczkami.service -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

Po zmianie konfiguracji Caddy najpierw zweryfikuj ją, a dopiero potem
przeładuj usługę:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Nie wystawiaj publicznie PostgreSQL (`5432`) ani Django (`8000`).

## Wdrożenie zmian aplikacji

Przed aktualizacją produkcji sprawdź i zatwierdź zmiany w Git. Po pobraniu
nowego kodu na serwerze zainstaluj zależności, zastosuj migracje i zbierz
statyczne pliki. Jeśli któraś czynność się nie powiedzie, nie restartuj
usługi, dopóki nie zostanie rozpoznany problem.

```bash
cd /opt/sklepzdoniczkami
git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart sklepzdoniczkami.service
```

Po wdrożeniu sprawdź stronę główną, `/admin/` i logi usługi. Migracje
produkcyjne mogą zmienić schemat bazy, dlatego przed ich wykonaniem potrzebna
jest aktualna kopia zapasowa.

## Kopie zapasowe i odzyskiwanie

Automatyczne, niezależne kopie zapasowe aktualnej bazy VPS i plików `media/`
nie są skonfigurowane. Zanim sklep zacznie przechowywać ważne produkty,
zamówienia lub dane klientów, skonfiguruj kopię przechowywaną poza VPS,
zabezpiecz klucze dostępu i przetestuj odtworzenie na osobnej bazie.

Na VPS pozostawiono jednorazowy, chroniony dump
`/var/backups/sklepzdoniczkami/production-before-neon-restore-20261007.dump`.
To kopia sprzed uruchomienia pustej bazy; nie odtwarzaj jej bez świadomej
decyzji o przywróceniu wcześniejszej zawartości. Nie usuwaj jej, dopóki nie
powstanie i nie zostanie sprawdzona niezależna kopia obecnej bazy.

Repozytorium nie zawiera produkcyjnej bazy, sekretów ani przesłanych plików
mediów. Obrazy w `static/` są częścią kodu; pliki użytkowników w `media/`
wymagają osobnej kopii.
