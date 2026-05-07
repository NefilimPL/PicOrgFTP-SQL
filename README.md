# PicOrgFTP-SQL
Python picture organiser with ability to send to FTP and SQL

[![Build Windows EXE](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml/badge.svg?branch=main)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml)

Project roadmap / plan rozwoju: [PLAN_ROZWOJU.md](PLAN_ROZWOJU.md)

<img width="965" height="1040" alt="image" src="https://github.com/user-attachments/assets/9f646441-23a5-497b-bd4b-32ecf9373ca0" />
<img width="1043" height="557" alt="image" src="https://github.com/user-attachments/assets/3f6849c9-2b9a-4c1f-a570-00e2348b11fa" />
<img width="1043" height="557" alt="image" src="https://github.com/user-attachments/assets/1e76653b-6366-4aef-8b74-a571cce6e2d0" />



## English

### Operation
The script provides a graphical interface where you enter the product name, type, model and colours. You can drag and drop images into the form. After filling the required fields and confirming:

1. Files are copied to the `_ZDJECIA PRZEROBIONE_` directory and arranged using the structure `NAME/TYPE/MODEL/COLOR1_COLOR2_COLOR3/ADDITION`.
2. Images are optimised, optionally resized/compressed/converted (JPEG/PNG/etc.), and receive a structured name starting with `EAN_slot...`.
3. If `enable_ftp_update` is enabled, new files are uploaded to the FTP server and old versions with the same EAN can be removed.
4. If `enable_sql_update` is enabled, an SQL query is executed to update image paths in the `sql` or `mysql` database.

Program actions are logged to `changes_log.txt` and errors to `error_log.txt`. On first run a `config.json` file with connection settings is created.

### Features
- Product form with auto-complete lists (name/type/model/colors/extras) backed by an Excel workbook; prompts to add missing values and includes a list editor.
- Optional EAN (13-digit) with `BRAK-EAN` fallback; quick "Load" to fetch existing entries and images; "Open folder" shortcut.
- Drag-and-drop image slots with thumbnails; move images between slots; per-slot status plus LOCAL/FTP/SQL presence badges; clear/reset actions.
- Automated file organization into `_ZDJECIA PRZEROBIONE_` with a structured folder tree and normalized filenames based on EAN, slot, and product data.
- Image processing options: resize to max dimension, compression quality, max file size limit (quality downscale), and optional TIFF conversion to a chosen format.
- FTP integration: connection test, upload new images, delete old versions for the same EAN, check remote presence, and download remote-only files.
- SQL integration (MS SQL via ODBC or MySQL): connection test, parameterized update query, optional presence check per slot, column detection, and drag-and-drop column mapping.
- Customizable photo fields (add/rename/remove slot definitions) with SQL mapping and translation suggestions (Google/MyMemory/DeepL) saved to localization files.
- Settings & localization: base directory in `local_settings.json`, language switch (auto/pl/ua/eng), encrypted secrets via `APP_SECRET`, admin-unlocked settings where required.
- Diagnostics & logs: error test buttons, code/UI diagnostics reports, `changes_log.txt`/`error_log.txt` plus the in-app log with a clear button.

### Configuration
The application stores its working files in the directory defined in the `local_settings.json` file located next to `PicOrgFTP-SQL.pyw`. The file is created automatically on first launch; if it does not contain a path, the script asks for a folder and saves the selected location back to `local_settings.json`. You can use forward slashes in the path (e.g. `C:/TEST/GUI_ZDJ`) to avoid escaping backslashes on Windows. If the configured folder later becomes unavailable, the application asks you to point to a new location.

The first lines of the file contain a configuration section that makes the script easy to adjust. You can change:

- `base_dir_override` in `local_settings.json` – base directory used to store data.
- `language` in `local_settings.json` – preferred interface language (`auto`, `pl`, `ua`, `eng`).
- `APP_SECRET` – key used for encrypting configuration data.
- `PORT` – default FTP server port.
- `SQL_UPDATE_TEMPLATE` – default SQL query that updates image paths.
- `DEFAULT_CONFIG` – initial FTP/SQL/MySQL login data and SQL query used when updating paths. All text fields use raw strings `r""`, so special characters do not need escaping. The `ftp`, `sql` and `mysql` sections include `host`/`server`, `port`, `user`, `pass` (and `path` for FTP). Additional keys are `db_type`, `sql_query`, `enable_ftp_update` and `enable_sql_update`.

