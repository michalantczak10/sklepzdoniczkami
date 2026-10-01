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
  Nie był uruchamiany; nie wykonywać migracji ani
  deployu production przed potwierdzeniem źródła danych i odtworzenia backupu.
- Dodawać testy migracji i plan rollbacku dla zmian schematu; migracje muszą
  być kompatybilne z wersją aplikacji działającą równolegle podczas deployu.

## Hosting, pliki i operacje

Na razie pozostać przy Renderze i Neon. Live preprod jest teraz skierowany na
branch `dev`, korzysta z ograniczonej roli runtime i przeszedł sprawdzenie
HTTP oraz syntetycznego katalogu. Produkcja nadal wskazuje `main`, ale jej
auto-deploy jest wyłączony zarówno w Renderze, jak i w aktualnym `render.yaml`
na branchu `main`.

**Warunek wejścia w realną produkcję:** obecny Render `free` nie jest
akceptowalny dla sklepu przyjmującego prawdziwe zamówienia. Render wprost
odradza plan Free do produkcji; usypia usługę po bezczynności, a jej wznowienie
może trwać około minuty. Przed uruchomieniem lub dalszą obsługą realnych
zamówień trzeba najpierw skonfigurować i zweryfikować trwałą bazę PostgreSQL,
backup i próbę odtworzenia. SQLite używane przy braku poprawnego URL-a jest
plikiem w efemerycznym filesystemie Render i nie zapewnia trwałości zamówień.
Następnie należy przenieść usługę produkcyjną na płatny plan Render albo
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

1. **Częściowo ukończone:** live ustawienie Rendera i `render.yaml` mają
   `autoDeployTrigger: "off"`, a manifest nie uruchamia produkcyjnych
   migracji podczas builda. Aktywnej komendy builda Render nie zmieniano.
   Ręczny workflow migracyjny istnieje, ale nie był uruchamiany.
2. **Ukończone:** chronić `dev` przed bezpośrednim pushem. Pull requesty nie
   otrzymują sekretów Neon; pushowe joby uruchamiają się w chronionym
   środowisku.
3. **Ukończone z ograniczeniem:** `main` i `dev` wymagają PR-ów i zielonych
   checków oraz blokują force-push/usuwanie. GitHub nie wymaga zatwierdzeń
   (0 approvals); trzy pozytywne review subagentów są procesem, a nie
   egzekwowanym statusem GitHub.
4. **Bloker production:** usługa Render ma starszą, niesufiksowaną zmienną
   `DATABASE_URL`, wskazującą bazę `sklepzdoniczkami` i rolę owner. Jej
   endpoint nie należy do projektu Neon widocznego przez aktualny klucz API.
   Brakuje `APP_ENV`, `DATABASE_URL_PRODUCTION` i
   `DJANGO_SECRET_KEY_PRODUCTION`; obecnie wdrożony kod wybiera
   `APP_ENV=development` i SQLite, bo nie ma `DATABASE_URL_DEVELOPMENT`.
   Kod po merge'u #46 odrzuca brak jawnego `APP_ENV` na Renderze, więc
   następny deploy zatrzyma się bezpiecznie, dopóki konfiguracja nie zostanie
   poprawiona. Produkcja nie została wdrożona ponownie.
   SQLite znajduje się na efemerycznym filesystemie Render, więc zapisy
   zamówień mogą zniknąć przy restarcie/redeployu. Jeśli sklep już przyjmuje
   prawdziwe zamówienia, potraktować to jako pilny incydent trwałości danych.
   Nie przepinać production na Neon `prod`, nie migrować i nie usuwać starej
   bazy, dopóki nie zostaną ustalone aktywne dane oraz ich kopia.
5. **Oczekuje:** po potwierdzeniu źródła production wykonać backup i próbę
   odtworzenia na izolowanym branchu. Zweryfikować dane biznesowe oraz kopię
   mediów; obecny workflow backupu sprawdza endpoint i schemat, ale nie
   potwierdza zawartości produkcyjnej.
