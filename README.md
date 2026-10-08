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
Łącz się do nich z Windows przez tunel SSH:

```powershell
ssh -N -i "$HOME\.ssh\sklep-vps" `
  -L 8001:127.0.0.1:8001 `
  -L 8002:127.0.0.1:8002 `
  ubuntu@141.94.224.49
```

Pozostaw to okno otwarte i otwórz `https://localhost:8001/` (development)
lub `https://localhost:8002/` (preprod). W drugim oknie PowerShell możesz
sprawdzić samą odpowiedź HTTP:

```powershell
curl.exe -k -sS -o NUL -w "dev HTTP %{http_code}`n" https://localhost:8001/
curl.exe -k -sS -o NUL -w "preprod HTTP %{http_code}`n" https://localhost:8002/
```

Oczekiwany status to `200`. Opcja `-k` służy tu wyłącznie do sprawdzenia
dostępności przez tunel SSH; nie używaj jej do logowania ani przesyłania
poufnych danych. Certyfikat localhost jest self-signed, więc przeglądarka może
pokazać ostrzeżenie. Używaj wyłącznie kont testowych; nie wpisuj haseł
produkcyjnych ani danych płatniczych. Nie otwieraj portu PostgreSQL ani portów
Django w firewallu.

Każda usługa ma osobny checkout i `.venv` pod `/opt`, odrębne konto systemowe
bez logowania, katalog mediów pod `/var/lib` oraz własny plik środowiskowy.
Uruchomiony proces development nie może czytać sekretów preprod ani produkcji.
Dev i preprod kończą TLS bezpośrednio w Gunicornie i są dostępne tylko przez
tunel SSH; ich jednostki systemd wyłączają przekierowanie HTTPS Django, które
oczekuje nagłówka od reverse proxy. Ciasteczka pozostają secure przy `DEBUG=False`.

## Praca na branchach i promocja wydań

### Zasada PR i merge

Każda zmiana trafia do `dev` lub `main` wyłącznie przez pull request. GitHub
wymaga pozytywnych kontroli CI i rozwiązania wszystkich wątków review; bezpośredni
push oraz force-push są zablokowane, także dla administratorów. Przed scaleniem
autor zleca dwa niezależne przeglądy subagentom AI i scala dopiero po ich
akceptacji oraz przejściu CI. Te przeglądy są procedurą zespołu, a nie approvals
rejestrowanymi ani egzekwowanymi przez GitHub.

1. Twórz branch `feature/...` z aktualnego `dev`, pracuj lokalnie i otwieraj PR
   do `dev`. Po dwóch niezależnych review AI i przejściu GitHub Actions (Django
   check, testy Django i testy E2E) scalaj przez squash merge. CI uruchamia się na
   GitHub-hosted runners, używa SQLite i nie wdraża aplikacji ani nie łączy się
   z bazami OVH.
2. Po scaleniu PR pobierz aktualny `dev` i wdrażaj jego pełny SHA wyłącznie do
   developmentu. Z katalogu repozytorium uruchom:
   ```powershell
   git fetch origin
   $sha = (git rev-parse origin/dev).Trim()
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment development -Commit $sha
   ```
   Skrypt przed połączeniem sprawdza, że commit należy do właściwej gałęzi i że
   wymagane checki Django oraz Playwright zakończyły się sukcesem.
3. Po testach akceptacyjnych otwieraj PR `dev` -> `main`. Po scaleniu wybierz
   pełny SHA z `main` i wdrażaj go najpierw na preprod:
   ```powershell
   git fetch origin
   $sha = (git rev-parse origin/main).Trim()
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment preprod -Commit $sha
   ```
4. Po akceptacji preprod wdrażaj **ten sam SHA** na produkcję:
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_ovh.ps1 -Environment production -Commit $sha
   ```
   Skrypt blokuje produkcję, jeśli ten sam SHA nie przeszedł wcześniej
   wdrożenia i testów health-check na preprod albo nie ma root-owned znacznika
   potwierdzającego zweryfikowaną kopię bazy i mediów poza VPS. `Bypass`
   dotyczy wyłącznie uruchomionego procesu PowerShell i nie zmienia trwałej
   polityki komputera ani użytkownika.

Jeśli `dev` i `main` się rozjadą, najpierw otwórz PR synchronizujący `main` do
`dev`, rozwiąż konflikty i poczekaj na wymagane CI. Do czasu jego scalenia nie
wdrażaj `dev`. Nie używaj force-push ani resetu branchy. Skrypt wdrożeniowy
korzysta z lokalnego SSH i GitHub CLI; klucz SSH nie jest przekazywany do
GitHub Actions.

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
- Wartości środowiskowe mają jawne nazwy baz i wymagane klucze dla preprod/prod;
  statyczne URL-e zaczynają się od `/static/`, by działały także na zagnieżdżonych
  ścieżkach produktów.

## Operacje i odzyskiwanie

Runbook VPS, usług, wdrożeń i obecnych ograniczeń odzyskiwania:
[docs/self-hosting-recovery.md](docs/self-hosting-recovery.md).

**Pozostałe ryzyko:** na VPS nie ma skonfigurowanej ani przetestowanej kopii
zapasowej poza serwerem. Nie przechowuj tam jedynej kopii zamówień ani danych
klientów; przed sprzedażą skonfiguruj niezależną kopię i przetestuj odtworzenie.

**Gotowość sprzedażowa:** ostatni odczyt produkcji wykazał wyłączony Stripe,
nie skonfigurowany SMTP, zero aktywnych produktów i zero produktów ze stanem
większym od zera. Odpowiedź strony HTTP 200 potwierdza tylko dostępność
aplikacji. Nie przyjmuj zamówień, dopóki nie skonfigurujesz płatności live i
webhooka Stripe, poczty transakcyjnej, rzeczywistego katalogu ze stanami oraz
zaszyfrowanych kopii bazy i mediów z przetestowanym odtworzeniem.
