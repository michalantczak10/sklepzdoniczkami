# Plan architektury sklepu

Data przeglądu: 2026-09-30

Ten dokument jest punktem odniesienia dla decyzji o bazach danych,
środowiskach, branchach, review i wdrożeniach. Zmiany w planie powinny wynikać
z nowego wymagania lub zweryfikowanych danych, a nie z chwilowej awarii
pojedynczego dostawcy.

## Rekomendacja w skrócie

- Zachować Django jako modularny monolit i PostgreSQL jako jedyną bazę danych.
- Nie dodawać MongoDB. Sklep, zamówienia, użytkownicy i płatności są danymi
  relacyjnymi; PostgreSQL obsługuje również pola JSON, jeśli pojawi się
  rzeczywista potrzeba.
- Utrzymywać trzy zdalne środowiska: development, preprod i production.
  Produkcja powinna docelowo być w osobnym projekcie Neon niż dev/preprod.
- Używać lokalnego PostgreSQL uruchamianego przez Docker Compose. Docker jest
  opcjonalny dla samej aplikacji, ale daje zgodność lokalnej bazy z produkcją.
- Pracować na krótkich branchach `feature/*`, robić PR-y i promować sprawdzony
  kod z `dev` do `main`. Nie scalać zmian bez zielonego CI.
- Używać agentów do niezależnego review, ale nie traktować ich głosów jako
  samodzielnej zgody na automatyczny merge.
- Na razie pozostać przy Renderze i Neon; najpierw naprawić i zweryfikować
  istniejącą konfigurację. Migracja dostawcy nie rozwiąże błędnego URL-a,
  pustej bazy ani brakujących sekretów.

## Docelowe bazy i dane

- **Lokalna praca:** Docker Compose + lokalny PostgreSQL. Osobna baza i wolumen
  na komputerze; wyłącznie dane testowe.
- **Development:** Neon `dev`, wspólna baza integracyjna; bez prawdziwych
  zamówień i danych klientów.
- **Preprod:** Neon `preprod`, osobna baza/branch; wyłącznie dane syntetyczne
  i klucze Stripe test.
- **Production:** Neon `prod`; tylko aplikacja produkcyjna zapisuje
  zamówienia, z ograniczonymi rolami i kopiami zapasowymi.
- **Testy CI:** tymczasowa baza PostgreSQL na run, z unikalną nazwą i
  sprzątaniem po teście; nigdy produkcja.

Docelowo zalecam dwa projekty Neon:

- `nonprod`: root branch `dev` oraz `preprod` jako child branch, z danymi
  syntetycznymi.
- `prod`: osobny root branch dla produkcji, z bazą `sklepzdoniczkami_prod`.

Osobny projekt ogranicza skutki błędnego resetu/ujawnienia uprawnień i pozwala
utrzymać produkcję jako root branch z dostępem do Neon PITR. Aktualnie Neon ma
jeden projekt: `dev` jest root branchem, a `preprod` i `prod` są jego child
branchami. Neon nie udostępnia instant restore/PITR dla child branchy, więc
obecny `prod` nie ma tej ochrony. Jeśli budżet nie pozwoli na osobny projekt,
nie zakładać PITR dla `prod`; trzeba wtedy polegać na niezależnych backupach
i regularnie sprawdzanym odtworzeniu. To wariant przejściowy o słabszej izolacji.

Nie należy tworzyć kolejnej trwałej bazy tylko na potrzeby każdego testu:
CI ma używać izolowanej, tymczasowej bazy i ją usuwać. Dane produkcyjne nie
powinny być kopiowane do preprod. Próby odtwarzania backupu wykonuj na
krótkotrwałym, odizolowanym branchu testowym, a następnie go usuń.

### PostgreSQL, Docker i MongoDB

Docker nie jest wymagany do połączenia z Neon ani do uruchomienia Django.
Zalecam jednak lokalny PostgreSQL z `docker compose up -d db`, bo odpowiada
bazie produkcyjnej lepiej niż SQLite. SQLite może pozostać lekkim trybem dla
wybranych testów jednostkowych, ale nie powinien być jedynym silnikiem w CI.
PR-y powinny testować się na efemerycznym PostgreSQL bez sekretów Neon.
Port lokalnej bazy w Compose powinien być wystawiony tylko na `127.0.0.1`,
nie na wszystkie interfejsy komputera.

MongoDB nie dodajemy bez konkretnego use case'u i uzasadnionych pomiarami
potrzeb. Drugi silnik bazy oznacza dodatkowe backupy, uprawnienia, migracje
i ryzyko niespójności; obecny model sklepu nie wskazuje na taką potrzebę.
Redis, kolejkę zadań lub mikroserwisy rozważymy dopiero wtedy, gdy pojawi się
konkretne obciążenie lub niezależny proces (np. długie zadania e-mailowe).