6. **Oczekuje:** przygotować produkcyjny root branch lub jawnie zaakceptować
   niezależny backup zamiast PITR. Cutover wykonać dopiero po końcowej
   synchronizacji zapisów i weryfikacji danych docelowych.
7. **Decyzja budżetowa i blocker danych:** production pozostaje na Render Free,
   z niezweryfikowanym URL-em i SQLite fallbackiem oraz bez trwałego storage
   mediów. Przed przyjmowaniem prawdziwych zamówień skonfigurować trwałą bazę
   PostgreSQL i potwierdzić backup/restore; następnie wybrać płatny plan lub
   hosting oraz object storage, przenieść media i zweryfikować migrację. Nie
   zmieniać planu ani źródła danych automatycznie. Jeśli sklep już obsługuje
   klientów, potraktować to jako pilny incydent dostępności i trwałości danych.
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
5. **Częściowo ukończone:** preprod ma jedną kontrolowaną ścieżkę migracji;
   wdrożyć analogiczny, ręcznie zatwierdzany job migracyjny dla production
   dopiero po potwierdzeniu jej właściwej bazy.

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
  Jego niesufiksowany `DATABASE_URL` wskazuje bazę `sklepzdoniczkami` i rolę
  owner, a endpoint nie należy do widocznego projektu Neon. Brak
  `APP_ENV`/zmiennych sufiksowanych oznacza, że aktualnie wdrożony kod wybiera
  development/SQLite z pliku na efemerycznym filesystemie Render. Kod na
  `main` po merge'u #46 nie pozwala już na taki fallback przy kolejnym
  uruchomieniu na Renderze; auto-deploy pozostaje wyłączony i produkcji nie
  wdrażano. Zapisy mogą nie przetrwać restartu/redeployu; nie potwierdzono,
  czy stary endpoint zawiera dane biznesowe i nie wykonywano tam migracji
  ani cutoveru.
- Render preprod wskazuje `dev`, ma plan Free i `autoDeployTrigger: checksPass`.
  Używa bazy `sklepzdoniczkami_preprod` na znanym branchu `preprod`, z
  oddzielną rolą runtime; job migracyjny z `.github/workflows/ci.yml` na
  branchu `dev` używa sekretu wyłącznie z GitHub Environment `preprod`. Deploy
  i syntetyczny katalog zweryfikowano przez HTTP 200.
- Workflow backupu nadal nie dowodzi istnienia użytecznych kopii danych
  produkcyjnych; targetowany `sklepzdoniczkami_prod` zgłaszał brak
  `django_migrations`, a branch `prod` był pusty przy ostatniej weryfikacji.
  Nie zmieniać ani nie usuwać baz, dopóki źródło danych produkcyjnych i
  możliwość odtworzenia nie zostaną potwierdzone.
- Read-only probe potwierdził, że produkcyjny endpoint Neon i baza
  `sklepzdoniczkami_prod` są dostępne, ale baza nie ma jeszcze tabel publicznych.
  Utworzono ograniczone role `_migrate_limited` i `_web_limited`: migrator ma
  DDL tylko w `public`, aplikacja nie ma CREATE, a domyślne uprawnienia dają jej
  DML i dostęp do sekwencji. Ich connection stringi są sekretami
  `DATABASE_URL_PRODUCTION_MIGRATE` i `DATABASE_URL_PRODUCTION_WEB` w
  GitHub Environment `production`. Starsze role production pozostają
  niezmienione i nie należy ich używać jako URL-i runtime/migracji.
- Produkcyjny workflow migracyjny jest dostępny na `main`, ale nie był
  uruchamiany. Wymaga jawnego hosta Neon jako `PRODUCTION_DATABASE_HOST`,
  ograniczonej roli migracyjnej, sekretów backupu oraz potwierdzenia
  odtworzenia. Pustą
  bazę dopuszcza wyłącznie jako jawny bootstrap bez istniejących tabel;
  inne niejednoznaczne stany odrzuca.
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