Changing these values before running the script helps tailor the program to your environment.

### LAN web panel

The repository also includes an early local-network web panel. It keeps the desktop application unchanged, but allows users on the same LAN to open a browser, log in and upload files into the configured photo slots. The first implementation saves uploaded files into the same `_ZDJECIA PRZEROBIONE_` product folder structure as the desktop workflow. FTP and SQL synchronization can be added to the same backend workflow later.

Install the web dependencies:

```powershell
python -m pip install -r requirements-web.txt
```

On Windows you can use the included double-click launchers instead of typing commands:

- `START_WEB.bat` starts the web panel, installs missing web dependencies if needed, opens the browser and prints the LAN address.
- `STOP_WEB.bat` stops the web panel started on the configured port.

Start the backend on the server or workstation that should host the service:

```powershell
$env:PICORG_WEB_ADMIN_PASSWORD = "change-this-password"
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Open `http://SERVER_IP:8000` from another computer in the same local network. The default login is `admin` / `admin` if `PICORG_WEB_ADMIN_PASSWORD` is not set. Keep the service inside a trusted LAN or VPN; do not expose this development login directly to the public internet.

### Building an executable

The application can be frozen with tools such as PyInstaller. When doing so, make sure the `Localization` directory is bundled together with the program so that the language switcher keeps working after conversion to `.exe`. The helper script `Dodatkowe (konwerter)/Konwerter PY oraz PYW na EXE v0.0.3.py` already adds the translation folders automatically and forces PyInstaller to bundle the `mysql.connector` package together with all locale data used for error messages, so the resulting EXE contains every runtime dependency required by the GUI. If you build manually, one possible command is:

```bash
pyinstaller PicOrgFTP-SQL.pyw \
  --name PicOrgFTP-SQL \
  --noconsole \
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization"
```

The runtime automatically searches for translation files next to the executable, in the PyInstaller temporary directory and inside the installed package. This means you can also ship an updated `Localization` folder next to the generated `PicOrgFTP-SQL.exe` without rebuilding the binary. The `local_settings.json` file will still be created next to the executable and stores both the working directory and the chosen language.

### GitHub Actions (Windows EXE)

This repository includes a Windows build workflow in `.github/workflows/build-exe.yml`. It builds the EXE with PyInstaller and uploads it as a workflow artifact.

1. Push the workflow file to your GitHub repository.
2. Go to **Settings → Actions → General** and make sure Actions are enabled for the repository.
3. Go to the **Actions** tab, open **Build Windows EXE**, and click **Run workflow** to build on demand (or push to `main`/`master` to run automatically).
4. After the job finishes, download the artifact named **PicOrgFTP-SQL-windows** from the workflow summary.

If you need to tweak build dependencies, edit `requirements-build.txt`. The workflow uses Python 3.11 by default.

## Polski

### Działanie
Skrypt udostępnia graficzny interfejs, w którym wprowadza się nazwę, typ, model i kolory produktu. Do formularza można przeciągać zdjęcia metodą drag-and-drop. Po uzupełnieniu wymaganych pól i zatwierdzeniu:

1. Pliki są kopiowane do katalogu `_ZDJECIA PRZEROBIONE_` i układane według struktury `NAZWA/TYP/MODEL/KOLOR1_KOLOR2_KOLOR3/DODATEK`.
2. Zdjęcia są optymalizowane, opcjonalnie skalowane/kompresowane/konwertowane (JPEG/PNG/etc.) i otrzymują ustrukturyzowaną nazwę zaczynającą się od `EAN_slot...`.
3. Jeżeli włączono `enable_ftp_update`, nowe pliki są wysyłane na serwer FTP, a stare wersje o tym samym EAN mogą zostać usunięte.
4. Jeżeli włączono `enable_sql_update`, wykonywane jest zapytanie SQL, które aktualizuje ścieżki obrazów w bazie `sql` lub `mysql`.

