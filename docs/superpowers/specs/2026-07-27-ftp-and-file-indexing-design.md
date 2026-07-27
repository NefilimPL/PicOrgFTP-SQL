# FTP i indeks plików — specyfikacja

Status: zatwierdzona

Priorytet: P0/P1

Pakiet: 4 z 7

## Cel

Ograniczyć częstotliwość pełnego listowania zdalnego katalogu FTP i pełnego
skanowania lokalnego drzewa zdjęć. Usunąć podwójny zapis indeksu, zapewnić
sprzątanie plików tymczasowych i pozostawić jedną aktywnie używaną
implementację indeksowania.

## Nienegocjowalne ograniczenia

- Zdalny katalog FTP pozostaje płaski.
- Nie powstają subfoldery per EAN ani żadna migracja plików FTP.
- Istniejące nazwy plików i reguły slotów nie zmieniają się.
- Nie wolno uznać braku obsługi wildcard przez serwer FTP za brak zdjęć.
- Manualne pełne odświeżenie pozostaje dostępne.
- Cache nie może ukrywać wyniku własnego uploadu lub usunięcia aplikacji.
- Cleanup usuwa tylko rozpoznane pliki i katalogi tymczasowe PicOrgFTP-SQL.

## Zakres

- selektywne listowanie FTP z bezpiecznym fallbackiem;
- cache nazw zdalnych plików i singleflight pełnego listingu;
- invalidacja cache po uploadzie i usunięciu;
- start z lokalnym cache indeksu bez automatycznego pełnego skanu;
- odświeżanie indeksu na podstawie świeżości i fingerprintów katalogów;
- jeden format trwałego indeksu;
- przyrostowy zapis zmienionych segmentów;
- cleanup plików tymczasowych FTP;
- anulowanie nieaktualnego pobierania podglądu między etapami;
- usunięcie martwych implementacji indeksowania po potwierdzeniu użycia.

## Poza zakresem

- zmiana serwera lub protokołu FTP;
- SFTP, WebDAV i zewnętrzny katalog plików;
- zmiana treści lub formatu zdjęć;
- cache wygenerowanych miniaturek HTTP;
- monitoring filesystemu wymagający nowej usługi systemowej;
- zmiana lokalizacji katalogu zdjęć użytkownika.

## Stan obecny

Lookup jednego EAN otwiera połączenie, pobiera wszystkie nazwy przez `MLSD`
albo `NLST`, a następnie filtruje je lokalnie. Przy dużym płaskim katalogu
koszt każdego lookupu rośnie wraz z całkowitą liczbą plików.

Lokalny indeks jest ładowany z cache przy starcie, ale aplikacja uruchamia
zaraz potem pełny refresh. Cache trafia do SQLite jako pełny JSON i
jednocześnie jako segmenty. Runtime opiera się głównie na pełnym snapshotcie,
więc drugi zapis zwiększa koszt bez proporcjonalnej korzyści.

Podglądy FTP korzystają z katalogów tymczasowych, które nie są konsekwentnie
usuwane po zmianie produktu albo zamknięciu aplikacji.

## Projekt FTP

### Strategia lookupu

Lookup EAN stosuje kolejno:

1. świeży cache nazw dla aktualnej konfiguracji FTP;
2. selektywne `NLST` z wzorcami wynikającymi z istniejącej konwencji nazw;
3. pełny `MLSD`, a następnie `NLST`, jeżeli selektywne listowanie nie jest
   wspierane lub wynik nie jest wiarygodny.

Obsługa wildcard zależy od serwera. Błąd typu „syntax not supported” albo
„invalid pattern” oznacza przejście do pełnego listingu. Pusta odpowiedź na
selektywne zapytanie jest uznawana za wiarygodną tylko dla serwera, dla
którego capability zostało wcześniej pozytywnie potwierdzone.

Nie są wykonywane komendy tworzenia ani zmiany katalogów poza istniejącym
`cwd` skonfigurowanej ścieżki.

### Cache zdalnych nazw

Cache jest kluczowany fingerprintem niesekretnej konfiguracji:

- host;
- port;
- użytkownik po zredagowaniu do klucza technicznego;
- ścieżka;
- tryb pasywny.

Hasło nigdy nie jest częścią jawnego klucza ani logu. Cache zawiera nazwy
plików oraz, jeśli `MLSD` je dostarcza, `size` i `modify`.

Domyślny TTL pełnego snapshotu wynosi 60 sekund i jest konfigurowalny.
Równoległe żądania odświeżenia tej samej lokalizacji korzystają z
singleflight: jedno wykonuje listing, pozostałe czekają na wynik.

Po udanym uploadzie lub usunięciu aplikacja aktualizuje cache przyrostowo.
Po częściowym błędzie synchronizacji cały snapshot jest oznaczany jako
niepewny i następny lookup wykonuje odświeżenie.

Cache żyje tylko w procesie. Trwały cache FTP nie jest wprowadzany w tej
iteracji, aby nie zwracać nieaktualnego stanu po restarcie.

## Projekt lokalnego indeksu

### Start

Przy starcie aplikacja:

1. wczytuje ostatni kompletny indeks;
2. publikuje go natychmiast jako snapshot;
3. sprawdza ścieżkę root, wersję formatu i czas utworzenia;
4. uruchamia refresh tylko wtedy, gdy indeks jest nieobecny, niezgodny,
   starszy niż domyślny TTL 15 minut albo użytkownik wymusi refresh.

Stary, ale poprawny snapshot pozostaje dostępny w czasie odświeżania. Błąd
refreshu nie zastępuje go pustym indeksem.

### Segmenty jako jedyne trwałe źródło

SQLite przechowuje:

