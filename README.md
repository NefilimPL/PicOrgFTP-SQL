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

If you have Python installed locally you can run the helper script `Dodatkowe (konwerter)/Konwerter PY oraz PYW na EXE v0.0.3.py` to launch an interactive PyInstaller builder that automatically bundles the localisation files and the `mysql.connector` locales required by the GUI. When building manually, remember to include the `Localization` directory so that the language switcher keeps working after conversion to `.exe`. One possible command is:

```bash
pyinstaller PicOrgFTP-SQL.pyw \
  --name PicOrgFTP-SQL \
  --noconsole \
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization"
```

The runtime automatically searches for translation files next to the executable, in the PyInstaller temporary directory and inside the installed package. This means you can also ship an updated `Localization` folder next to the generated `PicOrgFTP-SQL.exe` without rebuilding the binary. The `local_settings.json` file will still be created next to the executable and stores both the working directory and the chosen language.

Users who do not have Python installed can run the `Dodatkowe (konwerter)/build_exe_portable.bat` script. The batch file downloads a portable Python runtime together with Tkinter support, PyInstaller and all runtime libraries used by the app (including `tkinterdnd2`, Pillow, database drivers and spreadsheet helpers) — only on first run. It automatically points the helper converter script to `PicOrgFTP-SQL.pyw` and leaves the temporary toolchain in the `build-tools` directory for reuse. You can optionally pass a different `.py`/`.pyw` path as the first argument if you want to bundle another entry point. Any `.ico`, `.png`, `.jpg` or `.jpeg` files placed next to the batch script are automatically offered as icon choices during the build.

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

Jeżeli na komputerze jest zainstalowany Python, najwygodniej uruchomić pomocniczy skrypt `Dodatkowe (konwerter)/Konwerter PY oraz PYW na EXE v0.0.3.py`, który startuje interaktywny kreator PyInstaller i automatycznie dołącza katalogi tłumaczeń oraz lokalizacje `mysql.connector` wymagane przez interfejs GUI. Przy ręcznym budowaniu należy pamiętać o dołączeniu katalogu `Localization`, aby po konwersji do `.exe` nadal działało przełączanie języka. Przykładowe polecenie:

```bash
pyinstaller PicOrgFTP-SQL.pyw \
  --name PicOrgFTP-SQL \
  --noconsole \
  --add-data "picorgftp_sql/Localization;picorgftp_sql/Localization"
```

Podczas działania program wyszukuje pliki tłumaczeń obok pliku wykonywalnego, w katalogu tymczasowym PyInstaller oraz w zainstalowanym pakiecie. Dzięki temu można także dołączyć lub zaktualizować katalog `Localization` bez ponownego budowania `PicOrgFTP-SQL.exe`. Plik `local_settings.json` jest nadal tworzony obok programu i przechowuje zarówno katalog roboczy, jak i wybrany język.

Osoby, które nie mają zainstalowanego Pythona, mogą użyć skryptu wsadowego `Dodatkowe (konwerter)/build_exe_portable.bat`. Plik BAT przy pierwszym uruchomieniu pobiera przenośne środowisko Python z obsługą Tkintera, PyInstallerem oraz wszystkimi bibliotekami wymaganymi przez aplikację (w tym `tkinterdnd2`, Pillow, sterowniki baz danych i obsługę arkuszy). Skrypt automatycznie wskazuje konwerterowi plik `PicOrgFTP-SQL.pyw` i pozostawia przygotowane narzędzia w katalogu `build-tools`, aby można było ponownie z nich skorzystać w kolejnych kompilacjach. W razie potrzeby można przekazać inną ścieżkę do pliku `.py`/`.pyw` jako pierwszy argument, aby zbudować inny punkt wejścia. Dodatkowo wszystkie pliki `.ico`, `.png`, `.jpg` lub `.jpeg` znajdujące się obok tego BAT-a są automatycznie proponowane jako ikony podczas budowania.

