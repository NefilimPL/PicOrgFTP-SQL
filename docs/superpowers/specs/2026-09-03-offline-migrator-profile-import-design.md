# Offline migrator profilu PicOrgFTP-SQL — projekt

## Cel

Usunąć import starej konfiguracji z działającej aplikacji PicSyncra i udostępnić
go wyłącznie w osobnym `PicSyncra-Migrator.exe`. Migrator ma obsługiwać dwa
jawnie wybierane tryby:

1. **`picorgftp_sql.sqlite` → `picsyncra.sqlite`** — istniejąca migracja bazy
   SQLite sprzed rebrandingu.
2. **`LEGACY` → SQLite PicSyncra** — import kompletnego, wskazanego folderu
   PicOrgFTP-SQL do nowej bazy SQLite PicSyncra.

Ustawienie typu bazy w aplikacji (`sqlite` lub `legacy`) pozostaje dostępne i
nie zmienia swojego kontraktu. Udana migracja naturalnie ustawia docelową
konfigurację na `sqlite`, ponieważ jej wynikiem jest baza `picsyncra.sqlite`.

## Zakres

- Jeden migrator GUI z wyborem dwóch trybów i wspólnym paskiem postępu.
- Zachowanie istniejącego przepływu konwersji pojedynczej skonfigurowanej
  SQLite bez zmiany jego reguł bezpieczeństwa.
- Nowy, offline'owy przepływ importu jednego pełnego profilu PicOrgFTP-SQL:
  `picorgftp_sql.sqlite` wraz z sidecarami oraz bezpośrednie pliki
  `config.json`, `lists.xlsx`, `web_users.json`, `web_history.json`,
  `file_index.json` i `local_settings.json`.
- Usunięcie z WWW i aplikacji głównej interfejsu oraz trasy importu starego
  profilu.
- Testy regresji dla obu trybów, bezpieczeństwa transakcji oraz braku dostępu
  do importu przez HTTP.

## Poza zakresem

- Zmiana opcji `SQLite`/`legacy` w ustawieniach aplikacji.
- Automatyczne przeszukiwanie dysku w poszukiwaniu profilu źródłowego.
- Nadpisywanie istniejącej docelowej bazy `picsyncra.sqlite`.
- Uruchamianie głównej aplikacji po migracji.
- Usuwanie modułów domenowych `legacy_profile`, `legacy_profile_import` i
  `legacy_migration`; pozostają one implementacją używaną przez migrator.

## Architektura

Migrator pozostaje cienką aplikacją Tkinter. Widok ma pole wyboru trybu, pole
folderu aplikacji PicSyncra oraz — tylko dla pełnego importu profilu — pole
folderu źródłowego PicOrgFTP-SQL. Przed drugim potwierdzeniem GUI pokazuje
rozpoznane źródło, docelową bazę i katalog archiwum. Praca wykonywana jest w
wątku roboczym, a aktualizacje widoku są przekazywane wyłącznie przez
`Tk.after`.

Logika domenowa jest rozdzielona według rodzaju źródła:

- istniejący `offline_legacy_sqlite_migrator` zachowuje odpowiedzialność za
  kopię i aktualizację samej starej SQLite;
- nowy offline'owy adapter profilu wywołuje `load_legacy_profile` oraz
  `adopt_legacy_profile` dla jednego, wybranego katalogu;
- współdzielone funkcje offline odczytują i atomowo aktualizują
  `local_settings.json` wskazanej aplikacji, bez używania globalnego stanu
  uruchomionego serwera WWW.

Oba tryby najpierw zatrzymują tylko zweryfikowane procesy PicSyncra/PicOrgFTP
należące do wskazanego katalogu aplikacji. Nie wybierają ani nie kończą
ogólnych procesów `python.exe` lub procesów spoza tego katalogu.

## Przepływy danych

### Tryb 1 — konwersja starej SQLite

1. Użytkownik wybiera katalog aplikacji PicSyncra.
2. Migrator odczytuje wyłącznie jego `local_settings.json`, rozwiązuje
   wskazaną `picorgftp_sql.sqlite` i odrzuca nieistniejące źródło albo
   istniejący cel `picsyncra.sqlite`.
3. Migrator zatrzymuje zweryfikowaną aplikację, tworzy kopię roboczą przez API
   SQLite, aktualizuje schemat i porównuje integralność, liczniki tabel,
   produkty oraz konta.
4. Po walidacji publikuje nową bazę, atomowo przełącza `local_settings.json`
   na `data_mode=sqlite`, `database_location_mode=custom` i nową ścieżkę, po
   czym archiwizuje jedynie użyte pliki SQLite i sidecary.

