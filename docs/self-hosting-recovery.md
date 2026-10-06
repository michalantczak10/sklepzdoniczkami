# Self-hosting i odzyskiwanie sklepu

Ten dokument jest głównym runbookiem uruchomienia sklepu poza Renderem. Ma
prowadzić od czystego komputera do bezpiecznie przetestowanej kopii sklepu,
bez polegania na historii rozmów.

## Stan i wybór platformy

Ostatni znany stan projektu:

- publiczna produkcja działa na Renderze i używa produkcyjnej bazy Neon;
- na komputerze deweloperskim działa odizolowana kopia development na
  PostgreSQL pod `127.0.0.1:5435`;
- skrypty Windows do PostgreSQL/Waitress i instrukcja
  [`windows-self-hosting.md`](windows-self-hosting.md) są w repozytorium;
- nie zmieniono DNS domeny, routera ani publicznego hostingu.

Windows 11 Home sam w sobie nie oznacza zakazu używania PostgreSQL. Problem
instalacji na konkretnym laptopie może wynikać z uprawnień, polityk urządzenia,
braku miejsca lub konfliktu portu. Najpierw należy sprawdzić dokładny komunikat
instalatora, a nie zakładać, że trzeba reinstalować system.

Na laptop-serwer rekomendowany jest Ubuntu Server LTS z natywnym PostgreSQL,
systemd i Caddy. Docker nie jest wymagany. Repozytorium zawiera skrypt
instalujący zależności aplikacji i lokalną bazę na Ubuntu z systemd,
szablon usługi systemd oraz przykładową konfigurację Caddy. Skrypt nie był
jeszcze uruchomiony na laptopie z Ubuntu; przed użyciem produkcyjnym trzeba
przetestować go na czystej instalacji i zweryfikować backup/restore.

## Co musi być w repozytorium, a co poza nim

Repozytorium przechowuje kod aplikacji, migracje bazy, przykładową konfigurację,
skrypty i instrukcje. Nie przechowuje i nie powinno przechowywać:

- haseł, `.env`, kluczy Django/Stripe/SMTP ani kluczy GitHub/Render;
- kopii produkcyjnej bazy danych, danych klientów/zamówień ani prywatnych
  uploadów z `media/`;
- plików instalacyjnych systemu operacyjnego lub PostgreSQL.

Na wypadek utraty hostingu należy niezależnie od Git utrzymywać aktualne,
zaszyfrowane kopie bazy i `media/`, a klucze ich odszyfrowania przechowywać
osobno, np. w menedżerze haseł. Repozytorium samo nie zawiera danych, których
potrzebowałby nowy sklep do odtworzenia rzeczywistych produktów, kont i
zamówień. Nie zaliczać do jedynej kopii zapasowej tymczasowych GitHub Actions
artefaktów: mają ograniczony okres przechowywania.

Obecny workflow GitHub Actions przechowuje zaszyfrowane kopie samej bazy jako
artefakty przez 90 dni; nie zawierają plików `media/`. Odszyfrowanie wymaga
sekretów `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY` z GitHub Environment
`production`. GitHub nie pozwala odzyskać wartości istniejących sekretów,
dlatego należy przechować je od początku również w menedżerze haseł/offline.
Artefakt nie jest długoterminową kopią, dopóki nie zostanie pobrany,
zweryfikowany i skopiowany do bezpiecznego, niezależnego miejsca wraz z
potrzebnymi kluczami. Nie odszyfrowuj produkcyjnej kopii na komputerze
współdzielonym ani do katalogu repozytorium.

Przed awarią należy też upewnić się, że właściciel ma dostęp do repozytorium,
rejestratora domeny/DNS, Stripe, poczty oraz kopii i kluczy backupu. Nie
wklejać tych sekretów do rozmowy, commitów ani logów.

## Uruchomienie kopii na Windows

Zweryfikowany lokalny wariant opisano w
[`windows-self-hosting.md`](windows-self-hosting.md). W skrócie, po instalacji
Pythona 3.11+ i PostgreSQL 18:

```powershell
git clone https://github.com/michalantczak10/sklepzdoniczkami.git
Set-Location sklepzdoniczkami
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_selfhost.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_windows_selfhost.ps1
```