## Branchowanie i przepływ zmian

1. Chronione, długowieczne branche: `dev` dla integracji i `main` dla wydań.
2. Każda zmiana powstaje na krótkim branchu, np. `feature/nazwa`,
   `fix/nazwa` albo `docs/nazwa`.
3. PR z brancha roboczego trafia do `dev`; po zielonym CI i review jest
   wdrażany na preprod.
4. Po sprawdzeniu preprod tworzony jest PR `dev` → `main`. Wdrożenie produkcji
   powinno być osobnym, świadomym krokiem, najlepiej ręcznym zatwierdzeniem.
5. Hotfix zaczyna się od `main`; po wydaniu należy przenieść go z powrotem do
   `dev`.

Nie commitować bezpośrednio do `main` ani `dev`, nie force-pushować tych
branchy i nie utrzymywać długo branchy funkcjonalnych. Feature PR-y można
scalać squash; PR promujący `dev` do `main` powinien zachować czytelną relację
między historią integracji i wydania.

## PR-y, review i automatyczne scalanie

- Każda zmiana kodu idzie przez PR z krótkim opisem celu, ryzyka i testów.
- Dla zwykłych zmian: dwa niezależne review subagentów (np. poprawność oraz
  bezpieczeństwo/operacje). Dla zmian auth, płatności, danych, migracji,
  sekretów, CI/CD lub infrastruktury: trzy.
- W review sprawdzany jest dokładny commit PR-a. Znaleziska muszą być
  rozstrzygnięte; samo „approve” bez sprawdzenia diffu nie wystarcza.
- Agenci są doradcami, nie niezależnymi właścicielami systemu ani
  wiarygodnym statusem GitHub. Mogą przeoczyć błąd albo zgłosić fałszywy alarm.
  Ostateczna decyzja pozostaje po stronie właściciela projektu.
- Na tym etapie nie włączać merge'u automatycznego opartego wyłącznie na
  głosach agentów. Najpierw wymagane checki CI; po nich ręczna decyzja.
  Później można rozważyć GitHub Auto-merge dla niskiego ryzyka, jeśli warunki
  review są egzekwowane jako rzeczywiste statusy GitHub.
- Nie robić auto-merge zmian produkcyjnej bazy, migracji, płatności, auth,
  sekretów ani wdrożeń. Dla krytycznych zmian wymagać osobnego ręcznego
  przeglądu wdrożenia.

### Ustawienia GitHub do doprowadzenia do celu

- `main` ma już wymagane checki `Django tests` i
  `End-to-end tests (Playwright)` oraz jednego zatwierdzenia PR.
- `dev` nie jest obecnie chroniony. Dodać do niego te same wymagane checki,
  zakaz bezpośredniego push/force-push i wymaganie PR.
- Zachować wymagane zatwierdzenie na `main`, jeśli dostępny jest niezależny
  człowiek-reviewer. Przy pracy solo, jeśli nie da się go uzyskać, jawnie
  zdecydować o zmianie liczby wymaganych approvals albo utrzymać zaufanego
  zewnętrznego reviewera; nie obchodzić reguły po cichu. Subagenci nie spełniają
  wymagania GitHub approval i nie zastępują zatwierdzenia innej osoby.
- Zachować ograniczenia środowisk GitHub: sekrety deweloperskie dostępne
  tylko na `main`/`dev`; workflow PR nie otrzymuje ich. Sekret produkcyjny
  dostępny wyłącznie w chronionym środowisku produkcyjnym.

## CI, migracje i deploye

Obecny projekt ma jeden workflow CI z testami Django i Playwright; są to
oddzielne joby jednego pipeline'u, nie dwa konkurencyjne CI. Backup jest osobnym
workflowem operacyjnym i powinien nim pozostać.

Obecnie testy PR wybierają `config.settings_test`, czyli in-memory SQLite.
Kod zamówień i stanów magazynowych korzysta z `select_for_update()` w
transakcjach; zielone testy SQLite nie weryfikują semantyki blokad PostgreSQL.
To uzasadnia usługową bazę PostgreSQL w CI PR, bez sekretów Neon.

Docelowo:

- PR: lint/check Django, testy i E2E na efemerycznym PostgreSQL w GitHub Actions;
  bez dostępu do sekretów Neon, Render ani Stripe.
- Push na `dev`/`main`: integracyjne kontrole Neon na dedykowanej bazie
  testowej z unikalną nazwą i gwarantowanym sprzątaniem. Testy nie zapisują
  danych do współdzielonych tabel aplikacji.