### Tryb 2 — pełny import LEGACY

1. Użytkownik wybiera katalog aplikacji PicSyncra i dokładnie jeden folder
   źródłowy PicOrgFTP-SQL przez natywny wybór katalogu.
2. Migrator rozpoznaje źródło przez `load_legacy_profile`; pobiera wyłącznie
   dozwolone pliki bezpośrednio z wybranego katalogu, nie miesza plików z
   sąsiednich katalogów i odrzuca katalog bez importowalnych danych.
3. Z konfiguracji docelowej aplikacji wyznaczana jest ścieżka nowej SQLite.
   Jeżeli cel istnieje, migracja kończy się przed zmianą źródła i ustawień.
4. Po zatrzymaniu zweryfikowanej aplikacji adapter uruchamia
   `adopt_legacy_profile`. Transakcja buduje roboczą bazę, importuje dane
   SQLite oraz JSON/XLSX z tego samego profilu, porównuje dane i konta,
   wykonuje archiwum w `BACKUP/legacy-import`, a następnie publikuje wynik.
5. Finalizator offline atomowo zapisuje ustawienia docelowej aplikacji jako
   SQLite i zachowuje dozwolone ustawienia importowanego profilu. Jeśli
   zapis ustawień albo publikacja się nie powiedzie, transakcja wycofuje
   aktywację; źródło pozostaje nienaruszone.

## Usunięcie z aplikacji głównej i WWW

Zostają usunięte wyłącznie mechanizmy importu pełnego starego profilu:

- trasa `POST /api/settings/import-legacy` oraz jej importy w `web/app.py`;
- pole „Folder starej konfiguracji”, przycisk wczytywania i obsługa żądania w
  `web/static/app.js`;
- akcja/okno wyboru starej konfiguracji w aplikacji Tkinter oraz jej testy.

Pozostałe ustawienia bazy, w tym przełącznik `SQLite`/`legacy`, nie są
zmieniane. Import można uruchomić tylko z osobnego migratora, który działa
poza serwerem WWW i korzysta z lokalnego wyboru folderów.

## Obsługa błędów i bezpieczeństwo danych

- Każdy tryb wymaga jawnego wyboru i potwierdzenia pokazywanych ścieżek.
- Zawsze używany jest jeden wybrany katalog źródłowy; wykrywanie nie łączy
  plików z sąsiednich katalogów ani nie wykonuje skanowania dysku.
- Baza docelowa nigdy nie jest nadpisywana.
- Dane źródłowe są archiwizowane wyłącznie po udanej publikacji i aktywacji.
- Komunikaty postępu oraz raporty nie ujawniają sekretów ani hashy haseł.
- Usunięcie route'u HTTP eliminuje przepływ `source_directory` z żądania do
  operacji plikowych, który powodował pięć alarmów `py/path-injection` CodeQL.

## Testowanie

- Testy istniejącego trybu SQLite pozostają zielone dla poprawnego źródła,
  zajętego celu i błędu aktualizacji ustawień.
- Testy nowego trybu profilu obejmują poprawny profil z SQLite i plikami
  JSON/XLSX, katalog bez importowalnych danych, dane z dwóch katalogów, istniejący cel,
  błąd walidacji oraz błąd aktualizacji ustawień.
- Testy GUI potwierdzają wybór trybu, wymaganie folderu źródłowego tylko w
  trybie LEGACY, poprawne komunikaty potwierdzenia i przekazywanie postępu do
  wątku GUI.
- Testy źródłowe i testy HTTP potwierdzają brak `/api/settings/import-legacy`,
  brak pola oraz przycisku WWW, a także brak akcji importu w aplikacji głównej.
- Przed przekazaniem zmian uruchamiane są testy migratorów, testy importu
  profilu, testy WWW, kompilacja modułów oraz pełne `pytest`.

## Kryteria akceptacji

- Migrator pokazuje dokładnie dwa tryby: konwersję SQLite i import LEGACY.
- Tryb LEGACY nie działa bez wskazania pojedynczego folderu źródłowego i
  wskazanej aplikacji docelowej.
- Udany import wybranego profilu kończy się aktywną SQLite PicSyncra oraz
  archiwum dokładnie użytych źródeł.
- Nieudana migracja nie nadpisuje celu, nie przełącza ustawień i nie usuwa
  źródeł.
- Strona WWW i aplikacja główna nie oferują już importu starej konfiguracji.
- Ustawienia aplikacji nadal pozwalają wybrać `SQLite` albo `legacy`.