Serwer testowy nasłuchuje tylko na `127.0.0.1:8000`, a lokalny PostgreSQL
tylko na `127.0.0.1:5435`. Wariant `development` jest przeznaczony do testów;
nie wystawiać go do internetu. Skrypt tworzy lokalną bazę, nie odtwarza
automatycznie bieżących danych produkcyjnych ani plików mediów.

### Windows 11 z Ubuntu w WSL2

Jeśli polityka integralności kodu Windows blokuje natywne biblioteki
PostgreSQL, pozostaw ochronę Windows włączoną i uruchom środowisko development
w Ubuntu 24.04 LTS przez WSL2. W PowerShell zainstaluj WSL i dystrybucję:

```powershell
wsl --install --distribution Ubuntu-24.04
```

Po wymaganym restarcie uruchom Ubuntu, utwórz zwykłego użytkownika Linux i
sprawdź, że `systemd` działa (`systemctl is-system-running`). Jeśli dystrybucja
nie ma włączonego `systemd`, dodaj `systemd=true` w sekcji `[boot]` pliku
`/etc/wsl.conf`, zachowując jego pozostałe ustawienia, a następnie wykonaj
`wsl --shutdown` i uruchom Ubuntu ponownie.

W terminalu Ubuntu przygotuj checkout zgodnie z procedurą poniżej: zainstaluj
Git, sklonuj repozytorium do `/opt/sklepzdoniczkami` należącego do zwykłego
użytkownika i uruchom `sudo bash scripts/setup_ubuntu_selfhost.sh development`.
Skrypt tworzy osobną bazę development i włącza lokalną usługę systemd; nie
odtwarza danych produkcyjnych, nie modyfikuje bazy Windows/Neon i nie konfiguruje
publicznego dostępu. W Windows strona jest pod
`http://127.0.0.1:8000/`, a panel pod `http://127.0.0.1:8000/admin/`.
Po pierwszym setupie możesz załadować pięć syntetycznych produktów ze zdjęciami
poleceniem `python manage.py load_sample_products` w katalogu checkoutu.
Polecenie odmawia działania poza `APP_ENV=development` i można je bezpiecznie
uruchamiać ponownie.

Po restarcie Windows uruchom dystrybucję poleceniem
`wsl --distribution Ubuntu-24.04`; wtedy systemd uruchomi włączoną usługę.
Pozostaw sesję Ubuntu uruchomioną podczas korzystania ze sklepu; po zakończeniu
wszystkich procesów WSL może zatrzymać dystrybucję i lokalne usługi.
PostgreSQL pozostaje prywatny w Ubuntu. Nie zmieniaj DNS ani ustawień routera
dla developmentu.

### Lokalne profile preprod i production obok development

Na komputerze z już działającym profilem development możesz utworzyć dwie
dodatkowe, odizolowane bazy i usługi:

```bash
cd /opt/sklepzdoniczkami
sudo bash scripts/setup_ubuntu_local_profiles.sh
```

Development pozostaje pod `http://127.0.0.1:8000/`. Lokalny preprod działa pod
`https://localhost:8001/`, a lokalna symulacja production pod
`https://localhost:8002/`. Każdy profil ma osobną bazę i rolę PostgreSQL
(`sklepzdoniczkami_dev`, `sklepzdoniczkami_preprod`,
`sklepzdoniczkami_prod`), osobny plik ustawień w
`/etc/sklepzdoniczkami/` i osobną usługę systemd. Profile preprod i production
używają samopodpisanego certyfikatu TLS dla `localhost`; przeglądarka pokaże
ostrzeżenie o zaufaniu do certyfikatu. Nie używaj tego certyfikatu na publicznej
domenie.

Skrypt wymaga, aby development był już skonfigurowany i działał. Preprod
otrzymuje syntetyczny katalog. Lokalna baza production jest pusta poza
migracjami i administratorem; nie są kopiowane konta, zamówienia ani media
klientów z Render/Neon. Stripe nie jest skonfigurowany, a wiadomości e-mail
pozostają w logu aplikacji. To są lokalne symulacje, nie publiczna produkcja;
nie zmieniają DNS, Rendera ani zdalnych baz. Wszystkie trzy usługi i PostgreSQL
nasłuchują wyłącznie na loopback.

