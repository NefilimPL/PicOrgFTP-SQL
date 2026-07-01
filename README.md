# PicOrgFTP-SQL
Python picture organiser with ability to send to FTP and SQL

[![Build Windows EXE](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml/badge.svg?branch=main)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml)
[![CI](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/ci.yml)

Project roadmap / plan rozwoju: [PLAN_ROZWOJU.md](PLAN_ROZWOJU.md)

<img width="1920" height="1040" alt="PicOrgFTP-SQL-v0 3 9_i14o8ovPc3" src="https://github.com/user-attachments/assets/8d2f9c31-1103-4368-bea2-7b6899d92761" />
<img width="1082" height="812" alt="image" src="https://github.com/user-attachments/assets/48f3f87e-b4bd-402b-bcbf-16d5a160ed0d" />
<img width="838" height="419" alt="image" src="https://github.com/user-attachments/assets/f5ff136e-213e-4a43-baca-518905c447c6" />

## Pimcore 6.6 REST

1. W Pimcore włącz `Settings > System Settings > Web Service API`.
2. Utwórz lub wybierz dedykowanego użytkownika Pimcore i skopiuj jego klucz API.
3. Nadaj temu użytkownikowi uprawnienia odczytu informacji o serwerze, klas, klasy Product oraz docelowego folderu `Produkty`.
4. Nadaj uprawnienia tworzenia, odczytu i usuwania obiektów, jeżeli test zapisu w ustawieniach ma korzystać z opcji `Usun po tescie`.
5. W PicOrgFTP-SQL otwórz `Ustawienia > Pimcore`, ustaw bazowy URL, klucz API, nazwę klasy i ID folderu nadrzędnego, a następnie przypisz nagłówki CSV do pól Pimcore.
6. Uruchom `Sprawdz konfiguracje`. Popraw każdy wiersz z błędem przed włączeniem tworzenia obiektów w głównym formularzu.
7. Uruchom `Testowo dodaj obiekt`, wpisz odizolowane dane testowe, wybierz sposób sprzątania i sprawdź log na żywo.

Klucz API jest przechowywany w postaci zaszyfrowanej. Standardowy endpoint ustawień ani logi operacji Pimcore nigdy go nie zwracają. Obiekt pozostawiony przez test w Pimcore jest nieopublikowany. Jeżeli automatyczne usuwanie się nie powiedzie, użyj ID, klucza lub ścieżki obiektu z raportu operacji, aby usunąć go ręcznie.




## English

### Operation
The script provides a graphical interface where you enter the product name, type, model and colours. You can drag and drop images into the form. After filling the required fields and confirming:

1. Files are copied to the `_ZDJECIA PRZEROBIONE_` directory and arranged using the structure `NAME/TYPE/MODEL/COLOR1_COLOR2_COLOR3/ADDITION`.
2. Images are optimised, optionally resized/compressed/converted (JPEG/PNG/etc.), and receive a structured name starting with `EAN_slot...`.
3. If `enable_ftp_update` is enabled, new files are uploaded to the FTP server and old versions with the same EAN can be removed.
4. If `enable_sql_update` is enabled, an SQL query is executed to update image paths in the `sql` or `mysql` database.

Program actions are logged to `logs/changes_log.txt` and errors to `logs/error_log.txt`. On first run a `config.json` file with connection settings is created.

### Features
- Product form with auto-complete lists (name/type/model/colors/extras) backed by an Excel workbook; prompts to add missing values and includes a list editor.
- Product fields in desktop and web settings can rename, enable/disable, and require all eight fields (name, type, model, color 1-3, extra, EAN); the normalized settings persist through SQLite data mode or `config.json` in legacy mode.
- Optional EAN (13-digit) with `BRAK-EAN` fallback; quick "Load" to fetch existing entries and images; "Open folder" shortcut.
- Drag-and-drop image slots with thumbnails; move images between slots; per-slot status plus LOCAL/FTP/SQL presence badges; clear/reset actions.
- Automated file organization into `_ZDJECIA PRZEROBIONE_` with a structured folder tree and normalized filenames based on EAN, slot, and product data.
- Image processing options: resize to max dimension, compression quality, max file size limit (quality downscale), and optional TIFF conversion to a chosen format.
- FTP integration: connection test, upload new images, delete old versions for the same EAN, check remote presence, and download remote-only files.
- SQL integration (MS SQL via ODBC or MySQL): connection test, parameterized update query, optional presence check per slot, column detection, and drag-and-drop column mapping.
- Customizable photo fields (add/rename/remove slot definitions) with SQL mapping and translation suggestions (Google/MyMemory/DeepL) saved to localization files.
- Settings & localization: base directory in `local_settings.json`, language switch (auto/pl/ua/eng), encrypted secrets via `APP_SECRET`, admin-unlocked settings where required.
- Diagnostics & logs: error test buttons, code/UI diagnostics reports, `logs/changes_log.txt`/`logs/error_log.txt` plus the in-app log with a clear button.

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

The repository also includes an early local-network web panel. It keeps the desktop application unchanged, but allows users on the same LAN to open a browser, log in and upload files into the configured photo slots. The panel saves uploaded files into the same `_ZDJECIA PRZEROBIONE_` product folder structure as the desktop workflow and can show local or cached FTP previews when those sources are available.

The web panel currently includes product entry loading/search by EAN, product matching by name/type/model with an in-page selection dialog, thumbnail-based slot previews, per-slot FIT processing, loading existing local/FTP photos into slots, drag-and-drop upload and moving between slots, per-slot clearing, LOCAL/FTP/SQL presence badges with lazy FTP preview loading, FTP upload after processing, saving new or existing Excel entries, EAN-grouped web history with user filtering, context-aware custom suggestions, changed-field warnings with per-field undo, a list editor, a clear-form action, browser-editable settings, local file index status/refresh, adding/editing slots with slot-to-SQL-column mapping, local/FTP/SQL connection tests, and user administration with password changes. Login is enabled by default. The initial account is `admin` / `admin`; change that password in **Settings -> Users** before using the panel beyond a trusted test LAN.

Install the web dependencies:

```powershell
python -m pip install -r requirements-web.txt
```

On Windows you can use the included double-click launchers instead of typing commands:

- `START_WEB.bat` starts the web panel, installs missing web dependencies if needed, opens the browser and prints the LAN address.
- `STOP_WEB.bat` stops the web panel started on the configured port.

Start the backend on the server or workstation that should host the service:

```powershell
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Open `http://SERVER_IP:8000` from another computer in the same local network. Keep the service inside a trusted LAN or VPN; do not expose this LAN MVP directly to the public internet. Settings are visible only to web users with the `admin` role.

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

This repository includes a CI workflow in `.github/workflows/ci.yml` and a Windows build workflow in `.github/workflows/build-exe.yml`. CI runs on `push` and `pull_request` for `main`, `master` and `dev`, and checks Python syntax, JavaScript syntax, critical pytest coverage, web smoke tests, UI integrity, desktop imports and lightweight performance paths.

The Windows build workflow builds the EXE with PyInstaller, packages the web runtime as a separate ZIP and uploads the EXE files and ZIP as workflow artifacts only when run manually or when a GitHub release is published. Before building, the workflow checks how many idle online self-hosted runners with `self-hosted`, `Windows` and `X64` labels are available. The desktop EXE and web EXE/ZIP are then built as parallel matrix jobs, so two available runners can work at the same time. If no matching self-hosted runner is available, both matrix jobs fall back to `windows-latest`. When a GitHub release is published, the same workflow also tries to attach `PicOrgFTP-SQL-<tag>.exe`, `PicOrgFTP-SQL-WEB-<tag>.exe` and `PicOrgFTP-SQL-web-<tag>.zip` to that release. The visible program version is taken from the release tag.

To let the workflow inspect repository self-hosted runners, create a fine-grained personal access token with access only to this repository and **Administration: Read-only** permission, then save it as an Actions repository secret named `ACTIONS_RUNNER_READ_TOKEN`. If the secret is missing or the API call is rejected, the workflow safely uses `windows-latest`.

On self-hosted runners, the workflow uses the locally installed Python instead of `actions/setup-python`, because that action may need registry permissions when it tries to install Python into the runner tool cache. The preferred version is Python 3.14; Python 3.13, 3.12 and 3.11 are accepted as fallbacks. Install Python once on the runner as an administrator, then restart the runner service:

```powershell
winget install -e --id Python.Python.3.14 --scope machine
py -3.14 -m pip install --upgrade pip
py -3.14 -m pip install -r requirements-build.txt -r requirements-web.txt
```

The workflow creates an isolated virtual environment in the runner temp directory for each matrix job, then installs Python package dependencies into that venv during each run. The manual `pip install` command above is only useful to verify that Python and package downloads work on the runner. The GitHub Actions runner application should also be kept current because the workflow uses Node 24-compatible action versions.

Artifact upload is guarded by a tiny probe artifact with one-day retention for each matrix target. If GitHub rejects artifact upload, usually because of storage quota or permissions, the EXE build still completes and the workflow summary notes that upload was skipped or partially failed. Normal EXE artifacts use seven-day retention to reduce storage pressure. Release assets are uploaded through the GitHub API, so GitHub CLI (`gh`) does not need to be installed on self-hosted runners.

The local scripts in `Generator exe/` and the GitHub Actions workflow also generate a PyInstaller `--version-file`, so Windows file properties show `File description`, `File version`, `Product name`, `Product version`, `Company name`, `Copyright`, `Internal name` and `Original filename` for both EXE files. In GitHub Actions, product/company metadata is taken from the GitHub repository context; local builds use Windows registration data (`RegisteredOrganization` / `RegisteredOwner`) and then the current Windows user as a fallback.

1. Push the workflow file to your GitHub repository.
2. Go to **Settings → Actions → General** and make sure Actions are enabled for the repository.
3. Go to the **Actions** tab, open **CI**, and check that tests pass for your branch or pull request.
4. Add the optional `ACTIONS_RUNNER_READ_TOKEN` repository secret if you want self-hosted runner detection.
5. Open **Build Windows EXE** and click **Run workflow** only when you want a manual build artifact.
6. Check the workflow summary. It shows how many self-hosted runners were available, whether the build used self-hosted runners or `windows-latest`, and whether artifact upload was available.
7. After the build job finishes, download **PicOrgFTP-SQL-windows**, **PicOrgFTP-SQL-web-exe** or **PicOrgFTP-SQL-web** from the workflow summary when artifact upload succeeded.
8. To publish release assets, create and publish a GitHub release from a tag such as `v1.2.3`; the workflow will build and try to attach the EXE and web ZIP automatically.

If you need to tweak build dependencies, edit `requirements-build.txt`. The workflow uses Python 3.14 by default on GitHub-hosted runners and accepts Python 3.14, 3.13, 3.12 or 3.11 on self-hosted runners.


<img width="1080" height="780" alt="image" src="https://github.com/user-attachments/assets/953f09d3-e6f2-4c14-96a0-7193689fe16a" />
<img width="1082" height="812" alt="PicOrgFTP-SQL-v0 3 9_9jAs7Fw19f" src="https://github.com/user-attachments/assets/0b5cbd68-d42e-49ed-b912-7542d6f965b8" />
<img width="842" height="417" alt="image" src="https://github.com/user-attachments/assets/4ee9558d-6ebf-4d57-84fc-004e2d2c9c8e" />




## Polski

### Działanie
Skrypt udostępnia graficzny interfejs, w którym wprowadza się nazwę, typ, model i kolory produktu. Do formularza można przeciągać zdjęcia metodą drag-and-drop. Po uzupełnieniu wymaganych pól i zatwierdzeniu:

1. Pliki są kopiowane do katalogu `_ZDJECIA PRZEROBIONE_` i układane według struktury `NAZWA/TYP/MODEL/KOLOR1_KOLOR2_KOLOR3/DODATEK`.
2. Zdjęcia są optymalizowane, opcjonalnie skalowane/kompresowane/konwertowane (JPEG/PNG/etc.) i otrzymują ustrukturyzowaną nazwę zaczynającą się od `EAN_slot...`.
3. Jeżeli włączono `enable_ftp_update`, nowe pliki są wysyłane na serwer FTP, a stare wersje o tym samym EAN mogą zostać usunięte.
4. Jeżeli włączono `enable_sql_update`, wykonywane jest zapytanie SQL, które aktualizuje ścieżki obrazów w bazie `sql` lub `mysql`.

Działania programu są zapisywane w `logs/changes_log.txt`, a ewentualne błędy w `logs/error_log.txt`. Przy pierwszym uruchomieniu tworzony jest plik `config.json` z ustawieniami połączeń.

### Funkcje
- Formularz danych produktu z listami podpowiedzi (nazwa/typ/model/kolory/dodatki) opartymi o plik Excel; pytania o dodanie nowych pozycji i edytor list.
- Pola produktu w ustawieniach desktopowych i webowych pozwalają zmienić nazwę, włączać/wyłączać i oznaczać jako wymagane wszystkie osiem pól (nazwa, typ, model, kolory 1-3, dodatek, EAN); znormalizowane ustawienia zapisują się w trybie SQLite albo w `config.json` w trybie legacy.
- Opcjonalny EAN (13 cyfr) z zamiennikiem `BRAK-EAN`; szybkie wczytywanie danych po EAN i skrót do otwarcia katalogu produktu.
- Sloty zdjęć z drag-and-drop i miniaturami; przenoszenie zdjęć między slotami; statusy oraz oznaczenia LOCAL/FTP/SQL; czyszczenie/reset.
- Automatyczna organizacja plików w `_ZDJECIA PRZEROBIONE_` z drzewem katalogów i ustandaryzowaną nazwą opartą o EAN, slot i dane produktu.
- Ustawienia obróbki: skalowanie do maks. wymiaru, kompresja jakości, limit maks. rozmiaru pliku (obniżanie jakości) oraz opcjonalna konwersja TIFF do wybranego formatu.
- FTP: test połączenia, wysyłka nowych zdjęć, usuwanie starych dla tego samego EAN, sprawdzanie obecności na FTP i pobieranie brakujących.
- SQL (MS SQL przez ODBC lub MySQL): test połączenia, zapytanie aktualizujące, opcjonalne sprawdzanie obecności dla slotów, wykrywanie kolumn i mapowanie przez drag-and-drop.
- Konfigurowalne pola zdjęć (dodawanie/zmiana/usuwanie slotów) wraz z mapowaniem SQL i podpowiedziami tłumaczeń (Google/MyMemory/DeepL) zapisywanymi do plików lokalizacji.
- Ustawienia i język: katalog roboczy w `local_settings.json`, przełączanie języka (auto/pl/ua/eng), szyfrowanie sekretów przez `APP_SECRET`, blokada edycji wrażliwych ustawień bez uprawnień administratora.
- Diagnostyka i logi: testy błędów, raporty diagnostyki kodu/UI, `logs/changes_log.txt` i `logs/error_log.txt` plus log w aplikacji z przyciskiem czyszczenia.

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

Repozytorium zawiera także pierwszy lokalny panel webowy. Obecna aplikacja desktopowa zostaje bez zmian, a użytkownicy w tej samej sieci lokalnej mogą otworzyć stronę w przeglądarce, zalogować się i wgrać pliki do skonfigurowanych slotów zdjęć. Panel zapisuje uploady do tej samej struktury `_ZDJECIA PRZEROBIONE_`, której używa desktop, oraz potrafi pokazywać lokalne albo cache'owane podglądy FTP, gdy takie źródła są dostępne.

Panel webowy obsługuje obecnie wczytywanie i wyszukiwanie wpisów po EAN, dopasowanie produktu po nazwie/typie/modelu z oknem wyboru wewnątrz strony, miniatury w slotach, per-slot FIT oraz globalny domyślny FIT w ustawieniach obróbki, wczytywanie istniejących zdjęć lokalnych/FTP do slotów, upload przez przeciąganie plików, przenoszenie zdjęć między slotami, czyszczenie pojedynczego slotu, znaczniki LOCAL/FTP/SQL z leniwym pobieraniem podglądu FTP, wysyłkę FTP po przetworzeniu, zapis nowego albo istniejącego wpisu Excel, historię webową pogrupowaną po EAN z filtrem użytkownika, kontekstowe customowe podpowiedzi, ostrzeżenia zmienionych pól z cofnięciem pojedynczego pola, edytor list, czyszczenie formularza, edycję ustawień w przeglądarce, status i odświeżanie indeksu lokalnych plików, dodawanie/edycję slotów z mapowaniem do kolumn SQL, testy folderów lokalnych/FTP/SQL oraz administrację użytkownikami z ustawianiem haseł. Logowanie jest domyślnie włączone. Pierwsze konto to `admin` / `admin`; zmień to hasło w **Ustawienia -> Użytkownicy** przed używaniem panelu poza zaufanym testem w LAN.

Instalacja zależności webowych:

```powershell
python -m pip install -r requirements-web.txt
```

Na Windows możesz użyć plików do dwukliku zamiast wpisywać komendy:

- `START_WEB.bat` uruchamia panel webowy, doinstalowuje brakujące zależności webowe, otwiera przeglądarkę i pokazuje adres w LAN.
- `STOP_WEB.bat` zatrzymuje panel webowy uruchomiony na skonfigurowanym porcie.

Uruchomienie backendu na serwerze albo komputerze hostującym usługę:

```powershell
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Z innego komputera w tej samej sieci otwórz `http://IP_SERWERA:8000`. Trzymaj usługę w zaufanej sieci LAN albo VPN; tego MVP nie należy wystawiać bezpośrednio do publicznego internetu. Ustawienia są widoczne tylko dla użytkowników webowych z rolą `admin`.

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

W repozytorium znajduje się workflow `.github/workflows/build-exe.yml`, który buduje EXE przez PyInstaller, pakuje panel webowy do osobnego ZIP-a i publikuje pliki jako artefakty. Przed właściwym buildem workflow sprawdza, ile jest dostępnych self-hosted runnerów z etykietami `self-hosted`, `Windows` i `X64`, statusem `online` oraz `busy: false`. Desktop EXE i web EXE/ZIP są budowane jako równoległe joby matrix, więc dwa wolne runnery mogą pracować jednocześnie. Jeżeli nie ma żadnego pasującego self-hosted runnera albo API GitHuba nie pozwala odczytać listy runnerów, oba joby przechodzą na `windows-latest`.

Do sprawdzania runnerów najlepiej dodać sekret `ACTIONS_RUNNER_READ_TOKEN`. Utwórz fine-grained personal access token na GitHubie z dostępem tylko do tego repozytorium i uprawnieniem **Administration: Read-only**. Następnie wejdź w repozytorium na GitHubie: **Settings -> Secrets and variables -> Actions -> New repository secret**, ustaw nazwę `ACTIONS_RUNNER_READ_TOKEN` i wklej token jako wartość. Token nie jest potrzebny do samego builda EXE, ale bez niego sprawdzanie self-hosted runnerów może dostać `403` i wtedy workflow przejdzie na `windows-latest`.

Na self-hosted runnerach workflow używa lokalnie zainstalowanego Pythona zamiast `actions/setup-python`, bo `setup-python` może próbować instalacji do tool cache i wymagać uprawnień do rejestru Windows. Preferowany jest Python 3.14; Python 3.13, 3.12 i 3.11 są akceptowane jako fallback. Zainstaluj Pythona raz na runnerze jako administrator, a potem zrestartuj usługę runnera:

```powershell
winget install -e --id Python.Python.3.14 --scope machine
py -3.14 -m pip install --upgrade pip
py -3.14 -m pip install -r requirements-build.txt -r requirements-web.txt
```

Workflow tworzy izolowane środowisko virtualenv w katalogu tymczasowym runnera dla każdego joba matrix i instaluje zależności Pythona do tego venv przy każdym uruchomieniu. Powyższe `pip install` jest przydatne tylko do sprawdzenia, czy Python i pobieranie pakietów działają na runnerze. Aplikacja GitHub Actions runnera powinna być aktualna, bo workflow używa wersji akcji kompatybilnych z Node 24.

Workflow wykonuje też próbny upload małego artefaktu z retencją jednego dnia dla każdego targetu matrix. Jeżeli GitHub odrzuci upload, najczęściej przez limit miejsca albo uprawnienia, właściwe artefakty są pomijane lub oznaczone jako częściowo nieudane, ale build EXE nie jest przez to przerywany. Zwykłe artefakty EXE mają retencję siedmiu dni, żeby ograniczyć zużycie limitu. Po opublikowaniu GitHub Release workflow dodatkowo próbuje podpiąć do release pliki `PicOrgFTP-SQL-<tag>.exe`, `PicOrgFTP-SQL-WEB-<tag>.exe` oraz `PicOrgFTP-SQL-web-<tag>.zip` przez GitHub API, więc GitHub CLI (`gh`) nie musi być zainstalowany na self-hosted runnerach. Wersja widoczna w GUI i webie jest pobierana z taga release.

Lokalne skrypty z `Generator exe/` i workflow GitHub Actions generują też plik PyInstaller `--version-file`, dlatego we właściwościach Windows dla obu EXE są uzupełniane: opis pliku, wersja pliku, nazwa produktu, wersja produktu, firma, prawa autorskie, nazwa wewnętrzna i oryginalna nazwa pliku. W GitHub Actions dane produktu/firmy są pobierane z kontekstu repozytorium GitHub, a lokalne buildy używają danych rejestracji Windows (`RegisteredOrganization` / `RegisteredOwner`) i awaryjnie bieżącego użytkownika Windows.

1. Wypchnij pliki workflow do swojego repozytorium na GitHub.
2. Wejdź w **Settings -> Actions -> General** i upewnij się, że Actions są włączone dla repozytorium.
3. Jeżeli chcesz używać self-hosted runnerów, upewnij się, że runner ma etykiety `self-hosted`, `Windows` i `X64`, jest `Idle`/`online` oraz nie wykonuje innego joba.
4. Dodaj sekret `ACTIONS_RUNNER_READ_TOKEN`: **Settings -> Secrets and variables -> Actions -> New repository secret**. Wartością ma być fine-grained PAT z uprawnieniem **Administration: Read-only** dla tego repozytorium.
5. Otwórz kartę **Actions**, wybierz **Build Windows EXE** i kliknij **Run workflow**.
6. W podsumowaniu workflow sprawdź sekcję **Runner selection**. `Available self-hosted runners` pokazuje liczbę wolnych runnerów. `Self-hosted: true` oznacza, że joby matrix używały Twoich runnerów. `Self-hosted: false` oznacza fallback na `windows-latest`.
7. Po zakończeniu joba pobierz artefakty **PicOrgFTP-SQL-windows**, **PicOrgFTP-SQL-web-exe** albo **PicOrgFTP-SQL-web**, jeżeli upload artefaktów był dostępny.
8. Jeżeli zobaczysz komunikat `Artifact upload was skipped or partially failed`, build EXE się wykonał, ale GitHub nie przyjął artefaktów. Najczęściej trzeba usunąć stare artefakty albo poczekać na zwolnienie limitu.
9. Aby opublikować pliki przy wydaniu, utwórz i opublikuj release z tagiem, np. `v1.2.3`; workflow zbuduje pliki i spróbuje dodać EXE oraz ZIP do release.

Jeśli chcesz zmienić zależności do budowania, edytuj `requirements-build.txt`. Workflow domyślnie używa Pythona 3.14 na runnerach GitHub-hosted i akceptuje Pythona 3.14, 3.13, 3.12 albo 3.11 na self-hosted runnerach.


Web:
<img width="1912" height="922" alt="msedge_lQaWA3VIoF" src="https://github.com/user-attachments/assets/1cdeae0d-db34-488f-9565-ad791805cf83" />
<img width="1912" height="922" alt="msedge_RxPXrvqZlJ" src="https://github.com/user-attachments/assets/6f66ecca-6e23-40c5-a46e-63693d1eea40" />
<img width="1283" height="631" alt="msedge_NsL6SP5i0C" src="https://github.com/user-attachments/assets/e7a44084-5694-4968-a632-6465818b65f2" />
<img width="1275" height="864" alt="image" src="https://github.com/user-attachments/assets/613d7141-305a-436c-a7fd-32f72fbdd50e" />
<img width="1272" height="307" alt="image" src="https://github.com/user-attachments/assets/24eabef8-57e5-431a-9945-52e14d0eb63b" />
<img width="1249" height="362" alt="image" src="https://github.com/user-attachments/assets/16118148-3323-4868-8038-75825fbfa1ca" />