Działania programu są zapisywane w `changes_log.txt`, a ewentualne błędy w `error_log.txt`. Przy pierwszym uruchomieniu tworzony jest plik `config.json` z ustawieniami połączeń.

### Funkcje
- Formularz danych produktu z listami podpowiedzi (nazwa/typ/model/kolory/dodatki) opartymi o plik Excel; pytania o dodanie nowych pozycji i edytor list.
- Opcjonalny EAN (13 cyfr) z zamiennikiem `BRAK-EAN`; szybkie wczytywanie danych po EAN i skrót do otwarcia katalogu produktu.
- Sloty zdjęć z drag-and-drop i miniaturami; przenoszenie zdjęć między slotami; statusy oraz oznaczenia LOCAL/FTP/SQL; czyszczenie/reset.
- Automatyczna organizacja plików w `_ZDJECIA PRZEROBIONE_` z drzewem katalogów i ustandaryzowaną nazwą opartą o EAN, slot i dane produktu.
- Ustawienia obróbki: skalowanie do maks. wymiaru, kompresja jakości, limit maks. rozmiaru pliku (obniżanie jakości) oraz opcjonalna konwersja TIFF do wybranego formatu.
- FTP: test połączenia, wysyłka nowych zdjęć, usuwanie starych dla tego samego EAN, sprawdzanie obecności na FTP i pobieranie brakujących.
- SQL (MS SQL przez ODBC lub MySQL): test połączenia, zapytanie aktualizujące, opcjonalne sprawdzanie obecności dla slotów, wykrywanie kolumn i mapowanie przez drag-and-drop.
- Konfigurowalne pola zdjęć (dodawanie/zmiana/usuwanie slotów) wraz z mapowaniem SQL i podpowiedziami tłumaczeń (Google/MyMemory/DeepL) zapisywanymi do plików lokalizacji.
- Ustawienia i język: katalog roboczy w `local_settings.json`, przełączanie języka (auto/pl/ua/eng), szyfrowanie sekretów przez `APP_SECRET`, blokada edycji wrażliwych ustawień bez uprawnień administratora.
- Diagnostyka i logi: testy błędów, raporty diagnostyki kodu/UI, `changes_log.txt` i `error_log.txt` plus log w aplikacji z przyciskiem czyszczenia.

### Konfiguracja
Aplikacja zapisuje pliki robocze w katalogu zdefiniowanym w pliku `local_settings.json`, znajdującym się obok `PicOrgFTP-SQL.pyw`. Plik tworzy się automatycznie przy pierwszym uruchomieniu; jeżeli nie zawiera ścieżki, skrypt poprosi o wskazanie folderu i zapisze wybór do `local_settings.json`. W ścieżce możesz użyć ukośników (np. `C:/TEST/GUI_ZDJ`), aby uniknąć konieczności podwójnego wpisywania ukośników odwrotnych w systemie Windows. Jeżeli zapisany katalog stanie się niedostępny, aplikacja poprosi o wybranie nowej lokalizacji.

Pierwsze linie pliku zawierają sekcję konfiguracyjną ułatwiającą dostosowanie skryptu do własnych potrzeb. Można tam zmienić m.in.:

- `base_dir_override` w `local_settings.json` – katalog startowy do zapisu danych.
- `language` w `local_settings.json` – preferowany język interfejsu (`auto`, `pl`, `ua`, `eng`).
- `APP_SECRET` – klucz używany do szyfrowania danych konfiguracji.
- `PORT` – domyślny port serwera FTP.
- `SQL_UPDATE_TEMPLATE` – domyślne zapytanie SQL aktualizujące ścieżkę obrazów w bazie.
- `DEFAULT_CONFIG` – początkowe dane logowania FTP/SQL/MySQL oraz zapytanie SQL wykorzystywane przy aktualizacji ścieżek. Wszystkie pola tekstowe używają surowych łańcuchów `r""`, dzięki czemu nie trzeba uciekać znaków specjalnych. Sekcje `ftp`, `sql` i `mysql` zawierają odpowiednio pola `host`/`server`, `port`, `user`, `pass` (oraz `path` dla FTP). Pozostałe klucze to `db_type`, `sql_query`, `enable_ftp_update` i `enable_sql_update`.

