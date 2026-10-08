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

## Praca na branchach i promocja wydań

### Zasada PR i merge

Każda zmiana trafia do `dev` lub `main` wyłącznie przez pull request. PR wymaga
dwóch zatwierdzeń od osób innych niż autor, pozytywnych wymaganych kontroli CI
oraz rozwiązania wszystkich wątków przeglądu. Nowy commit po zatwierdzeniu
unieważnia wcześniejsze review; po aktualizacji PR ponownie zbiera oba
zatwierdzenia. Nie omijaj zabezpieczeń także jako administrator, nie wypychaj
bezpośrednio do chronionych branchy i nie używaj force-pusha. Scalaj dopiero po
spełnieniu wszystkich warunków ochrony gałęzi.

1. Twórz branch `feature/...` z aktualnego `dev`, pracuj lokalnie i otwieraj PR
   do `dev`. Po dwóch review i przejściu GitHub Actions (Django check, testy
   Django i testy E2E) scalaj przez squash merge. CI uruchamia się na
   GitHub-hosted runners, używa SQLite i nie wdraża aplikacji ani nie łączy się
   z bazami OVH.
2. Wdrażaj `dev` wyłącznie do usługi development i bazy
   `sklepzdoniczkami_dev`. Testuj tam funkcjonalność oraz przykładowe dane.
3. Po akceptacji otwieraj PR `dev` -> `main`. Po scaleniu wybierz konkretny
   commit `main`, wdrażaj go najpierw do preprod z bazą
   `sklepzdoniczkami_preprod` i wykonaj testy akceptacyjne. Ten PR także wymaga
   dwóch review i przejścia wymaganych kontroli.
4. Po akceptacji preprod wdrażaj **ten sam commit** na produkcję. Nie wdrażaj
   produkcji bez sprawdzenia migracji i aktualnej, przetestowanej kopii bazy.
   Wdrożenia są ręczne; GitHub Actions nie ma sekretów SSH i nie uruchamia
   deploymentu.

**Blokada przed następnym wdrożeniem:** zdalny branch `dev` jest stary i
rozjechał się z `main`. Ostatni `dev` (`65522f2`) nadal zawiera konfigurację
Render/Neon, a `main` (`da455da`) ma względem niego 54 commity do przodu i 21
commitów, których nie ma w `main`. Nie wdrażaj obecnego `dev` na OVH. Najpierw
przygotuj PR synchronizujący `main` do `dev`, usuń z niego pozostałą starą
konfigurację i sprawdź całą historię/konflikty; dopiero potem wróć do opisanej
promocji branchy. Nie rozwiązuj tego przez force-push ani reset `dev`.

Do czasu tej synchronizacji niezależne checkouts development i preprod na VPS
są przypięte do bezpiecznego commitu `main` `da455da`; produkcja działa na
`adc66a9`. Usługi są od siebie odizolowane, ale `dev` nie jest jeszcze
wdrażany z gałęzi o tej samej nazwie. Nie traktuj tego stanu jako ukończonego
przepływu promocji.

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
