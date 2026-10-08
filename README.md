# Sklepzdoniczkami

Sklep internetowy oparty na Django: katalog produktów, koszyk, zamówienia,
płatności Stripe, konta klientów i panel administratora.

## Środowiska

Wszystkie uruchomione środowiska aplikacji i bazy danych znajdują się na VPS
OVH. Komputer developerski służy do edycji kodu i opcjonalnego uruchamiania
testów; nie hostuje sklepu ani jego baz.

| Środowisko | Baza i rola PostgreSQL | Usługa | Dostęp |
| --- | --- | --- | --- |
| Development | `sklepzdoniczkami_dev` | `sklepzdoniczkami-development.service` | SSH tunnel, port loopback 8001 |
| Preprod | `sklepzdoniczkami_preprod` | `sklepzdoniczkami-preprod.service` | SSH tunnel, port loopback 8002 |
| Produkcja | `sklepzdoniczkami_prod` | `sklepzdoniczkami.service` | Caddy, `https://sklepzdoniczkami.pl` |

Produkcyjna baza nie zawiera przykładowego katalogu, zamówień ani klientów;
nie seeduj do niej danych developerskich.

Usługi development i preprod oraz PostgreSQL nie są wystawione publicznie.
Aby sprawdzić obie wersje sklepu, uruchom jedno polecenie z katalogu repozytorium:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_ovh_store.ps1
```

Skrypt otwiera bezpieczny tunel SSH, sprawdza, czy obie strony zwracają HTTP
`200`, po czym otwiera je w przeglądarce. Po sprawdzeniu wróć do PowerShell
i naciśnij Enter — tunel zostanie zamknięty. Możesz wskazać jedno środowisko:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_ovh_store.ps1 -Environment development
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_ovh_store.ps1 -Environment preprod
```

Samo sprawdzenie dostępności bez otwierania przeglądarki wykonasz przez dodanie
`-CheckOnly`.

Domyślnie skrypt wybiera klucz SSH `~\.ssh\sklep-vps`, a jeśli go nie ma —
`~\.ssh\sklepzdoniczkami_ovh_ed25519`. Inny klucz można podać parametrem
`-SshKeyPath`. Przeglądarka może ostrzec o self-signed certyfikacie `localhost`;
kontynuuj tylko dla tych lokalnych adresów i używaj wyłącznie kont testowych.
Nie wpisuj haseł produkcyjnych ani danych płatniczych. Nie otwieraj portu
PostgreSQL ani portów Django w firewallu.

Każda usługa ma osobny checkout i `.venv` pod `/opt`, odrębne konto systemowe
bez logowania, katalog mediów pod `/var/lib` oraz własny plik środowiskowy.
Uruchomiony proces development nie może czytać sekretów preprod ani produkcji.
Dev i preprod kończą TLS bezpośrednio w Gunicornie i są dostępne tylko przez
tunel SSH; ich jednostki systemd wyłączają przekierowanie HTTPS Django, które
oczekuje nagłówka od reverse proxy. Ciasteczka pozostają secure przy `DEBUG=False`.

## Praca na branchach i promocja wydań

### Gałęzie i PR-y

Wystarczą **dwie stałe gałęzie: `dev` i `main`**. `dev` jest integracją zmian,
`main` — kodem zatwierdzonym do wydania. Preprod i produkcja są środowiskami
wdrażanymi po SHA, a nie osobnymi branchami; dodatkowe stałe branche
`preprod`/`prod` nie poprawiłyby izolacji, za to zwiększyłyby ryzyko rozjazdu.
Branche `feature/...`, `fix/...` i `chore/...` są krótkotrwałe i po PR powinny
znikać. GitHub usuwa branche PR automatycznie po scaleniu.

Ochrona `dev` i `main` wymaga przejścia `Django tests`, `End-to-end tests
(Playwright)`, `PostgreSQL tests` oraz rozwiązania wątków review; bezpośredni
push i force-push są zablokowane, także dla administratorów. Wymagane approvals
wynoszą `0`, więc żaden człowiek nie musi zatwierdzać PR-a. Dwa niezależne
przeglądy AI mogą być użyte jako dodatkowa kontrola, ale GitHub nie egzekwuje
ich jako warunku merge.