- metadane generacji indeksu;
- segmenty wpisów pod stabilnym kluczem katalogu/produktu;
- fingerprint każdego segmentu;
- status kompletności generacji.

Pełny blob JSON przestaje być zapisywany po migracji. Istniejący blob jest
odczytany jeden raz, zamieniony na segmenty w atomowej generacji, a następnie
usunięty dopiero po potwierdzeniu kompletności.

Ładowanie snapshotu może zrekonstruować pamięciową mapę z segmentów, ale na
dysku istnieje tylko jedna kopia danych indeksu.

### Odświeżanie przyrostowe

Każdy segment ma fingerprint oparty na:

- kanonicznej ścieżce;
- mtime katalogu;
- liczbie bezpośrednich wpisów;
- wersji reguł parsowania nazw.

Nie zmieniony segment jest kopiowany logicznie do nowej generacji bez
ponownego parsowania wszystkich plików. Zmienione i nowe segmenty są
skanowane ponownie, a usunięte są usuwane z nowej generacji.

Zapis używa `executemany` lub wielowierszowego upsertu. Nowa generacja staje
się aktywna dopiero po pełnym sukcesie. Przerwany refresh pozostawia
poprzednią generację.

Jeżeli filesystem nie dostarcza wiarygodnych mtime, konfiguracja lub wykryta
niespójność wymusza pełny skan. Poprawność ma pierwszeństwo przed
przyrostowością.

## Pliki tymczasowe FTP

Każdy request podglądu otrzymuje osobny katalog z:

- rozpoznawalnym prefiksem;
- identyfikatorem requestu;
- znacznikiem aktywności.

Zmiana produktu anuluje stary request między pobraniami plików. Jego katalog
jest usuwany po zwolnieniu używanych uchwytów. Zamknięcie desktopu czyści
aktywne katalogi bieżącej sesji.

Przy starcie okresowy cleanup może usunąć wyłącznie katalogi o dokładnym
prefiksie aplikacji, starsze niż 24 godziny i nieoznaczone jako aktywne.
Każdy cel jest kanonizowany i sprawdzany jako dziecko systemowego katalogu
tymczasowego.

## Usunięcie duplikatów

Przed usunięciem implementacji `file_index_service.py`,
`directory_index_service.py` lub innych kandydatów należy potwierdzić przez:

- wyszukiwanie importów w kodzie i testach;
- analizę entrypointów builda;
- uruchomienie pakietu testów;
- sprawdzenie dynamicznych importów.

Kod nadal używany zostaje przeniesiony do jednej kanonicznej implementacji.
Martwy kod jest usuwany razem z testami odnoszącymi się wyłącznie do
nieaktywnej ścieżki.

## Błędy i diagnostyka

- Błąd selektywnego FTP przechodzi do pełnego listingu.
- Błąd pełnego listingu zachowuje dotychczasowy błąd użytkownika.
- Niekompletny indeks nie staje się aktywny.
- Stary poprawny snapshot pozostaje dostępny po błędzie refreshu.
- Cleanup rejestruje odmowę usunięcia podejrzanej ścieżki, ale jej nie usuwa.
- Logi nie zawierają hasła FTP ani pełnych danych uwierzytelniających.

## Kryteria akceptacji

1. Żaden kod nie tworzy subfolderów FTP dla EAN.
2. Dwa lookupy w czasie TTL wykonują najwyżej jeden pełny listing.
3. Równoległe lookupy wymagające refreshu wykonują jeden pełny listing.
4. Upload i usunięcie są widoczne w następnym lookupie bez oczekiwania na TTL.
5. Serwer bez wildcard działa przez bezpieczny fallback.
6. Świeży lokalny indeks nie uruchamia pełnego skanu przy starcie.
7. Zmiana jednego segmentu nie powoduje ponownego parsowania wszystkich
   niezmienionych segmentów.
8. SQLite nie przechowuje jednocześnie pełnego bloba i równoważnych segmentów.
9. Przerwany refresh pozostawia poprzedni kompletny indeks.
10. Pliki tymczasowe bieżącego requestu i stare katalogi są bezpiecznie
    sprzątane.
11. Po usunięciu duplikatów nie pozostają importy do nieistniejących modułów.

## Testy i benchmark

Testy FTP:

- selektywne `NLST`, brak wildcard i fallback;
- pusta wiarygodna i niewiarygodna odpowiedź;
- TTL, singleflight i invalidacja;
- częściowy błąd uploadu;
- brak komend tworzących katalog.

Testy indeksu:

- świeży cache i start bez skanu;
- stary cache i refresh w tle;
- jeden zmieniony, nowy i usunięty segment;
- atomowe generacje;
- migracja bloba;
- fallback pełnego skanu;
- `executemany`.

Benchmark obejmuje:

- FTP z 100 000 nazw i serię lookupów EAN;
- start z aktualnym indeksem;
- zmianę 1% segmentów w dużym drzewie;
- liczbę wywołań FTP, operacji filesystem i zapisanych bajtów SQLite.

## Główne miejsca w kodzie

- `picorgftp_sql/services/ftp_service.py`
- `picorgftp_sql/file_index.py`
- `picorgftp_sql/services/file_index_service.py`
- `picorgftp_sql/services/directory_index_service.py`
- `picorgftp_sql/sqlite_store.py`
- `picorgftp_sql/web_data.py`
- `picorgftp_sql/app.py`
- `tests/test_ftp_service.py`
- `tests/test_file_index.py`
- `tests/test_app_performance_helpers.py`

## Zależności

Pakiet powinien korzystać z lifecycle SQLite z pakietu 1. Zmiany FTP i
lokalnego indeksu można dostarczać w osobnych commitach, ale wspólna
specyfikacja zapewnia jedną politykę cache i invalidacji plików.
