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

Osobny projekt ogranicza skutki błędnego resetu/ujawnienia uprawnień; jego
produkcyjny root branch może korzystać z Neon PITR. Sama funkcja PITR wymaga
root brancha, nie osobnego projektu. Aktualnie Neon ma jeden projekt: `dev`
jest root branchem, a `preprod` i `prod` są jego child branchami. Neon nie
udostępnia instant restore/PITR dla child branchy, więc obecny `prod` nie ma
tej ochrony. Jeśli budżet nie pozwoli na osobny projekt, trzeba przebudować
topologię tak, by produkcja była root branchem; jeśli to nie jest możliwe,
nie zakładać PITR i polegać na niezależnych backupach oraz sprawdzanym
odtworzeniu.

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
- Dla każdego PR-a uruchamiać trzy niezależne review subagentów: poprawność
  zmian, testy/regresje oraz bezpieczeństwo/operacje. Dla zmian wysokiego
  ryzyka rozszerzyć zakres każdej oceny, zamiast pomijać którąś z perspektyw
  przy małych PR-ach.
- W review sprawdzany jest dokładny commit PR-a. Znaleziska muszą być
  rozstrzygnięte; samo „approve” bez sprawdzenia diffu nie wystarcza.
- Scalać PR dopiero po trzech pozytywnych review tego samego commita,
  rozstrzygnięciu wszystkich znalezisk, zielonych wymaganych checkach CI i
  spełnieniu ewentualnego wymagania zatwierdzenia GitHub.
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
  `End-to-end tests (Playwright)`, ale obecnie nie wymaga PR ani zatwierdzenia.
  Wymusić PR, zakaz bezpośredniego push/force-push i co najmniej jedno
  zatwierdzenie niezależnego reviewera, jeśli jest dostępny; review subagentów
  nie zastępuje wymogu GitHub.
- `dev` nie jest obecnie chroniony. Wymusić PR, zakaz bezpośredniego
  push/force-push i te same wymagane checki; do czasu skutecznej ochrony nie
  udostępniać pushowym jobom sekretów development.
- Przy pracy solo, jeśli niezależny człowiek-reviewer nie jest dostępny, jawnie
  zdecydować o liczbie wymaganych approvals albo utrzymać zaufanego
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
przy redeployu, restarcie albo uśpieniu usługi Free. Przed poleganiem na
obrazach produktów przechowywanych w aplikacyjnym `media/` przenieść je do
object storage (np. S3/R2). To zalecana opcja, bo nie jest związana z
lifecycle web service i pozwala skalować aplikację poziomo.

Persistent disk na płatnej instancji może być rozwiązaniem przejściowym, ale
Render nie pozwala wtedy na zero-downtime deploye ani skalowanie usługi do
wielu instancji. Wybrać go tylko wtedy, gdy akceptujemy krótką niedostępność
przy wdrożeniu i pojedynczą instancję; `MEDIA_ROOT` musi wskazywać ścieżkę
montowania dysku.

