# Migrator SQLite sprzed rebrandingu — projekt

## Cel

Jednorazowo przekształcić wskazaną przez konfigurację głównej aplikacji bazę
`picorgftp_sql.sqlite` w nową bazę `picsyncra.sqlite`. Narzędzie ma działać
poza serwerem WEB, pokazywać postęp, bezpiecznie archiwizować źródłowy zestaw
SQLite po aktywacji i przygotować konfigurację tak, aby następne uruchomienie
głównego EXE otworzyło nową bazę.

## Zakres

- Osobny `PicSyncra-Migrator.exe` z prostym GUI oraz paskiem postępu.
- Odczyt źródła wyłącznie z `local_settings.json` należącego do wskazanego
  katalogu głównej aplikacji.
- Migracja wyłącznie starej SQLite. Nie są importowane ani scalane `xlsx`,
  JSON-y, indeksy plików ani inne pliki legacy.
- Bezpieczne zatrzymanie tylko rozpoznanej instancji PicSyncra/PicOrgFTP z
  wybranego katalogu głównej aplikacji.
- Raport JSON bez sekretów, hashy haseł i danych wrażliwych.

## Poza zakresem

- Przeszukiwanie dysków lub zgadywanie katalogu ze starą bazą.
- Import danych z plików JSON/XLSX do nowej bazy.
- Przełączanie aktywnej bazy z wnętrza działającego backendu WEB.
- Zatrzymywanie ogólnych procesów `python.exe` lub procesów spoza wskazanego
  katalogu aplikacji.

## Wybór źródła i celu

1. Użytkownik uruchamia migrator i wskazuje katalog głównej aplikacji.
   Domyślnie jest to katalog obok migratora, ale użytkownik może go zmienić.
2. Migrator znajduje w tym katalogu plik `local_settings.json` utworzony przez
   główną aplikację i rozwiązuje z niego skonfigurowaną ścieżkę bazy. Dla
   zgodności ze starą konfiguracją, niepusta wartość `database_path` wskazująca
   dokładnie na `picorgftp_sql.sqlite` ma pierwszeństwo także wtedy, gdy stary
   plik ma `database_location_mode=exe_dir`; w pozostałych przypadkach
   stosowana jest standardowa reguła lokalizacji z konfiguracji.
3. Źródło jest poprawne tylko wtedy, gdy istnieje, ma nazwę
   `picorgftp_sql.sqlite` i przechodzi odczytowy `PRAGMA integrity_check`.
   Migrator nie szuka żadnych alternatywnych plików ani katalogów.
4. Przed działaniem GUI wyświetla katalog aplikacji, plik ustawień, pełną
   ścieżkę źródła oraz proponowany cel `picsyncra.sqlite` w tym samym katalogu
   co źródło. Użytkownik musi to potwierdzić.
5. Istniejący plik celu powoduje bezpieczne zatrzymanie przed rozpoczęciem.
   Migrator niczego nie nadpisuje i nie usuwa automatycznie.

## Zatrzymanie aplikacji i blokady

Migrator odnajduje procesy wyłącznie przez plik PID/port głównej aplikacji, a
następnie weryfikuje, że ścieżka wykonywalna procesu należy do wskazanego
katalogu aplikacji oraz że nazwa odpowiada PicSyncra/PicOrgFTP. Próbuje
grzecznego zamknięcia, a następnie — po pokazaniu statusu — może wymusić
zakończenie tylko tak zweryfikowanych PID-ów. Po zakończeniu czeka na
zwolnienie portu i sprawdza, że źródłową bazę można odczytać przez SQLite.

Jeżeli procesu nie da się zweryfikować, zakończyć albo uchwyt bazy pozostaje
otwarty, migrator kończy się czytelnym błędem bez utworzenia celu i bez zmian
w konfiguracji.

## Przepływ migracji

1. Preflight: odczyt ustawień, kontrola źródła i wyświetlenie potwierdzenia.
2. Zatrzymanie wyłącznie zweryfikowanej głównej aplikacji oraz oczekiwanie na
   zwolnienie uchwytów.
3. Utworzenie roboczej kopii źródła przez API SQLite backup w tym samym
   woluminie co cel. Źródło jest otwarte tylko do odczytu.
4. Uruchomienie migracji schematu PicSyncra na roboczej kopii. To zachowuje
   istniejące tabele i dane SQLite; nie wykonuje dodatkowego importu plików.
5. Walidacja: `integrity_check`, brak starych triggerów, obecność nowych
   triggerów, zgodność liczby rekordów w tabelach źródłowych, liczby oraz
   identyfikatorów produktów, a także kont (login, rola, aktywność i hash).
6. Atomowe opublikowanie roboczej bazy jako `picsyncra.sqlite` tylko, jeśli
   cel nadal nie istnieje.
7. Atomowa aktualizacja `local_settings.json`: `data_mode=sqlite`, lokalizacja
   niestandardowa i ścieżka opublikowanej bazy. Pozostałe ustawienia lokalne
   są zachowane.
8. Przeniesienie wyłącznie migrowanego zestawu
   `picorgftp_sql.sqlite`, `-wal` i `-shm` do
   `BACKUP/legacy-import/<data-id>/legacy-source-files`, usunięcie własnego
   katalogu roboczego i pokazanie raportu zakończenia. Główna aplikacja nie
   jest uruchamiana automatycznie; następne jej uruchomienie korzysta z nowej
   SQLite.

Jeśli etap 1–5 zawiedzie, baza docelowa i ustawienia pozostają bez zmian.
Jeśli aktualizacja ustawień zawiedzie po publikacji, migrator usuwa wyłącznie
nowo opublikowany plik celu i raportuje błąd.
Jeśli archiwizacja nie powiedzie się już po aktywacji, nowa baza i ustawienia
pozostają aktywne, a migrator pokazuje ostrzeżenie; pliki tymczasowo zablokowane
są rejestrowane do ponownego przeniesienia po zwolnieniu.

## GUI i postęp

GUI raportuje etapy: wybór konfiguracji, weryfikacja źródła, zatrzymywanie
aplikacji, kopia SQLite, migracja schematu, walidacja tabel i kont, aktywacja
oraz sprzątanie. Dla kopiowania i walidacji produktów pokazuje licznik
przetworzonych rekordów. Kończy krótkim komunikatem sukcesu lub konkretnym
błędem z bezpieczną wskazówką naprawczą.

## Testy akceptacyjne

- Konfiguracja wskazująca nieistniejącą bazę lub plik o innej nazwie jest
  odrzucona bez skanowania katalogów.
- Proces spoza wskazanego katalogu nie może zostać zatrzymany.
- Niedostępna/zablokowana baza nie zmienia celu ani `local_settings.json`.
- Migracja kompletnej legacy SQLite zachowuje liczniki tabel, produkty i
  konta, tworzy bazę schema v17 oraz usuwa stare triggery.
- Istniejący cel blokuje migrację bez nadpisania.
- Po sukcesie odczyt ustawień głównej aplikacji wskazuje `picsyncra.sqlite`.
- Po sukcesie migrowane pliki źródłowe SQLite oraz ich sidecary są przeniesione
  do `BACKUP/legacy-import`; znikają również katalogi robocze utworzone przez
  migrator.

## Sprzątanie danych testowych

Po wdrożeniu może zostać usunięty wyłącznie utworzony podczas wcześniejszych
testów katalog `Generator exe/Recovered profile 2026-09-01 1034`. Katalogi ze
źródłowymi kopiami użytkownika nie są usuwane przez migrator.