Zmiana tych wartości przed uruchomieniem skryptu umożliwia szybkie dostosowanie działania programu do własnego środowiska.

### Panel webowy w LAN

Repozytorium zawiera także pierwszy lokalny panel webowy. Obecna aplikacja desktopowa zostaje bez zmian, a użytkownicy w tej samej sieci lokalnej mogą otworzyć stronę w przeglądarce, zalogować się i wgrać pliki do skonfigurowanych slotów zdjęć. Pierwsza wersja zapisuje uploady do tej samej struktury `_ZDJECIA PRZEROBIONE_`, której używa desktop. Synchronizację FTP i SQL można później dopiąć w tym samym workflow backendu.

Instalacja zależności webowych:

```powershell
python -m pip install -r requirements-web.txt
```

Na Windows możesz użyć plików do dwukliku zamiast wpisywać komendy:

- `START_WEB.bat` uruchamia panel webowy, doinstalowuje brakujące zależności webowe, otwiera przeglądarkę i pokazuje adres w LAN.
- `STOP_WEB.bat` zatrzymuje panel webowy uruchomiony na skonfigurowanym porcie.

Uruchomienie backendu na serwerze albo komputerze hostującym usługę:

```powershell
$env:PICORG_WEB_ADMIN_PASSWORD = "zmien-to-haslo"
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Z innego komputera w tej samej sieci otwórz `http://IP_SERWERA:8000`. Domyślne logowanie to `admin` / `admin`, jeżeli nie ustawiono `PICORG_WEB_ADMIN_PASSWORD`. Trzymaj usługę w zaufanej sieci LAN albo VPN; tego prostego logowania nie należy wystawiać bezpośrednio do publicznego internetu.

### Budowanie pliku wykonywalnego

Aplikację można zamrozić np. za pomocą PyInstaller. Należy przy tym dołączyć katalog `Localization`, aby po konwersji do `.exe` nadal działało przełączanie języka. Pomocniczy skrypt `Dodatkowe (konwerter)/Konwerter PY oraz PYW na EXE v0.0.3.py` automatycznie dołącza katalogi tłumaczeń oraz wymusza spakowanie pakietu `mysql.connector` wraz z danymi lokalizacyjnymi komunikatów błędów, dzięki czemu powstały plik EXE zawiera wszystkie zależności wymagane przez interfejs GUI. Przy ręcznym budowaniu przykładowe polecenie wygląda następująco:

```bash
pyinstaller PicOrgFTP-SQL.pyw \
  --name PicOrgFTP-SQL \
  --noconsole \
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization"
```

Podczas działania program wyszukuje pliki tłumaczeń obok pliku wykonywalnego, w katalogu tymczasowym PyInstaller oraz w zainstalowanym pakiecie. Dzięki temu można także dołączyć lub zaktualizować katalog `Localization` bez ponownego budowania `PicOrgFTP-SQL.exe`. Plik `local_settings.json` jest nadal tworzony obok programu i przechowuje zarówno katalog roboczy, jak i wybrany język.

### GitHub Actions (budowanie EXE na Windows)

W repozytorium znajduje się workflow `.github/workflows/build-exe.yml`, który buduje EXE przez PyInstaller i publikuje je jako artefakt.

1. Wypchnij pliki workflow do swojego repozytorium na GitHub.
2. Wejdź w **Settings → Actions → General** i upewnij się, że Actions są włączone.
3. Otwórz kartę **Actions**, wybierz **Build Windows EXE** i kliknij **Run workflow** (lub wypchnij zmiany na `main`/`master`, aby uruchomić automatycznie).
4. Po zakończeniu joba pobierz artefakt **PicOrgFTP-SQL-windows** z podsumowania workflow.

Jeśli chcesz zmienić zależności do budowania, edytuj `requirements-build.txt`. Workflow domyślnie używa Pythona 3.11.
