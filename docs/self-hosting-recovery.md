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
Produkcyjny Gunicorn używa wyłącznie roli PostgreSQL
`sklepzdoniczkami_prod_web_limited`; nie jest ona właścicielem bazy ani schematu.
Rola `sklepzdoniczkami_prod` jest właścicielem bazy i służy wyłącznie migracjom.
Konto systemowe `sklepzdoniczkami-migrator` wykonuje migracje; ma
dostęp do kodu i venv, ale nie jest kontem usługi.

Pliki `development.env`, `preprod.env` i `app.env` są osobno dostępne tylko
odpowiedniej grupie usługi; `app.env` zawiera poświadczenia wyłącznie ograniczonej
roli runtime. Plik `migration.env` jest własnością roota, dostępny tylko grupie
konta migracyjnego i zawiera poświadczenia właściciela bazy. Konto Gunicorna nie
należy do tej grupy. Nie pokazuj ani nie kopiuj zawartości tych plików. Katalog
`/etc/sklepzdoniczkami` pozwala na przejście do jawnie znanej ścieżki, ale nie
na listowanie. Checkouts i venv są czytelne dla usługi oraz konta migracyjnego;
lokalny checkout `.env` nie jest używany i instalator odrzuca go, jeśli jest
czytelny grupowo lub publicznie. Systemd ogranicza dostęp procesu m.in. przez
`ProtectSystem`, `ProtectHome`, `PrivateTmp`, `NoNewPrivileges` i osobne
`StateDirectory`.

Instalator `scripts/setup_ubuntu_selfhost.sh` jest przeznaczony wyłącznie dla
nowego VPS produkcyjnego. Odmawia pracy, jeśli znajdzie istniejącą produkcyjną
rolę/bazę, usługę, pliki konfiguracyjne, katalog danych lub venv. Po błędzie
usuwa tylko zasoby utworzone podczas tego uruchomienia i nie usuwa niepustych
katalogów danych; błędy sprzątania wymagają ręcznej kontroli przed ponowną próbą.
Pakiety systemowe i konfiguracja repozytorium PGDG mogą pozostać zainstalowane.

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

Przed wdrożeniem development sprawdź, czy branch `dev` jest zsynchronizowany z
aktualną architekturą z `main`. Jeśli branch był długo nieaktualizowany, otwórz
PR `main` -> `dev`, usuń starą konfigurację w ramach przeglądanego diffu i
scal dopiero po wymaganym CI. Nie wdrażaj starego `dev` ani nie używaj
force-push/resetu. Bieżący commit na każdym środowisku sprawdzisz poleceniem
`git -C <ścieżka-checkoutu> rev-parse HEAD`.

## Dostęp do dev i preprod

Z poziomu repozytorium w Windows otwórz obie strony i sprawdź ich dostępność
jednym poleceniem:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_ovh_store.ps1
```

Skrypt otworzy tunel SSH, sprawdzi odpowiedź HTTP `200` i otworzy strony
development (`https://localhost:8001/`) oraz preprod
(`https://localhost:8002/`) w domyślnej przeglądarce. Po testach naciśnij Enter
w oknie PowerShell, aby zamknąć tunel. Do pojedynczego środowiska dodaj
`-Environment development` lub `-Environment preprod`. Domyślny klucz to
`~\.ssh\sklep-vps`, z awaryjnym wyborem `~\.ssh\sklepzdoniczkami_ovh_ed25519`;
możesz wskazać inny przez `-SshKeyPath`. Dodaj `-CheckOnly`, aby sprawdzić
statusy bez uruchamiania przeglądarki.

Certyfikat dla `localhost` jest self-signed i przeglądarka może pokazać
ostrzeżenie. Dev i
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

Uruchamiaj wdrożenia z Windows w katalogu repozytorium przez
`scripts/deploy_ovh.ps1`. Skrypt weryfikuje lokalnie, że commit należy do
oczekiwanej gałęzi i oba wymagane checki GitHub Actions zakończyły się
sukcesem. Łączy się do VPS przy użyciu lokalnego klucza SSH; nie dodawaj tego
klucza do GitHub ani do CI.

```powershell
git fetch origin
$developmentSha = (git rev-parse origin/dev).Trim()
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment development -Commit $developmentSha
```

