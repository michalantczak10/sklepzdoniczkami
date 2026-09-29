# Wyniki automatycznego provisioningu Neon (podsumowanie)

Data: 2026-09-29 16:16:56

Co sprawdzono:
- .env: NEON_API_KEY znaleziony; STRIPE_SECRET_KEY_DEVELOPMENT znaleziony i zweryfikowany (Stripe API OK);
- DATABASE_URL_DEVELOPMENT był zmaskowany/niekompletny — brak możliwości połączenia;
- psql nie jest zainstalowane w tym środowisku, więc GRANTy nie mogły być zastosowane.

Działania wykonane automatycznie:
- Utworzono role na branchu `dev`: `sklepzdoniczkami_dev_ro`, `sklepzdoniczkami_dev_migrate` (hasła nie są zapisywane w repo).
- Próbowano wygenerować tymczasowy credential właściciela, lecz Neon API nie zwróciło plaintext connection_string / compute endpoint był nieaktywny — nie udało się zbudować pełnego DATABASE_URL.

Co wymaga ręcznej akcji (kolejność):
1. W Neon Console: aktywować compute dla branchu `dev` (udostępni host/endpoint).
2. W Neon Console: utworzyć (lub wyeksportować) credential właściciela i przekleić/ustawić pełny connection string (DATABASE_URL_DEVELOPMENT) w .env albo jako GitHub Secret.
3. Na maszynie z `psql`: uruchomić `neon_hardening.ps1` aby zastosować GRANTy (lub wykonać GRANTy ręcznie).

Uwagi:
- Nie modyfikowano istniejących sekretów produkcyjnych.
- Pełna automatyzacja wymaga NEON API z prawami admina lub aktywnego compute endpoint.

Chętnie dokończę automat po aktywacji compute lub po otrzymaniu (bezpiecznie) admin NEON API key — daj znać jak chcesz dalej.