1. Zaczynaj `feature/...`, `fix/...` lub `chore/...` od aktualnego `dev`.
   Otwórz PR do `dev`; poczekaj na wszystkie wymagane checki i rozwiąż wszystkie
   wątki. Dla zwykłych zmian scalaj przez squash, aby historia `dev` była
   czytelna. CI uruchamia testy na GitHub-hosted runners z SQLite i PostgreSQL,
   nie wdraża aplikacji ani nie łączy się z bazami OVH.
2. Po merge wdrażaj pełny SHA `origin/dev` wyłącznie na development:
   ```powershell
   git fetch --prune origin
   $sha = (git rev-parse origin/dev).Trim()
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment development -Commit $sha
   ```
   Skrypt sprawdza, czy SHA należy do właściwej gałęzi i czy wymagane checki
   `Django tests`, `End-to-end tests (Playwright)` i `PostgreSQL tests`
   zakończyły się sukcesem.
3. Po testach akceptacyjnych otwieraj PR `dev` -> `main`. Scalaj go przez
   **merge commit**, aby zachować relację historii gałęzi. Po scaleniu otwórz
   synchronizujący PR `main` -> `dev` i również poczekaj na wymagane checki.
   Dzięki temu kod obu branchy pozostaje identyczny, a `main` jest przodkiem
   `dev`. Taki synchronizujący PR może nie zmieniać plików — przenosi historię
   merge’a i nadal przechodzi przez ochronę branchy. Nie kontynuuj promocji
   kolejnego wydania, dopóki synchronizacja nie zostanie scalona.
4. Wybierz pełny SHA z `main` i wdrażaj go najpierw na preprod:
   ```powershell
   git fetch --prune origin
   $sha = (git rev-parse origin/main).Trim()
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment preprod -Commit $sha
   ```
5. Po akceptacji preprod wdrażaj **ten sam SHA** na produkcję:
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment production -Commit $sha
   ```
   Skrypt blokuje produkcję, jeśli ten sam SHA nie przeszedł wcześniej
   wdrożenia i testów health-check na preprod albo brakuje root-owned znaczników
   `/etc/sklepzdoniczkami/preprod-deployed-commit` i
   `/etc/sklepzdoniczkami/production-backup-verified`. Drugi potwierdza
   zweryfikowaną kopię bazy i mediów poza VPS. `Bypass` dotyczy wyłącznie
   uruchomionego procesu PowerShell i nie zmienia trwałej polityki komputera ani
   użytkownika.

Nagły hotfix produkcyjny zaczynaj od `main`, scalaj PR-em do `main`, sprawdź go
na preprod i wdrażaj ten sam SHA; następnie otwórz PR synchronizujący `main` do
`dev` przed wznowieniem zwykłej pracy. Przy nieoczekiwanym rozjechaniu branchy
nie wdrażaj `dev`, dopóki synchronizacja przez PR i wymagane CI nie przejdą.
Nie używaj force-push ani resetu branchy. Skrypt wdrożeniowy korzysta z
lokalnego SSH i GitHub CLI; klucz SSH nie trafia do GitHub Actions. GitHub CLI
zainstaluj i uwierzytelnij jednorazowo na Windows:

```powershell
winget install --id GitHub.cli --exact
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

Dependabot sprawdza co tydzień aktualizacje Pythona i GitHub Actions, tworząc
zwykłe PR-y do `dev`. Alerty podatności i automatyczne PR-y poprawek
bezpieczeństwa są włączone; poprawki bezpieczeństwa mogą trafiać bezpośrednio
do domyślnego `main`, ale również muszą przejść wymagane CI, preprod i późniejszą
synchronizację `main` -> `dev`. Nie włączaj auto-merge.

Zmiany schematu dodawaj jako migracje Django w tym samym PR co kod. Uruchamiaj
migracje osobno i wyłącznie dla docelowego środowiska. Dane developerskie,
konta, zamówienia i stany magazynowe nie są kopiowane między bazami. Komenda
`load_sample_products` jest przeznaczona wyłącznie dla developmentu; nie
uruchamiaj jej w preprod ani produkcji. Produkcja nie ma być automatycznie
zasilana zawartością dev.