Źródła: [ograniczenia Render Free](https://render.com/docs/free) i
[ograniczenia persistent disks w Render](https://render.com/docs/disks).
Render wdraża domyślnie po pushu do podpiętego brancha:
[automatyczne deploye](https://render.com/docs/deploys).

Backup powinien być niezależny od aplikacji, szyfrowany i regularnie
odtwarzany testowo. Aktualny workflow odrzuca pustą lub błędnie wskazaną bazę,
co jest bezpieczne, ale nie dowodzi jeszcze, że istnieje użyteczny backup
aktywnej produkcji. Aktualny `prod` jest child branchem `dev`, więc nie ma Neon
PITR. Produkcyjny branch powinien być root branchem, jeśli chcemy polegać na
PITR; osobny projekt jest zalecany dla izolacji, ale nie jest wymagany przez
samą funkcję PITR.
Przy przejściowym układzie z produkcją jako child branchem nie zakładać PITR —
niezależny, testowany backup jest wtedy wymagany. Sprawdzić okno historii
konkretnego planu i regularnie testować odtworzenie co najmniej kwartalnie.
Dodać alerty dla błędów HTTP, niedostępności aplikacji, problemów z bazą i
nieudanych backupów.

Źródło: [Neon Instant Restore / PITR](https://neon.com/docs/postgres/backup-restore/branch-restore).

Wszystkie usługi i baza powinny być w tym samym regionie, najlepiej blisko
klientów i z uwzględnieniem wymogów danych UE. Przed zakupem sprawdzić
dostępność regionu i koszty planów Neon/Render. Bez konkretnego problemu nie
zmieniać hostingu na alternatywy takie jak Railway/Fly.io/serwer własny — każda
zmiana dokłada pracę operacyjną i ryzyko migracji.

## Kolejność prac

### P0 — bezpieczeństwo danych i uruchomienie środowisk

1. W Renderze wyłączyć auto-deploy produkcji do czasu potwierdzenia celu bazy
   i ścieżki migracji. Usługa jest spięta z `main`, a Render domyślnie deployuje
   po pushu; `render.yaml` uruchamia `migrate` w `buildCommand`. Do czasu
   ustawienia gate'u nie scalać ani nie wdrażać zmian, które mogą uruchomić
   niezweryfikowaną migrację produkcji.
2. Zabezpieczyć `dev` przed bezpośrednim pushem, zanim pushowe joby CI będą
   mogły używać sekretów development. Obecnie branch nie jest chroniony,
   a push uruchamia workflow w środowisku `development`; do czasu wdrożenia
   ochrony usunąć sekrety z tych jobów albo wyłączyć sekrety przy pushach na
   `dev`.
3. Wymusić dla `main` aktualizacje wyłącznie przez PR, bez bezpośrednich
   pushy/force-pushy i bez cichego obejścia reguł. Wymagać zielonych checków
   CI oraz co najmniej jednego niezależnego zatwierdzenia, jeśli dostępny jest
   reviewer. Do czasu potwierdzenia bazy nie scalać zmian, które mogą uruchomić
   niezweryfikowaną migrację.
4. W Renderze, bez kopiowania sekretu do czatu, potwierdzić host/nazwę bazy
   używaną przez usługę produkcyjną i zestawić je z Neon `prod`. Obecny raport
   wskazuje pustą bazę Neon `prod` i niepotwierdzony URL aktywnej usługi.
   Nie wykonywać migracji ani nie przełączać live na pustą bazę.
5. Po potwierdzeniu aktywnej bazy wykonać backup i próbę odtworzenia na
   izolowanym branchu. Zweryfikować nie tylko schemat i integralność backupu,
   ale też obecność i zgodność oczekiwanych danych biznesowych; obecny workflow
   sprawdza endpoint i istnienie tabel, nie ich zawartość. Przed zmianą
   planu/hostingu zachować również istniejące pliki mediów i zweryfikować ich
   kopię; nie polegać na backupie, który nie przeszedł testu odtworzenia.
6. Przygotować produkcyjny root branch albo jawnie zaakceptować zewnętrzny
   backup zamiast PITR w wariancie przejściowym. Przed cutover zatrzymać zapisy
   albo wykonać końcową synchronizację zmian, zweryfikować dane docelowe i
   dopiero potem przełączyć ruch produkcyjny. Nie przełączać live na pustą bazę
   ani na kopię, która nie zawiera wszystkich zapisów przyjętych przed cutover.
7. Przed przyjmowaniem prawdziwych zamówień zmienić produkcję z Render Free na
   odpowiedni płatny plan lub inny kwalifikujący się hosting. Najpierw jawnie
   wybrać i zatwierdzić koszt planu, a media skopiować i zweryfikować w object
   storage; dopiero potem wdrożyć zmianę konfiguracji i planu usługi. Do tego
   czasu nie synchronizować Blueprintu jako wdrożenia live. Jeśli produkcja
   już obsługuje klientów, potraktować to jako pilną poprawkę dostępności i
   trwałości danych.
8. Naprawić preprod na Renderze na podstawie logów i sprawdzić endpoint
   zdrowia, migracje, połączenie z właściwą bazą oraz syntetyczny katalog.

### P1 — spójny developer workflow

1. Skierować Render preprod na `dev`, a wdrożenie produkcji zrobić ręcznym
   gate'em z `main`.
2. Ograniczyć publikację portu PostgreSQL z Docker Compose do `127.0.0.1`
   (np. `127.0.0.1:5434:5432`), nie wszystkich interfejsów hosta.
3. Uruchamiać PR-owe testy PostgreSQL bez sekretów na usługowym PostgreSQL
   GitHub Actions zamiast polegać wyłącznie na SQLite.
4. Ujednolicić README i `.env.example`: przykład nie ustawia obecnie
   `DATABASE_URL_DEVELOPMENT`, więc hostowe Django używa SQLite, mimo że
   instrukcja sugeruje lokalny PostgreSQL z Docker Compose. README twierdzi też,
   że testy Django w CI używają Neon dev i osobnej bazy testowej, chociaż joby
   pull requestów używają SQLite; opisać osobno zachowanie PR i pushów albo
   zmienić konfigurację workflow.
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
  wyjaśnić tę niespójność. README opisuje również testy CI jako korzystające
  z Neon dev, mimo że testy PR działają na in-memory SQLite.
- Neon API sprawdzone 2026-09-30: jeden projekt z `dev` jako root oraz
  `preprod` i `prod` jako child branche `dev`; poświadczenia CI są ograniczone
  do środowiska development, a testy PR nie dostają tych sekretów. Child
  branch `prod` nie obsługuje PITR.
- `main` wymaga dwóch checków CI i egzekwuje ochronę również wobec
  administratorów, ale obecnie nie wymaga zatwierdzenia PR; `dev` nie jest
  chroniony. Push na `dev` uruchamia workflow CI w środowisku `development`,
  które udostępnia sekrety bazodanowe. Obie usługi Render w `render.yaml`
  wskazują `main`, a obie mają `plan: free`.
- Render domyślnie wdraża po pushu na podpięty branch; produkcyjny
  `buildCommand` uruchamia migracje. Auto-deploy produkcji trzeba zatrzymać
  do czasu potwierdzenia aktywnej bazy i kontrolowanej ścieżki migracji.
- Neon `prod` był pusty przy ostatniej weryfikacji. Workflow backupu sprawdza
  oczekiwany endpoint i istnienie tabel, ale nie potwierdza obecności danych
  biznesowych. Preprod Render zgłaszał błąd i nie można było sprawdzić logów
  bez dostępu do Render Dashboard/API.
- Klucze szyfrujące pozostają repozytoryjnymi sekretami do czasu migracji
  historycznych backupów; nie rotować ich bez planu zachowania odczytu starych
  artefaktów.

## Zasada komunikacji

Do Michała zawsze zwracam się po polsku. Nazwy komend, zmiennych, branchy,
statusów CI i fragmenty kodu pozostają w oryginalnej pisowni, jeśli tak jest
czytelniej.