- Preprod wdrażany z `dev`; production z `main` po ręcznej akceptacji wydania.
- Wybrać jedną kontrolowaną ścieżkę migracji. Obecnie `render.yaml` uruchamia
  `migrate` w `buildCommand`; nie dublować tego osobnym jobem CI. Docelowo
  migracje uruchamia osobny job przed wdrożeniem, z ograniczoną rolą migrate;
  web role nie ma uprawnień DDL. Produkcyjne migracje wymagają jawnego gate'u.
- Dodawać testy migracji i plan rollbacku dla zmian schematu; migracje muszą
  być kompatybilne z wersją aplikacji działającą równolegle podczas deployu.

## Hosting, pliki i operacje

Na razie pozostać przy Renderze — jest już skonfigurowany dla Django — i Neon.
Nie przenosić sklepu do innego dostawcy, zanim nie zostanie ustalona przyczyna
problemu preprod i potwierdzony produkcyjny URL. `render.yaml` wskazuje obecnie
branch `main` zarówno dla produkcji, jak i preprod; należy zmienić preprod na
`dev`, a produkcji nie wdrażać automatycznie przy każdym pushu do `main`.

**Warunek wejścia w realną produkcję:** obecny Render `free` nie jest
akceptowalny dla sklepu przyjmującego prawdziwe zamówienia. Render wprost
odradza plan Free do produkcji; usypia usługę po bezczynności, a jej wznowienie
może trwać około minuty. Przed uruchomieniem lub dalszą obsługą realnych
zamówień należy przenieść usługę produkcyjną na płatny plan Render albo
wybrać inny hosting o wymaganej dostępności. Obecny `render.yaml` nadal
deklaruje `plan: free` dla produkcji; przed synchronizacją Blueprintu dla live
trzeba jawnie zmienić plan usługi na wybrany płatny wariant. Nie ustawiam
konkretnego płatnego planu w tym dokumencie ani nie zmieniam go automatycznie,
bo wymaga to decyzji budżetowej. Sam płatny workspace nie zmienia planu
instancji — trzeba zmienić plan usługi.

Filesystem usług Render jest efemeryczny; pliki z `MEDIA_ROOT` mogą zniknąć
przy redeployu, restarcie albo uśpieniu usługi Free. Przed przyjmowaniem
uploadów i realnych zamówień przenieść media do object storage (np. S3/R2).
To zalecana opcja, bo nie jest związana z lifecycle web service i pozwala
skalować aplikację poziomo.

Persistent disk na płatnej instancji może być rozwiązaniem przejściowym, ale
Render nie pozwala wtedy na zero-downtime deploye ani skalowanie usługi do
wielu instancji. Wybrać go tylko wtedy, gdy akceptujemy krótką niedostępność
przy wdrożeniu i pojedynczą instancję; `MEDIA_ROOT` musi wskazywać ścieżkę
montowania dysku.

