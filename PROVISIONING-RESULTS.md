# Bieżący stan Neon

Zweryfikowano: 2026-09-29

## Development

- Branch `dev` ma aktywny compute.
- Lokalny i CI URL aplikacji (`DATABASE_URL_DEVELOPMENT`) używa roli
  `sklepzdoniczkami_dev_web` z prawami DML do schemy `public`; rola nie może
  tworzyć tabel ani baz.
- Testy Django i E2E używają odrębnej roli `sklepzdoniczkami_dev_test`
  z `CREATEDB`, bez `CREATEROLE` i superusera. Każdy run dostaje własną
  testową bazę, usuwaną również po błędzie.
- CI w PR #40 przeszło: testy Django na Neon PostgreSQL, kontrola migracji
  oraz Playwright E2E.

## Preprod

- Utworzono gałąź Neon `preprod` (`br-withered-forest-b51x3ley`) z gałęzi `dev`
  i aktywny endpoint read/write. Usunięto z niej sklonowaną bazę dev, aby
  preprod nie przechowywał kopii jej danych.
- Baza `sklepzdoniczkami_preprod` jest odrębna i należy do
  `sklepzdoniczkami_preprod_migrate_limited`. Rola
  `sklepzdoniczkami_preprod_web_limited` ma dostęp DML do schemy `public`,
  bez prawa tworzenia obiektów.
- Migracje Django przeszły na nowej bazie, a rola web utworzyła syntetyczny
  katalog preprod (2 kategorie, 3 produkty). Dane produkcyjne nie zostały
  skopiowane.
- Początkowe role utworzone przez Neon API miały nadmierne uprawnienia;
  zastąpiono je rolami SQL bez `CREATEDB`, `CREATEROLE`, `REPLICATION`,
  `BYPASSRLS` ani członkostwa w `neon_superuser`, a stare role usunięto.
- Połączenia obu ról są w lokalnym, ignorowanym `.env`. `DATABASE_URL_PREPROD`
  należy ustawić w usłudze Render, a `DATABASE_URL_PREPROD_MIGRATE` jako sekret
  GitHub Environment `preprod`; workflow udostępnia go wyłącznie jobowi migracji
  na zaufanym pushu do `dev`.
- Render API nie jest skonfigurowane w tym środowisku. Usługa publiczna
  `sklepzdoniczkami-preprod.onrender.com` odpowiadała HTTP 500; nie można było
  odczytać jej logów ani zaktualizować runtime URL-a z powodu braku API tokena.
- Blueprint wskazuje gałąź GitHub `dev` dla preprod i wdraża po przejściu CI;
  produkcja z `main` wymaga ręcznego wdrożenia po promocji sprawdzonego kodu
  przez PR `dev` → `main`.

## Backup produkcji

- Workflow używa sekretu `DATABASE_URL_PRODUCTION_BACKUP` i roli
  `sklepzdoniczkami_prod_backup`, bez praw tworzenia baz/ról ani superusera.
- Ręczne uruchomienie z brancha PR zostało zablokowane przez ochronę GitHub
  Environment `production`. Backup workflow należy zweryfikować z dozwolonego
  brancha po zatwierdzeniu zmian.
- Neon `prod` zwracał bazę `sklepzdoniczkami_prod` bez tabel w schemie `public`.
  Nie potwierdzono, czy aktywna usługa Render już używa tej bazy. Nie traktuj
  jej jako zweryfikowanego backupu działającego sklepu do czasu potwierdzenia
  URL-a w Renderze i pomyślnego uruchomienia backupu.

## Sekrety CI

- `DATABASE_URL_DEVELOPMENT_RO` — odczytowy test połączenia do Neon dev.
- `DATABASE_URL_DEVELOPMENT_TEST` — URL dedykowanej roli tworzącej tymczasowe
  bazy testowe; nie używać jako URL aplikacji.
- `DATABASE_URL_PRODUCTION_BACKUP` — odczytowy URL do backupu produkcji.
- `BACKUP_ENCRYPTION_KEY` i `BACKUP_HMAC_KEY` — klucze szyfrowania i kontroli
  integralności artefaktów backupu.

Wartości sekretów nie są przechowywane w repozytorium. `.env` pozostaje lokalny.
