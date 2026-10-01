# Plan architektury sklepu

Data przeglądu: 2026-10-01

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

### Ustawienia GitHub i ograniczenia

- `main` i `dev` wymagają PR-ów oraz checków `Django tests` i
  `End-to-end tests (Playwright)`; bezpośrednie pushowanie, force-push i
  usuwanie tych branchy są zablokowane. Liczba wymaganych zatwierdzeń GitHub
  wynosi obecnie 0, zgodnie z solo trybem pracy.
- Trzy niezależne review subagentów są wymagane jako proces przed scaleniem,
  ale nie są egzekwowane przez GitHub jako status check. Jeśli pojawi się
  niezależny człowiek-reviewer, ponownie rozważyć wymaganie co najmniej jednego
  zatwierdzenia GitHub.
- Przy pracy solo, jeśli niezależny człowiek-reviewer nie jest dostępny, jawnie
  uzgodnić tę różnicę; subagenci nie spełniają wymagania GitHub approval i nie
  zastępują zatwierdzenia innej osoby.
- Zachować ograniczenia środowisk GitHub: workflow PR używa środowiska `ci-pr`
  bez sekretów Neon; pushowe joby korzystają z sekretów chronionych środowisk
  `development` i `preprod`.

## CI, migracje i deploye

Obecny projekt ma jeden workflow CI z testami Django i Playwright; są to
oddzielne joby jednego pipeline'u, nie dwa konkurencyjne CI. Backup jest osobnym
workflowem operacyjnym i powinien nim pozostać.

Testy PR wybierają `config.settings_test`, czyli SQLite, bez sekretów Neon.
Pushowe joby używają tymczasowej bazy testowej w Neon i sprzątają ją po runie.
Kod zamówień i stanów magazynowych korzysta z `select_for_update()` w
transakcjach; zielone testy SQLite nie weryfikują semantyki blokad PostgreSQL.
To uzasadnia usługową bazę PostgreSQL w CI PR, bez sekretów Neon.

Docelowo:

- PR: lint/check Django, testy i E2E na efemerycznym PostgreSQL w GitHub Actions;
  bez dostępu do sekretów Neon, Render ani Stripe.
- Push na `dev`/`main`: integracyjne kontrole Neon na dedykowanej bazie
  testowej z unikalną nazwą i gwarantowanym sprzątaniem. Testy nie zapisują
  danych do współdzielonych tabel aplikacji.
- Preprod wdrażany z `dev` po zielonych checkach; production z `main` dopiero
  po ręcznej akceptacji wydania.
- Preprod migracje wykonuje osobny job GitHub Actions przed deployem, używając
  ograniczonej roli migrate; Render używa roli runtime i nie wykonuje DDL.
  Build production w `render.yaml` nie wykonuje migracji. Workflow
  `production-migrations.yml` udostępnia ręczną ścieżkę wyłącznie z `main`,
  z jawnym potwierdzeniem, przypiętym hostem Neon, walidacją bazy i historią
  migracji (albo jawnie wybranym pustym bootstrapem) oraz zaszyfrowaną kopią
  przed DDL. Wymaga skonfigurowania
  `DATABASE_URL_PRODUCTION_MIGRATE`, `PRODUCTION_DATABASE_HOST` i
  sekretów szyfrujących. Limited role URLs są zapisane w GitHub Environment
  `production`; workflow dodatkowo odrzuca role z nadmiernymi uprawnieniami.
  Dla istniejącej bazy wymaga, by migrator był właścicielem publicznych
  obiektów oraz oddzielnie zweryfikowanego odtworzenia backupu. Pusty bootstrap
  wymaga braku obiektów publicznych i jawnego potwierdzenia, że legacy SQLite
  jest celowo odrzucane. Ścieżka pustego bootstrapu została wykonana 2026-10-01
  w [runie 36860541866](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36860541866).
  Przed kolejnymi zmianami produkcyjnymi nadal wymagane są zaszyfrowane backupy
  i okresowe próby odtworzenia; nie używać pustego bootstrapu do istniejącej
  bazy ani gdy stare dane mają zostać zachowane.
- Dodawać testy migracji i plan rollbacku dla zmian schematu; migracje muszą
  być kompatybilne z wersją aplikacji działającą równolegle podczas deployu.

## Hosting, pliki i operacje

Na razie pozostać przy Renderze i Neon. Live preprod jest skierowany na branch
`dev`, korzysta z ograniczonej roli runtime i przeszedł sprawdzenie HTTP oraz
syntetycznego katalogu. Produkcja wskazuje `main`, ma wyłączony auto-deploy i
od 2026-10-01 korzysta z Neon `prod` przez ograniczoną rolę runtime. Wdrożony
commit `735d256b034e98410e7555c7ab1f76d35e0cafbf` odpowiada HTTP 200 na domenie
Render, domenie sklepu i stronie logowania administratora.

