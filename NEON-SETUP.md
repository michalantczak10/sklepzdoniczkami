NEON Setup & Hardening — Audit summary

Data: 2026-09-29

Wykonane automatycznie:
- Zrewidowano projekt Neon: znaleziono branche `dev` i `prod`.
- Utworzono/upewniono się, że istnieją role migrate/ro dla `dev` (sklepzdoniczkami_dev_migrate / _dev_ro) i częściowo dla `prod` (tam gdzie API pozwoliło).
- Zaktualizowano CI workflow (.github/workflows/ci.yml) tak, aby uruchamiać testy na branchach `main, dev` i korzystać z sekretu `DATABASE_URL_DEVELOPMENT` (sekret zapisany w GH).
- Zapisano w GitHub Secrets (repo: michalantczak10/sklepzdoniczkami):
  - NEON_API_KEY (obecny)
  - DATABASE_URL_DEVELOPMENT, DATABASE_NAME_DEVELOPMENT
  - DATABASE_URL_PRODUCTION, DATABASE_NAME_PRODUCTION (jeśli dostępne)
  - STRIPE_SECRET_KEY_DEVELOPMENT, STRIPE_PUBLIC_KEY_DEVELOPMENT, STRIPE_WEBHOOK_SECRET_DEVELOPMENT
  - Backup keys (wcześniej obecne)
- Zaktualizowano lokalne .env (masked) przy użyciu wygenerowanych poświadczeń tam, gdzie skrypt miał do nich dostęp.
- Uruchomiono migracje na dev i testy: wszystkie testy lokalne przeszły (44 passed, 6 warnings).

Co nie mogło zostać w pełni zautomatyzowane (wymaga ręcznej interwencji lub admina z Neon Console):
1) Uaktywnienie / włączenie compute endpoint dla branch `prod` w Neon Console, jeśli jest w stanie "idle" — bez aktywnego endpointu nie wszystkie operacje (np. uzyskanie plaintext credential) działają.
2) Zmiana właściciela bazy produkcyjnej na `sklepzdoniczkami_prod_owner` — rekomenduję wykonać to w Neon Console (Query/SQL) lub nadać admin NEON_API_KEY i pozwolić na automatyczną rotację.
3) Rotacja projektowego NEON API key w Neon Console (API często nie zwraca plaintext key, więc manualny krok w Console jest bezpieczniejszy).
4) Potwierdzenie backupów/PITR i zasady retencji w Neon Console oraz test przywrócenia backupu.

Zalecenia bezpieczeństwa:
- Nie commitować pliku `.env`. Jest w .gitignore.
- Trzymać production secrets wyłącznie w GitHub Secrets/CI vault i w Neon Console.
- Użyć dedykowanej roli `migrate` (sklepzdoniczkami_*_migrate) do uruchamiania migracji w CI, a app role (sklepzdoniczkami_*_app) trzymać z ograniczonymi uprawnieniami DML.
- Rotować admin NEON_API_KEY w Console regularnie.

Następne kroki proponowane (mogę wykonać automatycznie, jeśli dasz admin NEON key lub po potwierdzeniu manualnych kroków):
- Dokończyć zmianę ownera produkcyjnej bazy i ponownie zastosować GRANTy.
- Test restore z backupu.
- Upewnić się, że CI uruchamia testy na `dev` używając SECRETów (zrobione) i że deployy korzystają z odpowiednich zmiennych.

Kontakt / notatka: wszystkie zmiany kodeksowe zostały wprowadzone w nowym branchu `audit-fixes` (commit + push). PR zostanie utworzony automatycznie; jeśli automatyczny merge nie zadziała, proszę zmergować ręcznie (branch -> dev).