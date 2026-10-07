# Lokalne uruchomienie na Windows 11

Ta opcjonalna konfiguracja służy wyłącznie do lokalnego developmentu i testów.
Nie jest serwerem produkcyjnym i nie zmienia VPS-a OVH ani rekordów DNS.

Zainstaluj Python oraz PostgreSQL 18, a następnie z katalogu repozytorium
uruchom:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\setup_windows_selfhost.ps1
```

Skrypt tworzy prywatną bazę development i zapisuje jej poświadczenia poza
repozytorium w `%LOCALAPPDATA%\Sklepzdoniczkami`. Baza nasłuchuje wyłącznie
na `127.0.0.1:5435`. Istniejący plik `.env` nie jest odczytywany ani zmieniany.

Uruchom lokalną aplikację:

```powershell
.\scripts\run_windows_selfhost.ps1
```

Aplikacja testowa jest dostępna pod `http://127.0.0.1:8000/`. Nie wystawiaj
portów bazy ani development servera do Internetu. Dane lokalnej bazy są
oddzielone od produkcyjnej bazy na VPS.

Publiczny hosting, aktualizacje i kopie zapasowe produkcji opisuje
[runbook VPS](self-hosting-recovery.md).