**Pozostałe warunki stabilnej produkcji:** baza PostgreSQL Neon jest już
skonfigurowana, a fallback do SQLite został usunięty z bieżącej konfiguracji
Rendera. Usługa nadal działa jednak na planie `free`, który usypia aplikację po
bezczynności, a jej wznowienie może trwać około minuty. Plan Free nie jest
zalecany do sklepu przyjmującego prawdziwe zamówienia. `render.yaml` nadal
deklaruje `plan: free`; przed synchronizacją Blueprintu dla live trzeba wybrać
i ustawić płatny plan albo inny hosting. Nie zmieniam planu automatycznie,
ponieważ wymaga to decyzji budżetowej.

Filesystem usług Render jest efemeryczny; pliki z `MEDIA_ROOT` mogą zniknąć
przy redeployu, restarcie albo uśpieniu usługi Free. Przed dodaniem
produkcyjnych zdjęć przenieść media do object storage (np. S3/R2), niezależnego
od lifecycle web service.

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
odtwarzany testowo. Zaszyfrowany backup przed migracją i ręczny backup po
migracji zakończyły się powodzeniem 2026-10-01; artefakty są przechowywane w
GitHub Actions. Sam udany backup nie zastępuje próby odtworzenia. Aktualny
`prod` jest child branchem `dev`, więc nie ma Neon PITR. Produkcyjny branch
powinien być root branchem, jeśli chcemy polegać na PITR; osobny projekt jest
zalecany dla izolacji, ale nie jest wymagany przez samą funkcję PITR.
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

1. **Ukończone 2026-10-01:** produkcyjny `buildCommand` nie uruchamia migracji,
   a auto-deploy pozostaje wyłączony. Produkcyjny workflow migracyjny uruchomiono
   ręcznie na pustej bazie Neon po jawnej zgodzie właściciela na odrzucenie
   starych zamówień. Walidacja potwierdziła host, ograniczoną rolę i pusty
   schemat; przed DDL zapisano zaszyfrowany backup.
2. **Ukończone:** chronić `dev` przed bezpośrednim pushem. Pull requesty nie
   otrzymują sekretów Neon; pushowe joby uruchamiają się w chronionym
   środowisku.
3. **Ukończone z ograniczeniem:** `main` i `dev` wymagają PR-ów i zielonych
   checków oraz blokują force-push/usuwanie. GitHub nie wymaga zatwierdzeń
   (0 approvals); trzy pozytywne review subagentów są procesem, a nie
   egzekwowanym statusem GitHub.
4. **Ukończone 2026-10-01:** właściciel zaakceptował start bez historycznych
   zamówień. Render ma jawne `APP_ENV=production`, `DATABASE_URL_PRODUCTION`
   wskazujący `sklepzdoniczkami_prod` oraz ograniczoną rolę
   `sklepzdoniczkami_prod_web_limited`. Ustawiono też sufiksowane klucze Stripe,
   usunięto stare niesufiksowane zmienne i wdrożono commit
   `735d256b034e98410e7555c7ab1f76d35e0cafbf`. Sprawdzono HTTP 200 na obu
   domenach i stronie logowania administratora.
5. **Częściowo ukończone:** zaszyfrowany backup przed migracją oraz ręczny
   backup po migracji zakończyły się powodzeniem. Pozostaje regularnie
   odtwarzać kopie na izolowanym branchu i weryfikować dane oraz media.
6. **Oczekuje:** zdecydować, czy przenieść `prod` z child brancha na root
   branch, aby uzyskać Neon PITR, czy zaakceptować ochronę wyłącznie przez
   niezależne backupy. Historyczne zamówienia SQLite nie były przenoszone,
   zgodnie z decyzją właściciela.
7. **Decyzja budżetowa i operacyjna:** Render production nadal ma plan Free,
   a media nie mają trwałego object storage. Przed regularnym przyjmowaniem
   prawdziwych zamówień wybrać płatny plan/hosting, przenieść zdjęcia do
   object storage i przetestować odtworzenie backupu. Nie zmieniać planu
   automatycznie.
