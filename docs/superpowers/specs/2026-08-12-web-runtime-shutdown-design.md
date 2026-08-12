# Niezawodne zamykanie runtime panelu WWW — projekt

## Cel

Zamknięcie panelu WWW z lokalnego menedżera ma zakończyć wyłącznie procesy należące do uruchomionej instancji: serwer WWW, jego wrapper PyInstaller oraz launcher `START_WEB.bat` / PowerShell. Okno GUI ma zamknąć się dopiero po potwierdzeniu, że serwer nie nasłuchuje już na porcie.

## Kontekst

`PicOrgFTP-SQL-WEB.exe` jest budowany w trybie PyInstaller `--onefile`. Jedna uruchomiona rola składa się z bootloadera oraz procesu aplikacji. Menedżer uruchamia dodatkowo tę samą aplikację z parametrem `--service-run`, aby serwer WWW mógł działać niezależnie od GUI. Z kolei wariant skryptowy uruchamia `python -m uvicorn` z procesu PowerShell.

Obecny zapis `.picorg_web.pid` zawiera tylko jeden PID. Zamykanie nie zachowuje informacji o launcherze, nie weryfikuje kodu `taskkill` ani końcowego stanu portu. Skrypt zatrzymujący kończy wyłącznie jeden PID.

## Zakres

- W metadanych runtime zapisywać PID serwera i PID kontrolowanego launchera.
- Wariant EXE rozpoznaje wrapper PyInstaller uruchomiony dla `--service-run` jako launcher.
- `START_WEB.ps1` przekazuje swój PID jako jawnie oznaczony launcher.
- Zatrzymanie kończy launcher wraz z jego procesami potomnymi; jako fallback kończy znany PID serwera i wykryte procesy nasłuchujące panelu.
- Każde wywołanie zakończenia ocenia rzeczywisty kod narzędzia systemowego.
- Przed zwróceniem sukcesu kod czeka przez ograniczony czas, aż port panelu przestanie nasłuchiwać.
- Jeżeli serwer nadal działa albo Windows odmawia zatrzymania, GUI pozostaje otwarte i wyświetla konkretny komunikat.
- `STOP_WEB.ps1` stosuje ten sam model drzewa i nie kończy tylko pojedynczego PID.

## Poza zakresem

- Nie skanujemy i nie kończymy procesów wyłącznie po nazwie `powershell.exe`, `python.exe` albo `PicOrgFTP-SQL-WEB.exe`.
- Nie wprowadzamy Windows Job Object ani zmian w sposobie budowania EXE.
- Nie zamykamy obcych serwerów, konsol ani aplikacji, nawet jeśli używają podobnej nazwy procesu.

## Przepływ zamykania

1. Menedżer odczytuje metadane bieżącej instancji.
2. Tworzy uporządkowaną listę zaufanych PID-ów: launcher, PID serwera, a następnie rozpoznane procesy panelu nasłuchujące na skonfigurowanym porcie.
3. Dla każdego istniejącego i rozpoznanego PID-u uruchamia `taskkill /T /F`, aby zakończyć całe jego drzewo; błędny kod wyjścia zapisuje w wyniku diagnostycznym.
4. Program odpyta port przez krótki, ograniczony timeout. Sukces jest możliwy tylko wtedy, gdy na porcie nie ma już procesu panelu.
5. Po sukcesie usuwa metadane. Po niepowodzeniu zachowuje metadane dla kolejnej próby i zwraca błąd do GUI.

## Dane i zgodność

Nowe pola pliku `.picorg_web.pid`:

- `pid`: PID procesu serwera, zachowany dla zgodności z dotychczasowymi instalacjami;
- `launcher_pid`: PID procesu, którego drzewo należy zamknąć;
- `launcher`: opis trybu uruchomienia.

Starsze metadane zawierające tylko `pid` nadal będą obsługiwane. PID launchera zapisujemy tylko dla jawnie kontrolowanych ścieżek uruchomienia: procesu PyInstaller `--service-run` oraz `START_WEB.ps1`.

## Obsługa błędów

Kod zatrzymujący zgłasza błąd, gdy:

- system nie może zakończyć oznaczonego procesu;
- po timeoutcie panel nadal nasłuchuje na porcie;
- zatrzymanie zaplanowanej usługi nie powiedzie się, a jej proces wciąż działa.

Brak działającego panelu pozostaje poprawnym, idempotentnym wynikiem.

## Testy akceptacyjne

- `stop_web()` uwzględnia `launcher_pid` przed PID-em serwera i przekazuje `/T` do `taskkill`.
- Nie zwraca sukcesu, gdy `taskkill` zwraca błąd lub po timeoutcie działa rozpoznany listener panelu.
- Zwraca sukces i usuwa metadane, gdy listener znika.
- Uszkodzone lub starsze metadane bez `launcher_pid` nie blokują zatrzymania.
- `START_WEB.ps1` zapisuje PID PowerShell launchera, a `STOP_WEB.ps1` zatrzymuje drzewo procesu.
- Testy interfejsu nadal potwierdzają, że GUI zamyka się wyłącznie po sukcesie `stop_web()`.
