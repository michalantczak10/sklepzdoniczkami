# OVH: operacje, wdrożenia i odzyskiwanie

Runbook dotyczy VPS OVH i nie zawiera sekretów.

## Aktualna konfiguracja

- VPS `vps-13bc3512.vps.ovh.net`, Ubuntu 26.04, IPv4 `141.94.224.49`.
- PostgreSQL 18 działa lokalnie na VPS. Firewall nie wystawia portu `5432`.
- Publiczny Caddy obsługuje `sklepzdoniczkami.pl` i `www` oraz przekazuje ruch
  do produkcyjnego Gunicorna na `127.0.0.1:8000`.
- Development i preprod nasłuchują tylko na loopback `127.0.0.1:8001` i
  `127.0.0.1:8002`; dostęp zdalny jest przez SSH tunnel.
- Publiczne porty VPS: SSH 22, HTTP 80 i HTTPS 443.

| Środowisko | Kod / Python | Usługa i baza | Dane trwałe |
| --- | --- | --- | --- |
| Development | `/opt/sklepzdoniczkami-development`, własne `.venv`, commit `da455da` z `main` | `sklepzdoniczkami-development.service`, `sklepzdoniczkami_dev` | `/var/lib/sklepzdoniczkami-development` |
| Preprod | `/opt/sklepzdoniczkami-preprod`, własne `.venv`, commit `da455da` z `main` | `sklepzdoniczkami-preprod.service`, `sklepzdoniczkami_preprod` | `/var/lib/sklepzdoniczkami-preprod` |
| Produkcja | `/opt/sklepzdoniczkami`, własne `.venv`, commit `adc66a9` | `sklepzdoniczkami.service`, `sklepzdoniczkami_prod` | `/var/lib/sklepzdoniczkami-production` |

Każdy proces działa jako osobny systemowy użytkownik bez powłoki logowania.
Pliki `development.env`, `preprod.env` i `app.env` są osobno dostępne tylko
odpowiedniej grupie usługi; nie pokazuj ich zawartości. Katalog
`/etc/sklepzdoniczkami` pozwala na przejście do jawnie znanej ścieżki, ale nie
na listowanie. Checkouts, wirtualne środowiska, katalogi mediów i jednostki
systemd są rozdzielone. Systemd ogranicza dostęp procesu m.in. przez
`ProtectSystem`, `ProtectHome`, `PrivateTmp`, `NoNewPrivileges` i osobne
`StateDirectory`.

## Certyfikaty TLS dla dev i preprod

Jednostki dev/preprod terminują TLS bezpośrednio w Gunicornie. Każde środowisko
potrzebuje własnego certyfikatu self-signed dla `localhost` i prywatnego klucza;
nie commituj tych plików ani nie współdziel kluczy między usługami. Utwórz je
na VPS przed pierwszym uruchomieniem lub odtworzeniem usług:

```bash
sudo install -d -o root -g root -m 0711 /etc/sklepzdoniczkami
sudo install -d -o root -g root -m 0711 /etc/sklepzdoniczkami/tls

sudo openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
  -keyout /etc/sklepzdoniczkami/tls/development.key \
  -out /etc/sklepzdoniczkami/tls/development.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
sudo chown root:sklepzdoniczkami-development /etc/sklepzdoniczkami/tls/development.key
sudo chmod 0640 /etc/sklepzdoniczkami/tls/development.key
sudo chmod 0644 /etc/sklepzdoniczkami/tls/development.crt

sudo openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
  -keyout /etc/sklepzdoniczkami/tls/preprod.key \
  -out /etc/sklepzdoniczkami/tls/preprod.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
sudo chown root:sklepzdoniczkami-preprod /etc/sklepzdoniczkami/tls/preprod.key
sudo chmod 0640 /etc/sklepzdoniczkami/tls/preprod.key
sudo chmod 0644 /etc/sklepzdoniczkami/tls/preprod.crt
```

Certyfikaty wygasają po roku; przed wygaśnięciem wygeneruj nową parę dla
odpowiedniego środowiska i zrestartuj tylko jego usługę. Ostrzeżenie przeglądarki
jest oczekiwane dla self-signed `localhost`; używaj tunelu SSH i kont testowych.

**Stan branchy wymaga naprawy przed kolejnym wdrożeniem:** `dev` (`65522f2`)
zawiera jeszcze ustawienia Render/Neon i jest rozbieżny z `main` (`da455da`).
Nie wdrażaj go. Zsynchronizuj `main` do `dev` przez PR, rozwiąż konflikty,
usuń konfigurację starego hostingu i przepuść CI. Development i preprod
działają obecnie na bezpiecznym checkout `main` `da455da`; produkcja nadal
działa na `adc66a9`. Nie wykonuj force-push/resetu `dev`.

## Dostęp do dev i preprod

Na Windows uruchom tunel i pozostaw terminal otwarty:

```powershell
ssh -N -i "$HOME\.ssh\sklep-vps" `
  -L 8001:127.0.0.1:8001 `
  -L 8002:127.0.0.1:8002 `
  ubuntu@141.94.224.49
```

Pozostaw okno tunelu otwarte. Development: `https://localhost:8001/`;
preprod: `https://localhost:8002/`. Status HTTP możesz sprawdzić w drugim
oknie PowerShell:

