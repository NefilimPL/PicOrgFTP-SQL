# PicOrgFTP-SQL
Python picture organiser with ability to send to FTP and SQL

## English

### Operation
The script provides a graphical interface where you enter the product name, type, model and colours. You can drag and drop images into the form. After filling the required fields and confirming:

1. Files are copied to the `_ZDJECIA PRZEROBIONE_` directory and arranged using the structure `NAME/TYPE/MODEL/COLOR1_COLOR2_COLOR3/ADDITION`.
2. Images are optimised, converted to JPEG/PNG and receive the name `EAN_slot.ext`.
3. If `enable_ftp_update` is enabled, new files are uploaded to the FTP server and old versions with the same EAN can be removed.
4. If `enable_sql_update` is enabled, an SQL query is executed to update image paths in the `sql` or `mysql` database.

Program actions are logged to `changes_log.txt` and errors to `error_log.txt`. On first run a `config.json` file with connection settings is created.

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
2. Zdjęcia są optymalizowane, konwertowane do JPEG/PNG i otrzymują nazwę `EAN_slot.ext`.
3. Jeżeli włączono `enable_ftp_update`, nowe pliki są wysyłane na serwer FTP, a stare wersje o tym samym EAN mogą zostać usunięte.
4. Jeżeli włączono `enable_sql_update`, wykonywane jest zapytanie SQL, które aktualizuje ścieżki obrazów w bazie `sql` lub `mysql`.

Działania programu są zapisywane w `changes_log.txt`, a ewentualne błędy w `error_log.txt`. Przy pierwszym uruchomieniu tworzony jest plik `config.json` z ustawieniami połączeń.

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