Losowe dane logowania administratorów preprod i production skrypt zapisuje do
`~/.local/share/sklepzdoniczkami/local-profiles-credentials.txt` konta Linux
uruchamiającego `sudo`; plik ma uprawnienia `0600`. Nie dodawaj go do Git ani
nie publikuj. Usługi można kontrolować osobno:

```bash
sudo systemctl status sklepzdoniczkami-preprod sklepzdoniczkami-production
sudo systemctl stop sklepzdoniczkami-preprod sklepzdoniczkami-production
sudo systemctl start sklepzdoniczkami-preprod sklepzdoniczkami-production
```

Profile korzystają z tego samego checkoutu kodu, ale z odrębnych baz. Zmiana
kodu w tym checkoutcie wpływa na wszystkie lokalne profile po restarcie
odpowiedniej usługi. Lokalny profil production jest pustą symulacją do testów
konfiguracji; nie przywracaj do niego produkcyjnego backupu ani nie kieruj na
niego publicznej domeny w ramach tej procedury.

#### Lokalna domena na Windows

Jeżeli chcesz, aby `https://sklepzdoniczkami.pl` na tym laptopie otwierało
lokalny profil production zamiast publicznego Rendera, skonfiguruj proxy
Caddy i lokalny Gunicorn upstream w WSL:

```bash
cd /opt/sklepzdoniczkami
sudo bash scripts/setup_ubuntu_local_domain.sh
```

Skrypt instaluje Caddy z oficjalnego, podpisanego repozytorium pakietów,
wiąże go wyłącznie z `127.0.0.1`, ustawia certyfikat lokalnego urzędu Caddy i
oddzielny upstream Gunicorna na `127.0.0.1:8003`. Nie zmienia publicznego DNS.
Kopiuje także bieżący plik ustawień production do
`/etc/sklepzdoniczkami/production.env.before-local-domain`.

Następnie skopiuj wskazany przez skrypt plik `root.crt` z WSL do
`$env:TEMP\sklepzdoniczkami-wsl-root.crt` w Windows. Uruchom PowerShell jako
administrator i wykonaj z katalogu repozytorium:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_local_domain.ps1 `
  -Mode Install `
  -CertificatePath "$env:TEMP\sklepzdoniczkami-wsl-root.crt"
```

Skrypt robi kopię zapasową pliku `hosts`, dodaje oznaczony wpis dla domeny i
ufa certyfikatowi Caddy tylko w magazynie bieżącego użytkownika Windows.
Aby cofnąć lokalne przekierowanie oraz zaufanie certyfikatu, uruchom
PowerShell jako administrator:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_local_domain.ps1 `
  -Mode Remove `
  -CertificatePath "$env:TEMP\sklepzdoniczkami-wsl-root.crt"
```

Zmiana `hosts` dotyczy tylko tego laptopa; inne urządzenia nadal trafią na
publiczny adres Rendera. Lokalna baza production jest pusta do czasu
odtworzenia zweryfikowanego backupu, więc po przekierowaniu domena otworzy
lokalny sklep bez rzeczywistego katalogu, klientów ani zamówień.

## Uruchomienie na Ubuntu Server

Zainstaluj Ubuntu Server LTS i aktualizacje systemu. Zainstaluj Git, utwórz
katalog checkoutu dla zwykłego konta administratora (nie root), sklonuj
repozytorium i uruchom skrypt:

```bash
sudo apt update
sudo apt install --yes git
sudo install -d -o "$USER" -g "$(id -gn)" -m 0750 /opt/sklepzdoniczkami
git clone https://github.com/michalantczak10/sklepzdoniczkami.git /opt/sklepzdoniczkami
cd /opt/sklepzdoniczkami
sudo bash scripts/setup_ubuntu_selfhost.sh development
```

Skrypt dodaje oficjalne repozytorium PostgreSQL, instaluje PostgreSQL 18,
Python i venv, tworzy nową prywatną rolę i bazę development, zapisuje losowe
sekrety w
`/etc/sklepzdoniczkami/app.env`, instaluje zależności, wykonuje migracje,
zbiera pliki statyczne, tworzy administratora i włącza usługę systemd. Usługa
nasłuchuje tylko na `127.0.0.1:8000`; PostgreSQL nie jest wystawiany do
internetu. Logi: `sudo journalctl -u sklepzdoniczkami -f`.