## Testy

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest -q --ds=config.settings_test
pytest e2e -m e2e --browser chromium --browser-channel msedge --ds=config.settings_test
```

Testy używają odizolowanej bazy SQLite in-memory. Na Windows wymagają
zainstalowanego Microsoft Edge; alternatywnie pobierz przeglądarkę poleceniem
`playwright install chromium` i usuń `--browser-channel msedge`. Nie uruchamiaj
lokalnego `runserver`, PostgreSQL, kontenerów ani kopii produkcji; przeglądaj
dev/preprod przez SSH tunnel. Konfigurację środowisk na VPS przechowują prywatne pliki
`/etc/sklepzdoniczkami/{development.env,preprod.env,app.env}` poza repozytorium.
Nie wyświetlaj ani nie kopiuj ich sekretów do logów, GitHub Actions lub Git.

## Katalog przykładowy i grafiki

Development seed tworzy trzy kategorie oraz osiem powtarzalnie aktualizowanych
produktów z przykładowymi cenami i stanami: dwa betonowe, dwa drewniane i cztery
plastikowe (w tym dwa wcześniejsze przykłady). Grafiki SVG w
`sklepzdoniczkami/static/sklepzdoniczkami/img/` są oryginalnymi ilustracjami,
nie zdjęciami ani potwierdzeniem specyfikacji towaru. Zweryfikuj rzeczywisty
produkt, cenę, stan i zdjęcie przed publikacją w produkcji.

## Audyt plików i konfiguracji

- Zachowano Django, migracje, CI, konfigurację produkcyjnego Caddy oraz
  provisioning VPS.
- Usunięto lokalne profile hostingu Windows/WSL, skrypty modyfikujące `hosts`,
  lokalny Docker Compose, przykładową lokalną konfigurację bazy i zależność
  Waitress. Były nieużywane dla OVH, a konfiguracja WSL wcześniej mogła
  przekierować domenę produkcyjną na lokalny adres.
- Zachowano stare JPG, ponieważ służą jeszcze za ilustracje strony głównej i
  nieprodukcyjnego katalogu preview; ich źródła/licencje są w
  [README_IMAGES.md](README_IMAGES.md).
- Usunięto nieużywaną klasę `CategoryListView`, identyczny duplikat
  `Caddyfile.example`, dwa nieużywane zdjęcia oraz sześć kopii obrazów z
  `docs/sample-images/`; używane zdjęcia pozostają w katalogu statycznym
  aplikacji.
- Wartości środowiskowe mają jawne nazwy baz i wymagane klucze dla preprod/prod;
  statyczne URL-e zaczynają się od `/static/`, by działały także na zagnieżdżonych
  ścieżkach produktów.
- `.gitignore` wyklucza lokalne `.env`, bazy SQLite, `media/` i artefakty kopii.
  Mogą istnieć w roboczym katalogu, ale nie dodawaj ich do Git ani nie przesyłaj
  w PR; przechowuj kopie poza repozytorium i szyfruj je.

## Operacje i odzyskiwanie

Runbook VPS, usług, wdrożeń i obecnych ograniczeń odzyskiwania:
[docs/self-hosting-recovery.md](docs/self-hosting-recovery.md).

**Pozostałe ryzyko:** na VPS nie ma skonfigurowanej ani przetestowanej kopii
zapasowej poza serwerem. Nie przechowuj tam jedynej kopii zamówień ani danych
klientów; przed sprzedażą skonfiguruj niezależną kopię i przetestuj odtworzenie.
Pozostałe artefakty GitHub pochodzą ze starego workflow tworzącego kopię
wyłącznie bazy Neon; nie obejmują bieżącej bazy OVH ani mediów i nie są
potwierdzeniem aktualnego backupu.

**Gotowość sprzedażowa (kontrola 2026-10-08):** Stripe jest wyłączony, SMTP
nie jest skonfigurowany, produkcyjna baza ma zero aktywnych produktów i zero
produktów ze stanem większym od zera, a znacznik zweryfikowanej kopii offsite
nie istnieje. Odpowiedź HTTP 200 potwierdza tylko dostępność aplikacji. Nie
przyjmuj zamówień, dopóki nie skonfigurujesz płatności live i webhooka Stripe,
poczty transakcyjnej, prawdziwego katalogu ze stanami oraz zaszyfrowanych kopii
bazy i mediów z przetestowanym odtworzeniem.