```powershell
curl.exe -k -sS -o NUL -w "dev HTTP %{http_code}`n" https://localhost:8001/
curl.exe -k -sS -o NUL -w "preprod HTTP %{http_code}`n" https://localhost:8002/
```

Oczekiwany status to `200`. `-k` jest tylko do sprawdzenia dostępności przez
tunel SSH, nie do logowania ani wysyłania poufnych danych. Certyfikat dla
`localhost` jest self-signed i przeglądarka może pokazać ostrzeżenie. Dev i
preprod kończą TLS bezpośrednio w Gunicornie, dlatego ich jednostki ustawiają
`SECURE_SSL_REDIRECT=False`; ustawienie `SECURE_PROXY_SSL_HEADER` dotyczy
publicznej produkcji za Caddy. Porty Django i PostgreSQL muszą pozostać
niedostępne z Internetu. Hasła, tokeny płatnicze i prawdziwe dane klientów nie
powinny być używane w development/preprod.

## Kontrola stanu usług

```bash
sudo systemctl status sklepzdoniczkami-development.service
sudo systemctl status sklepzdoniczkami-preprod.service
sudo systemctl status sklepzdoniczkami.service
sudo systemctl status postgresql caddy
sudo journalctl -u sklepzdoniczkami-development.service -n 100 --no-pager
sudo journalctl -u sklepzdoniczkami-preprod.service -n 100 --no-pager
sudo journalctl -u sklepzdoniczkami.service -n 100 --no-pager
```

Jednostki źródłowe znajdują się w `deploy/`. Po zmianie Caddy najpierw
sprawdź konfigurację, dopiero potem ją przeładuj:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Bezpieczne wdrażanie

Nie wykonuj `git pull` w katalogu produkcyjnym bezpośrednio z `main`. Wybierz
konkretny commit i zachowaj go w historii wdrożenia. Deployment jest ręczny;
GitHub Actions uruchamia testy, ale nie ma dostępu SSH do VPS.

1. Upewnij się, że commit jest osiągalny z właściwego brancha: `dev` dla
   developmentu, `main` dla preprod i produkcji. Nie używaj obecnego `dev`,
   dopóki branch nie zostanie zsynchronizowany z `main`.
2. Sprawdź czystość właściwego checkoutu i pobierz kod jako administrator
   serwera. Osobne ścieżki checkoutów są wymienione wyżej. Używaj tylko
   zatwierdzonego SHA; nie kopiuj `.env`, lokalnej bazy ani katalogu `media`.
3. Przed migracją sprawdź konfigurację Django, nazwę bazy i migracje na
   docelowej usłudze. Wdrożenie kodu nie może zmieniać URL/roli innego
   środowiska.
4. Zastosuj migracje tylko w docelowej bazie, zbierz `staticfiles` i zrestartuj
   wyłącznie odpowiadającą jej usługę. Sprawdź `/admin/login/`, logi i
   publiczną stronę po wdrożeniu produkcji. Dla produkcji testuj dokładnie ten
   sam SHA wcześniej na preprod.
5. Migracje muszą być zgodne wstecznie podczas wdrożenia; wycofanie kodu nie
   cofa zmian schematu ani danych. Przy błędzie zatrzymaj promocję i oceń
   odtworzenie lub osobną migrację naprawczą.

Nie uruchamiaj `load_sample_products` poza developmentem. Nie synchronizuj
danych development -> preprod/produkcja. Nie używaj w produkcji komend
`seed_preprod_data` ani `seed_production_preview_catalog` bez osobnej,
świadomej decyzji i sprawdzenia ich zabezpieczeń.

## Kopie zapasowe i odzyskiwanie

Automatyczna, niezależna kopia bazy PostgreSQL i `media/` poza VPS **nie jest
skonfigurowana**. Lokalna kopia na tym samym serwerze nie chroni przed utratą
VPS. Zanim produkcja zacznie przechowywać zamówienia lub dane klientów,
skonfiguruj zaszyfrowane kopie poza serwerem, retencję, monitoring i test
odtworzenia do osobnej bazy. Do tego czasu nie wykonuj migracji produkcyjnej,
która może utrudnić odtworzenie, i nie traktuj serwera jako gotowego do
przyjmowania zamówień.

Na VPS pozostawiono wcześniejszy jednorazowy dump w
`/var/backups/sklepzdoniczkami/`. Nie odtwarzaj go bez świadomej decyzji:
może zawierać starsze dane. Zmiany izolujące usługi mają osobną kopię
konfiguracyjną w tym samym katalogu, ale nie jest to kopia zapasowa poza VPS.

Repozytorium nie zawiera baz, sekretów ani plików użytkowników. Obrazy
ilustracyjne w `static/` są kodem i podlegają wdrożeniu razem z aplikacją;
pliki użytkowników w katalogach `/var/lib/sklepzdoniczkami-*/media` wymagają
osobnej kopii.

## Płatności, e-mail i administrator

Stripe i SMTP nie są skonfigurowane. Nie przyjmuj płatności ani nie zakładaj,
że reset hasła wysyła wiadomość, dopóki integracje nie zostaną skonfigurowane
i przetestowane. Nie umieszczaj haseł administratora, kluczy SSH ani wartości
plików środowiskowych w Git, logach lub rozmowie.