Aby przygotować **pusty** lokalny profil produkcyjny na nowej instalacji,
użyj `sudo bash scripts/setup_ubuntu_selfhost.sh production`. Nie uruchamiaj
tego trybu jako procedury odzyskiwania bez wcześniejszego odtworzenia i
zweryfikowania danych. Skrypt celowo odmawia nadpisania istniejącej
konfiguracji, roli lub bazy. Nie odtwarza backupu, nie instaluje Caddy i nie
otwiera zapory/routera.

Plik `deploy/sklepzdoniczkami.service` jest szablonem kopiowanym i
uzupełnianym przez instalator. `deploy/Caddyfile` pokazuje proxy dla domeny;
zainstaluj stabilne wydanie Caddy z oficjalnego repozytorium i skopiuj
konfigurację:

```bash
sudo apt install --yes debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' |
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' |
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
sudo install -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy kończy TLS, a Django/Gunicorn pozostają na loopback. Nie otwieraj
portu 5432 ani 8000. W przypadku development nie kieruj publicznej domeny na
usługę.

### Odtworzenie bazy z backupu GitHub Actions

To przywraca tylko bazę danych. Potrzebujesz niewygasłego artefaktu z workflow
**Daily encrypted database backup** i wartości
`BACKUP_ENCRYPTION_KEY` oraz `BACKUP_HMAC_KEY` zapisanych wcześniej w
menedżerze haseł. GitHub nie pozwala odczytać istniejących wartości sekretów.
Jeśli brakuje któregokolwiek klucza albo artefakt wygasł, ta kopia nie jest
możliwa do odszyfrowania; nie próbuj odtwarzać zgadywanych kluczy.

Zaloguj GitHub CLI przez `gh auth login`, znajdź udane uruchomienie backupu
z ostatnich 90 dni w Actions i pobierz jego artefakt poza repozytorium:

```bash
gh run list --repo michalantczak10/sklepzdoniczkami --workflow db-backup.yml --limit 10
RUN_ID=WPISZ_ID_UDANEGO_URUCHOMIENIA
mkdir -m 0700 -p "$HOME/sklep-backup"
gh run download "$RUN_ID" \
  --repo michalantczak10/sklepzdoniczkami \
  --name "db-backup-package-${RUN_ID}.tgz" \
  --dir "$HOME/sklep-backup"
```

Po utworzeniu lokalnej konfiguracji `production`, sprawdź nazwę pliku
`db-backup-files-${RUN_ID}.tgz` w pobranym katalogu i uruchom z katalogu repo:

```bash
sudo .venv/bin/python scripts/restore_github_production_backup.py \
  "$HOME/sklep-backup/db-backup-files-${RUN_ID}.tgz"
