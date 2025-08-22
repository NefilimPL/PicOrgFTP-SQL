# PicOrgFTP-SQL
Python Picture orgraniser with ability to send to FTP and SQL

## Działanie

Skrypt udostępnia graficzny interfejs, w którym wprowadza się nazwę, typ,
model i kolory produktu. Do formularza można przeciągać zdjęcia metodą
drag-and-drop. Po uzupełnieniu wymaganych pól i zatwierdzeniu:

1. Pliki są kopiowane do katalogu `_ZDJECIA PRZEROBIONE_` i układane według
   struktury `NAZWA/TYP/MODEL/KOLOR1_KOLOR2_KOLOR3/DODATEK`.
2. Zdjęcia są optymalizowane, konwertowane do JPEG/PNG i otrzymują nazwę
   `EAN_slot.ext`.
3. Nowe pliki są wysyłane na serwer FTP, a stare wersje o tym samym EAN mogą
   zostać usunięte.
4. Jeżeli włączono `enable_sql_update`, wykonywane jest zapytanie SQL, które
   aktualizuje ścieżki obrazów w bazie `sql` lub `mysql`.

Działania programu są zapisywane w `changes_log.txt`, a ewentualne błędy w
`error_log.txt`. Przy pierwszym uruchomieniu tworzony jest plik `config.json`
z ustawieniami połączeń.

## Konfiguracja

Domyślnie plik `config.json` zapisywany jest w katalogu `Pictures` w folderze
użytkownika. Aby na stałe wskazać inną lokalizację startową, ustaw ścieżkę w
stałej `BASE_DIR_OVERRIDE` na początku pliku `PicOrgFTP-SQL`.

Pierwsze linie pliku zawierają sekcję konfiguracyjną ułatwiającą dostosowanie
skryptu do własnych potrzeb. Można tam zmienić m.in.:

- `BASE_DIR_OVERRIDE` – katalog startowy do zapisu danych.
- `APP_SECRET` – klucz używany do szyfrowania danych konfiguracji.
- `PORT` – domyślny port serwera FTP.
- `SQL_UPDATE_TEMPLATE` – domyślne zapytanie SQL aktualizujące ścieżkę
  obrazów w bazie.
- `DEFAULT_CONFIG` – początkowe dane logowania FTP/SQL/MySQL oraz zapytanie
  SQL wykorzystywane przy aktualizacji ścieżek. Wszystkie pola tekstowe używają
  surowych łańcuchów `r""`, dzięki czemu nie trzeba uciekać znaków specjalnych.
  Sekcje `ftp`, `sql` i `mysql` zawierają odpowiednio pola `host`/`server`,
  `port`, `user`, `pass` (oraz `path` dla FTP). Pozostałe klucze to `db_type`,
  `sql_query` i `enable_sql_update`.

Zmiana tych wartości przed uruchomieniem skryptu umożliwia szybkie dostosowanie
działania programu do własnego środowiska.