Źródła: [ograniczenia Render Free](https://render.com/docs/free) i
[ograniczenia persistent disks w Render](https://render.com/docs/disks).

Backup powinien być niezależny od aplikacji, szyfrowany i regularnie
odtwarzany testowo. Aktualny workflow odrzuca pustą lub błędnie wskazaną bazę,
co jest bezpieczne, ale nie dowodzi jeszcze, że istnieje użyteczny backup
aktywnej produkcji. Aktualny `prod` jest child branchem `dev`, więc nie ma
Neon PITR. Produkcyjny branch powinien być root branchem w osobnym projekcie,
jeśli chcemy polegać na PITR. Przy przejściowym układzie z produkcją jako child
branchem nie zakładać PITR — niezależny, testowany backup jest wtedy wymagany.
W obu przypadkach sprawdzić okno historii konkretnego planu i regularnie
testować odtworzenie co najmniej kwartalnie. Dodać alerty dla błędów HTTP,
niedostępności aplikacji, problemów z bazą i nieudanych backupów.

Źródło: [Neon Instant Restore / PITR](https://neon.com/docs/postgres/backup-restore/branch-restore).

Wszystkie usługi i baza powinny być w tym samym regionie, najlepiej blisko
klientów i z uwzględnieniem wymogów danych UE. Przed zakupem sprawdzić
dostępność regionu i koszty planów Neon/Render. Bez konkretnego problemu nie
zmieniać hostingu na alternatywy takie jak Railway/Fly.io/serwer własny — każda
zmiana dokłada pracę operacyjną i ryzyko migracji.

## Kolejność prac

### P0 — bezpieczeństwo danych i uruchomienie środowisk

1. W Renderze, bez kopiowania sekretu do czatu, potwierdzić host/nazwę bazy
   używaną przez usługę produkcyjną i zestawić je z Neon `prod`. Obecny raport
   wskazuje pustą bazę Neon `prod` i niepotwierdzony URL aktywnej usługi.
   Nie wykonywać migracji ani nie przełączać live na pustą bazę.
2. Po potwierdzeniu aktywnej bazy wykonać backup i próbę odtworzenia na
   izolowanym branchu. Przed zmianą planu/hostingu zachować również istniejące
   pliki mediów i zweryfikować ich kopię; nie polegać na backupie, który nie
   przeszedł testu odtworzenia.
3. Przygotować osobny projekt Neon z produkcyjnym root branchem albo jawnie
   zaakceptować zewnętrzny backup zamiast PITR w wariancie przejściowym.
   Przenosić dane produkcyjne dopiero po zweryfikowanym backupie i planie
   cutover; nie przełączać live na pustą bazę.
4. Przed przyjmowaniem prawdziwych zamówień zmienić produkcję z Render Free na
   odpowiedni płatny plan lub inny kwalifikujący się hosting. Najpierw jawnie
   wybrać i zatwierdzić koszt planu, a media skopiować i zweryfikować w object
   storage; dopiero potem wdrożyć zmianę konfiguracji i planu usługi. Do tego
   czasu nie synchronizować Blueprintu jako wdrożenia live. Jeśli produkcja
   już obsługuje klientów, potraktować to jako pilną poprawkę dostępności i
   trwałości danych.
5. Naprawić preprod na Renderze na podstawie logów i sprawdzić endpoint
   zdrowia, migracje, połączenie z właściwą bazą oraz syntetyczny katalog.

### P1 — spójny developer workflow

1. Skierować Render preprod na `dev`, a wdrożenie produkcji zrobić ręcznym
   gate'em z `main`.
2. Ochronić `dev` i `main` wymaganymi statusami i zasadami PR opisanymi wyżej.
3. Uruchamiać PR-owe testy PostgreSQL bez sekretów na usługowym PostgreSQL
   GitHub Actions zamiast polegać wyłącznie na SQLite.
4. Ujednolicić README i `.env.example`: przykład nie ustawia obecnie
   `DATABASE_URL_DEVELOPMENT`, więc hostowe Django używa SQLite, mimo że
   instrukcja sugeruje lokalny PostgreSQL z Docker Compose.
5. Uzgodnić jedną kontrolowaną ścieżkę migracji.

### P2 — izolacja produkcji i odporność

1. Dopasować historię Neon i retencję zewnętrznych backupów do uzgodnionych
   celów RPO/RTO oraz budżetu.
2. Ustalić monitoring, alerty i właściciela reakcji na
   incydent.
3. Automatyzować merge tylko dla bezpiecznych, niskiego ryzyka zmian po
   zbudowaniu wiarygodnych statusów review; zachować ręczne zatwierdzenie
   produkcyjnego wdrożenia.

## Stan ustalony przy przeglądzie

- Aplikacja jest Django z jednym głównym modułem sklepu i PostgreSQL; nie ma
  uzasadnienia dla MongoDB ani mikroserwisów.
- Repo ma Compose dla lokalnego PostgreSQL oraz ustawienia SQLite używane m.in.
  w testach PR.
- `.env.example` pozostawia `DATABASE_URL_DEVELOPMENT` nieustawione i wskazuje
  SQLite, a README opisuje go jako plik z lokalnym URL-em PostgreSQL; należy
  wyjaśnić tę niespójność.
- Neon ma jeden projekt z `dev` jako root oraz `preprod` i `prod` jako child
  branche `dev`; poświadczenia CI są ograniczone do środowiska development,
  a testy PR nie dostają tych sekretów. Child branch `prod` nie obsługuje PITR.
- `main` wymaga dwóch checków CI i jednego zatwierdzenia PR; `dev` nie jest
  chroniony. Obie usługi Render w `render.yaml` wskazują `main`, a obie mają
  `plan: free`.
- Neon `prod` był pusty przy ostatniej weryfikacji, więc workflow backupu
  celowo odmawia utworzenia artefaktu, dopóki poprawny, zmigrowany cel nie
  zostanie potwierdzony. Preprod Render zgłaszał błąd i nie można było sprawdzić
  logów bez dostępu do Render Dashboard/API.
- Klucze szyfrujące pozostają repozytoryjnymi sekretami do czasu migracji
  historycznych backupów; nie rotować ich bez planu zachowania odczytu starych
  artefaktów.

## Zasada komunikacji

Do Michała zawsze zwracam się po polsku. Nazwy komend, zmiennych, branchy,
statusów CI i fragmenty kodu pozostają w oryginalnej pisowni, jeśli tak jest
czytelniej.