```

Skrypt pyta o klucze bez wyświetlania ich, sprawdza skład archiwum, HMAC i
możliwość odczytu dumpa przez `pg_restore`, a przed zastąpieniem bazy wymaga
wpisania `RESTORE sklepzdoniczkami_prod`. Sprawdza, że celem jest baza
`sklepzdoniczkami_prod` na lokalnym PostgreSQL 18, zatrzymuje usługę na czas
odtwarzania i uruchamia ją dopiero po udanym restore, migracjach i odczycie
liczby użytkowników/produktów/zamówień. Jeśli restore się nie powiedzie,
usługa pozostanie zatrzymana; sprawdź bazę i logi, zanim ją uruchomisz.
Odszyfrowany dump znajduje się tylko w prywatnym katalogu tymczasowym i jest
usuwany po zakończeniu procesu.

**Backup Actions nie zawiera `media/`**, więc ten krok nie odtworzy
indywidualnie przesłanych plików. Obrazy będące w katalogu statycznym
repozytorium wrócą wraz z kodem; pozostałe pliki mediów wymagają osobnej,
aktualnej kopii. Nie przełączaj domeny, dopóki nie odzyskasz i nie sprawdzisz
potrzebnych mediów oraz pełnej funkcjonalności sklepu.

## Procedura awaryjnego uruchomienia produkcji

Nie zmieniać DNS, dopóki każdy punkt poniżej nie został wykonany i
zweryfikowany:

1. Przygotować laptop-serwer, aktualny system i zasilanie sieciowe. Dla
   Ubuntu Server LTS przetestować skrypt instalacyjny i usługę systemd na
   czystym systemie, a przed cutoverem osobno potwierdzić odtwarzanie backupu.
2. Sklonować `main` i zainstalować PostgreSQL oraz zależności dokładnie według
   instrukcji dla wybranego systemu. Utworzyć oddzielne środowisko produkcyjne
   i rolę/bazę `sklepzdoniczkami_prod`; nie podłączać aplikacji do starego
   publicznego Neon/Render URL przypadkowo.
3. Odtworzyć najnowszy sprawdzony backup produkcyjnej bazy i kopię `media/`.
   Używać tylko narzędzi PostgreSQL zgodnych z wersją źródłową; po odtworzeniu
   porównać liczbę użytkowników, produktów i zamówień. Nie uruchamiać
   produkcyjnego startu na pustej bazie, jeśli celem jest przywrócenie sklepu.
4. Wprowadzić prywatnie wymagane ustawienia `APP_ENV=production`,
   `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, URL i nazwę bazy,
   `DJANGO_SECRET_KEY_PRODUCTION`, Stripe live/webhook oraz SMTP. Jeśli płatność
   lub poczta nie są gotowe, jawnie odnotować wyłączoną funkcję; nigdy nie
   używać kluczy live w testach.
5. Wykonać migracje, `collectstatic`, sprawdzić panel administratora,
   katalog, logowanie, koszyk, zamówienie testowe bez obciążenia prawdziwej
   karty, media, logi i próbne odtworzenie backupu.
6. Skonfigurować automatyczny start i restart usługi aplikacji oraz PostgreSQL,
   HTTPS przez Caddy, firewall i router. Publicznie udostępniać wyłącznie TCP
   `80/443`; portu bazy i portu aplikacji nie wystawiać.
7. Sprawdzić publiczny adres IPv4, ewentualny CGNAT, aktualizację dynamicznego
   DNS i działanie z urządzenia poza domową siecią. Dopiero wtedy zmienić DNS
   `sklepzdoniczkami.pl` i `www`.
8. Po przełączeniu sprawdzić zakup/webhook, pocztę i kopię zapasową. Zachować
   możliwość rollbacku do starego hostingu do zakończenia okresu obserwacji;
   nie dopuścić do jednoczesnego przyjmowania zamówień przez dwie niezależne
   bazy produkcyjne.

## Granice obecnej automatyzacji

`scripts/clone_render_production_to_local.py` służy wyłącznie do początkowego
snapshotu z Render/Neon do pustej lokalnej bazy **development**. Wymaga dostępu
do Render API i nie jest procedurą odtwarzania produkcji po utracie hostingu.
Skrypty setup Windows/Ubuntu tworzą nową lokalną bazę, ale nie pobierają
automatycznie bieżących danych. Osobny
`scripts/restore_github_production_backup.py` weryfikuje i odtwarza bazę z
zaszyfrowanego artefaktu GitHub Actions do lokalnej bazy produkcyjnej; wymaga
ważnego artefaktu i kluczy przechowywanych poza GitHub. Nie ma jeszcze
automatycznego backupu/restore `media/`, a GitHub backup zawiera tylko bazę.
Instalator Ubuntu konfiguruje systemd, lecz nie instaluje Caddy, nie zarządza
backupami, routerem ani DNS. Dlatego repozytorium **nie wystarcza
samodzielnie do pełnego odzyskania aktualnego sklepu** bez dostępnego backupu
bazy, potrzebnych plików i kluczy szyfrujących.

Przed utratą starego hostingu należy dodać i przetestować niezależne,
automatyczne kopie bazy **i** mediów oraz procedurę pełnego odtworzenia na
czystym laptopie. Pierwsze uruchomienie `setup_ubuntu_selfhost.sh` należy
przetestować na kopii systemu przed przejściem na produkcję.