Po PR `dev` -> `main` i testach na development wybierz commit z `main`,
wdrażaj go na preprod, a po akceptacji podaj **ten sam SHA** dla produkcji:

```powershell
git fetch origin
$releaseSha = (git rev-parse origin/main).Trim()
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment preprod -Commit $releaseSha
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment production -Commit $releaseSha
```

The execution-policy bypass applies only to those PowerShell processes; it does
not change the machine or user policy.

Skrypt na VPS sprawdza czystość checkoutu, pochodzenie commitu, migracje,
collectstatic i health-check odpowiedniej usługi. Produkcja dodatkowo wymaga
tego samego SHA w preprod oraz root-owned pliku
`/etc/sklepzdoniczkami/production-backup-verified`. Utwórz ten znacznik dopiero
po skonfigurowaniu zaszyfrowanej kopii PostgreSQL i `media/` poza VPS oraz
udanym teście odtworzenia:

```bash
sudo install -o root -g root -m 0600 /dev/null \
  /etc/sklepzdoniczkami/production-backup-verified
```

Udane wdrożenie preprod zapisuje testowany SHA w
`/etc/sklepzdoniczkami/preprod-deployed-commit`. Katalog `/etc/sklepzdoniczkami`
oraz ten plik muszą pozostać root-owned i niezapisywalne przez konto usługi
preprod. Nie umieszczaj znacznika w `/var/lib/sklepzdoniczkami-preprod`, bo
konto tej usługi może modyfikować ten katalog.

Po błędzie wdrożenie przywraca poprzedni kod i uruchamia usługę; **migracje bazy
nie są automatycznie cofane**. Projektuj migracje kompatybilnie wstecz i przed
wdrożeniem produkcyjnym miej aktualną, przetestowaną kopię. Nie kopiuj `.env`,
lokalnej bazy ani katalogu `media` między środowiskami.

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

Jeśli masz wcześniej pobrany zaszyfrowany pakiet bazy w formacie GitHub Actions
(`.tgz` z metadanymi HMAC), repozytorium zawiera narzędzie
`scripts/restore_github_production_backup.py`. Uruchom je z katalogu
`/opt/sklepzdoniczkami` jako root, podając dokładnie sprawdzony pakiet; narzędzie
czyta poświadczenia właściciela z `migration.env`, weryfikuje HMAC, pyta o klucze
i wymaga jawnego potwierdzenia przed nadpisaniem lokalnej bazy produkcyjnej.
`pg_restore` używa roli-właściciela, a migracje wykonuje dedykowane konto
migracyjne. Narzędzie zatrzymuje usługę sklepu na czas odtworzenia i pozostawia
ją zatrzymaną, jeśli odtworzenie się nie powiedzie. Odtwarza wyłącznie bazę, nie
pliki `media/`; nie tworzy nowych kopii zapasowych i nie zastępuje kopii offsite.

```bash
sudo /opt/sklepzdoniczkami/.venv/bin/python \
  /opt/sklepzdoniczkami/scripts/restore_github_production_backup.py \
  /path/to/verified-backup.tgz
```

Repozytorium nie zawiera baz, sekretów ani plików użytkowników. Obrazy
ilustracyjne w `static/` są kodem i podlegają wdrożeniu razem z aplikacją;
pliki użytkowników w katalogach `/var/lib/sklepzdoniczkami-*/media` wymagają
osobnej kopii.

## Płatności, e-mail i administrator

Stripe i SMTP nie są skonfigurowane. Nie przyjmuj płatności ani nie zakładaj,
że reset hasła wysyła wiadomość, dopóki integracje nie zostaną skonfigurowane
i przetestowane. Nie umieszczaj haseł administratora, kluczy SSH ani wartości
plików środowiskowych w Git, logach lub rozmowie.

Ostatni bezpieczny odczyt konfiguracji produkcji wykazał `STRIPE_ENABLED=False`,
brak skonfigurowanych parametrów SMTP, zero aktywnych produktów i zero
produktów ze stanem magazynowym większym od zera. HTTP 200 nie oznacza gotowości
do sprzedaży. Przed otwarciem sklepu skonfiguruj klucze live i webhook Stripe,
SMTP, prawdziwe produkty/ceny/stany oraz niezależne kopie bazy i mediów z
udanym testem odtworzenia.