8. **Ukończone:** preprod wskazuje `dev`, ma oddzielny URL i nazwę bazy,
   runtime role bez DDL, a workflow CI na branchu `dev` wykonuje metadata
   rename i migracje rolą migrate przed deployem ([workflow](https://github.com/michalantczak10/sklepzdoniczkami/blob/dev/.github/workflows/ci.yml),
   [udany run](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36842344038)).
   Render wdrożył commit `65522f2`; sprawdzono HTTP 200.

### P1 — spójny developer workflow

1. **Ukończone:** Render preprod wskazuje `dev`; production ma ręczny gate
   (`autoDeployTrigger: "off"`) z `main`.
2. **Ukończone:** ograniczyć publikację portu PostgreSQL z Docker Compose do `127.0.0.1`
   (np. `127.0.0.1:5434:5432`), nie wszystkich interfejsów hosta.
3. **Oczekuje:** uruchamiać PR-owe testy PostgreSQL bez sekretów na usługowym
   PostgreSQL GitHub Actions zamiast polegać wyłącznie na SQLite.
4. **Ukończone:** ujednolicić README i `.env.example` oraz rozróżnić testy PR
   na SQLite od pushowych testów Neon.
5. **Ukończone:** preprod i production mają osobne, kontrolowane ścieżki
   migracji. Produkcyjny workflow wymaga jawnej zgody na porzucenie danych przy
   pustym bootstrapie albo zweryfikowanego odtworzenia przy istniejącej bazie.

### P2 — izolacja produkcji i odporność

1. Dopasować historię Neon i retencję zewnętrznych backupów do uzgodnionych
   celów RPO/RTO oraz budżetu.
2. Ustalić monitoring, alerty i właściciela reakcji na
   incydent.
3. Automatyzować merge tylko dla bezpiecznych, niskiego ryzyka zmian po
   zbudowaniu wiarygodnych statusów review; zachować ręczne zatwierdzenie
   produkcyjnego wdrożenia.

## Stan ustalony przy przeglądzie

- Aplikacja jest Django z PostgreSQL; nie ma uzasadnienia dla MongoDB ani
  mikroserwisów. Lokalny Compose uruchamia tylko PostgreSQL, a PR CI używa
  SQLite.
- Stan Neon sprawdzony 2026-10-01: jeden projekt z `dev` jako root oraz
  `preprod` i `prod` jako child branche. Child `prod` nie obsługuje PITR;
  docelowa separacja projektu production pozostaje rekomendacją.
- `main` i `dev` wymagają PR-ów, dwóch checków CI, zakazują force-push i
  usuwania; wymagane approvals wynoszą 0. Pull requesty używają `ci-pr` bez
  sekretów Neon. Push na `dev` wykonuje testy Neon; job migracyjny preprod jest
  w [workflow branchu `dev`](https://github.com/michalantczak10/sklepzdoniczkami/blob/dev/.github/workflows/ci.yml)
  i zakończył się powodzeniem w [runie wdrażanego commita](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36829814318).
- Render production wskazuje `main`, ma plan Free i `autoDeployTrigger: off`.
  Od 2026-10-01 ma poprawne sufiksowane zmienne production, używa Neon
  `sklepzdoniczkami_prod` przez ograniczoną rolę runtime i działa na commicie
  `735d256b034e98410e7555c7ab1f76d35e0cafbf`. Odpowiedzi HTTP 200 sprawdzono
  dla domeny Render, domeny sklepu i `/admin/login/`. Stare niesufiksowane
  zmienne zostały usunięte.
- Render preprod wskazuje `dev`, ma plan Free i `autoDeployTrigger: checksPass`.
  Używa bazy `sklepzdoniczkami_preprod` na znanym branchu `preprod`, z
  oddzielną rolą runtime; job migracyjny z `.github/workflows/ci.yml` na
  branchu `dev` używa sekretu wyłącznie z GitHub Environment `preprod`. Deploy
  i syntetyczny katalog zweryfikowano przez HTTP 200.
- Neon production został uruchomiony z pustego schematu w runie
  [36860541866](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36860541866).
  Stare zamówienia SQLite celowo pominięto. Zaszyfrowany backup przed migracją
  został zapisany jako artefakt Actions.
- Ograniczone role `_migrate_limited` i `_web_limited` pozostają aktywne:
  migrator ma DDL tylko w `public`, aplikacja nie ma CREATE, a default
  privileges dają DML i dostęp do sekwencji. Ich URL-e są w GitHub Environment
  `production`; starszych ról nie używać jako URL-i runtime/migracji.
- Ręczny backup po migracji zakończył się powodzeniem w runie
  [36862495568](https://github.com/michalantczak10/sklepzdoniczkami/actions/runs/36862495568).
  Odtworzenie kopii w izolowanym środowisku pozostaje do wykonania.
- Nowa baza nie zawiera aktywnego katalogu sprzedażowego ani użytkownika
  administratora. Przed uruchomieniem sprzedaży należy utworzyć konto admina
  i wprowadzić zweryfikowany katalog; nie używać produktów demonstracyjnych
  z migracji jako oferty produkcyjnej.
- Produkcja nadal jest na Render Free i nie ma trwałego storage mediów.
  Płatny plan i object storage wymagają decyzji budżetowej oraz migracji
  zweryfikowanych plików.
- Klucze szyfrujące pozostają repozytoryjnymi sekretami do czasu migracji
  historycznych backupów; nie rotować ich bez planu zachowania odczytu starych
  artefaktów.

## Zasada komunikacji

Do Michała zawsze zwracam się po polsku. Nazwy komend, zmiennych, branchy,
statusów CI i fragmenty kodu pozostają w oryginalnej pisowni, jeśli tak jest
czytelniej.
