# Review wydajności PicOrgFTP-SQL

Data przeglądu: 2026-07-27

Zakres: cały kod aplikacji desktopowej i webowej, ze szczególnym
uwzględnieniem CPU, operacji dyskowych, SQLite/SQL, FTP, przetwarzania
obrazów, pamięci i współbieżności.

## Podsumowanie

Największy wzrost wydajności powinny dać, w tej kolejności:

1. jednorazowa inicjalizacja SQLite i konfiguracja współbieżności,
2. przeniesienie wyszukiwania produktów z Pythona do zapytań SQL,
3. odciążenie pętli FastAPI podczas uploadu,
4. jednokrotne dekodowanie i kodowanie każdego obrazu,
5. ograniczenie kolejki zadań,
6. cache oraz selektywne listowanie plików FTP,
7. cache miniaturek i ograniczenie częstotliwości zapisów telemetrycznych.

## P0 — największy wpływ

### 1. Inicjalizowanie całego schematu SQLite przy prawie każdej operacji

`self.initialize()` występuje 64 razy w `sqlite_store.py`. Każde wywołanie
otwiera połączenie i wykonuje sprawdzanie schematu, migracji, indeksów oraz
incydentów. Warstwa observability dodatkowo tworzy nową instancję store i
ponownie ją inicjalizuje.

Pliki:

- [sqlite_store.py](picorgftp_sql/sqlite_store.py#L724)
- [sqlite_store.py — initialize](picorgftp_sql/sqlite_store.py#L752)
- [observability.py](picorgftp_sql/observability.py#L86)

Zalecenie:

- jedna instancja `SqliteStore` na rozwiązaną ścieżkę bazy,
- thread-safe `initialize_once()` z blokadą,
- migracje wykonywane tylko przy starcie, restore lub zmianie bazy,
- jawne unieważnianie instancji po zmianie konfiguracji.

### 2. Brak ustawień SQLite dla pracy wielowątkowej

Połączenie ustawia wyłącznie `foreign_keys`. Zapisy logów, jobów,
powiadomień i odczyty SSE mogą się wzajemnie blokować.

Plik: [sqlite_store.py](picorgftp_sql/sqlite_store.py#L727)

Zalecenie:

- `PRAGMA journal_mode=WAL`,
- `PRAGMA busy_timeout`,
- `PRAGMA synchronous=NORMAL`,
- krótkie transakcje,
- osobne połączenie dla każdego wątku,
- fallback dla bazy przechowywanej na udziale sieciowym.

### 3. Wyszukiwanie i podpowiedzi wczytują wszystkie produkty

Każde wyszukiwanie i autocomplete pobiera pełne listy produktów, a następnie
filtruje je w Pythonie. Frontend wysyła zapytania po około 180 ms lub 500 ms.
Istniejące indeksy SQLite nie są w tej ścieżce efektywnie wykorzystywane.

Pliki:

- [web_data.py — field_suggestions](picorgftp_sql/web_data.py#L951)
- [web_data.py — search_entries](picorgftp_sql/web_data.py#L1442)
- [app.js — autocomplete](picorgftp_sql/web/static/app.js#L2046)

Zalecenie:

- `get_product_by_id()` i `get_product_by_ean()`,
- zapytania `WHERE ... LIMIT` dla wyszukiwania,
- `SELECT DISTINCT ... LIMIT` dla podpowiedzi,
- indeksy odpowiadające rzeczywistym warunkom wyszukiwania,
- cache statycznych wartości list,
- anulowanie nieaktualnych requestów autocomplete.

### 4. Upload blokuje główną pętlę FastAPI

Endpointy `async` wykonują synchronicznie zapis pliku, Pillow `verify`,
ponowne kodowanie z `optimize=True` i skan Microsoft Defender przez
`subprocess.run`. Podczas większego uploadu inne requesty mogą czekać.

Pliki:

- [web/app.py — _save_upload](picorgftp_sql/web/app.py#L1515)
- [web/app.py — upload cache](picorgftp_sql/web/app.py#L1575)
- [web/app.py — skan antywirusowy](picorgftp_sql/web/app.py#L1231)

Zalecenie:

- przenieść cały etap walidacji do dedykowanego executora,
- ograniczyć liczbę równoległych zadań semaforem,
- przetwarzać sloty współbieżnie tylko do ustalonego limitu,
- nie uruchamiać Pillow ani Defendera bezpośrednio w event loop.

### 5. Jedno zdjęcie jest dekodowane i kodowane kilka razy

Usuwanie metadanych wykonuje pełne kodowanie, a następnie właściwy pipeline
ponownie otwiera, skaluje i kompresuje obraz. Pętla limitu rozmiaru może
kodować JPEG kilkanaście razy.

Pliki:

- [web/app.py — metadata stripping](picorgftp_sql/web/app.py#L1084)
- [web_workflow.py — zapis obrazu](picorgftp_sql/web_workflow.py#L320)

Zalecenie:

- jeden pipeline: EXIF transpose, walidacja, crop/resize, usunięcie
  metadanych i końcowy zapis,
- wyszukiwanie jakości JPEG metodą binarną,
- jeden współdzielony helper dla wersji desktopowej i webowej,
- redukcja rozmiaru obrazu, jeżeli minimalna jakość nadal przekracza limit.

### 6. Kolejka przetwarzania jest nieograniczona

Executor ma jednego workera, ale `.submit()` nie ma limitu. Wiele uploadów
może pozostawić dużą kolejkę plików tymczasowych. Endpoint synchroniczny
omija tę kolejkę i korzysta ze wspólnego threadpoola.

Pliki:

- [web/app.py — executor](picorgftp_sql/web/app.py#L190)
- [web/app.py — queue](picorgftp_sql/web/app.py#L3872)

Zalecenie:

- jedna wspólna ścieżka przetwarzania,
- ograniczona kolejka,
- limit zadań per użytkownik,
- odpowiedź `429` lub `503` wraz z `Retry-After`,
- pozycja w kolejce i możliwość anulowania,
- automatyczne sprzątanie porzuconych plików.

### 7. FTP listuje cały katalog dla każdego EAN

`MLSD` lub `NLST` pobiera wszystkie nazwy i dopiero później filtruje EAN.
Desktop dodatkowo pobiera kolejno wszystkie zdjęcia produktu.

Pliki:

- [ftp_service.py — listing](picorgftp_sql/services/ftp_service.py#L26)
- [ftp_service.py — lookup EAN](picorgftp_sql/services/ftp_service.py#L69)
- [ftp_service.py — download](picorgftp_sql/services/ftp_service.py#L82)

Zalecenie:

- katalog na każdy EAN albo `NLST EAN_*` z bezpiecznym fallbackiem,
- cache listingu z TTL i unieważnianiem po uploadzie,
- lazy download tylko widocznej lub wybranej miniatury,
- ograniczony równoległy download,
- ponowne używanie połączenia FTP w obrębie jednego workera.

### 8. SSE synchronicznie odpytuje SQLite co sekundę

Każdy podłączony klient wykonuje osobne zapytanie z wnętrza asynchronicznego
generatora. Może to blokować event loop i zwiększa obciążenie liniowo wraz
z liczbą klientów.

Plik: [web/app.py](picorgftp_sql/web/app.py#L5258)

Zalecenie:

- wspólny broker in-memory lub `asyncio.Condition`,
- SQLite tylko do wznowienia strumienia i odtworzenia historii,
- minimalnie: przenieść polling do threadpoola.

## P1 — duże usprawnienia

### 9. Pełny skan katalogów przy każdym uruchomieniu

Cache indeksu jest ładowany, ale zaraz potem i tak uruchamia się pełny
refresh. Należy zastosować TTL, sprawdzanie mtime, watcher albo indeksowanie
przyrostowe.

Plik: [file_index.py](picorgftp_sql/file_index.py#L158)

### 10. Indeks plików jest zapisywany podwójnie

Indeks trafia do SQLite jako pełny JSON i równolegle jako osobne segmenty,
których runtime praktycznie nie wykorzystuje.

Plik: [sqlite_store.py](picorgftp_sql/sqlite_store.py#L3982)

Zalecenie: wybrać jeden format. Jeżeli pozostają segmenty, zapisywać je przez
`executemany` i rzeczywiście wczytywać je leniwie.

### 11. Brak serwerowego cache miniaturek

Każde pierwsze pobranie ponownie uruchamia Pillow i JPEG `optimize`.

Plik: [web/app.py](picorgftp_sql/web/app.py#L1450)

Zalecenie: ograniczony cache LRU lub cache dyskowy, kluczowany ścieżką, mtime,
rozmiarem i parametrami miniatury; dodać singleflight i ETag.

### 12. Zbyt wiele zapisów postępu i telemetrii

Każdy etap joba osobno zapisuje postęp i event do SQLite.

Plik: [web/app.py](picorgftp_sql/web/app.py#L3698)

Zalecenie: buforować i scalać wpisy, zapisując postęp maksymalnie co
250–500 ms. Błędy i stan końcowy nadal zapisywać natychmiast.

### 13. Pimcore nie wykorzystuje HTTP keep-alive

Każde wywołanie GET, POST lub PUT tworzy nowe połączenie i ponosi koszt
TCP/TLS.

Plik: [pimcore_service.py](picorgftp_sql/services/pimcore_service.py#L90)

Zalecenie: trwały `httpx.Client` lub `requests.Session`, zamykany po zmianie
konfiguracji.

### 14. Zapytania szablonów SQL i tłumaczenia wykonywane są kolejno

Każde mapowanie może otworzyć nowe połączenie SQL lub nowe połączenie HTTP.

Pliki:

- [web_data.py](picorgftp_sql/web_data.py#L2112)
- [pimcore_sql_service.py](picorgftp_sql/services/pimcore_sql_service.py#L206)

Zalecenie:

- jedno połączenie na profil podczas renderowania,
- grupowanie niezależnych zapytań,
- cache tłumaczeń po tekście, języku, providerze i wersji konfiguracji,
- kontrolowana równoległość tylko dla niezależnych mapowań.

### 15. Osobny UPDATE SQL dla każdego slotu zdjęcia

Aktualizacja zdjęć wykonuje osobne zapytanie dla każdej kolumny.

Plik: [web/app.py](picorgftp_sql/web/app.py#L1953)

Zalecenie: zbudować jeden parametryzowany `UPDATE` dla wszystkich kolumn.
Sprawdzanie istnienia rekordu można zastąpić kontrolą `rowcount`.

### 16. Konfiguracja storage jest wielokrotnie odczytywana z JSON

Pobranie aktywnego store ponownie ładuje ustawienia bootstrap.

Pliki:

- [storage_settings.py](picorgftp_sql/storage_settings.py#L64)
- [data_store.py](picorgftp_sql/data_store.py#L309)

Zalecenie: cache według mtime lub numeru generacji oraz jawne unieważnianie
po zapisie konfiguracji.

### 17. Desktop ładuje pełne listy przed pokazaniem interfejsu

Minimalny interfejs powinien wystartować natychmiast, a dane powinny zostać
wczytane w workerze i przekazane do wątku Tk jako gotowy snapshot.

W trybie Excel należy cache'ować dane workbooka według mtime. SQLite
powinien być preferowanym backendem, a Excel formatem importu i eksportu.

### 18. Pliki tymczasowe FTP nie są konsekwentnie sprzątane

Katalogi podglądu mogą pozostawać na dysku po zamknięciu aplikacji lub
zmianie produktu.

Pliki:

- [app.py — destroy](picorgftp_sql/app.py#L454)
- [app.py — download FTP](picorgftp_sql/app.py#L6273)

Zalecenie: cleanup przy zamknięciu, okresowe usuwanie starych katalogów
i anulowanie nieaktualnego downloadu po zmianie request ID.

## P2 — optymalizacje uzupełniające

### 19. Worker powiadomień budzi się co dwie sekundy

Nawet bez pracy wykonywanych jest kilka operacji bazodanowych.

Plik: [notification_service.py](picorgftp_sql/notification_service.py#L1398)

Zalecenie: wybudzanie eventem lub na podstawie czasu najbliższego zadania,
z dłuższym pollingiem awaryjnym.

### 20. Frontend posiada kilka niezależnych pollerów

Health, kolejka, indeks, logi i aktywni użytkownicy są pobierani niezależnie.

Zalecenie: jeden lekki endpoint statusowy albo wspólny SSE/WebSocket;
odpytywać wyłącznie aktywne funkcje.

### 21. Lista aktywnych klientów zapisuje pełny JSON podczas trzymania blokady

Plik: [web/app.py](picorgftp_sql/web/app.py#L4133)

Zalecenie: wykonać snapshot pod blokadą, a zapis na dysk poza blokadą lub
w tle.

### 22. Duży bundle JavaScript

`app.js` ma około 479 KB i ponad 12 tysięcy linii.

Zalecenie:

- minifikacja wersji produkcyjnej,
- gzip lub Brotli,
- długie cache dla wersjonowanych assetów,
- lazy loading ekranów administracyjnych i observability.

### 23. Zdublowane lub nieużywane implementacje indeksowania

Usunięcie martwego kodu nie da dużego bezpośredniego przyspieszenia, ale
uprości profilowanie i zmniejszy ryzyko optymalizowania niewykorzystywanej
ścieżki.

### 24. Bardzo duże pliki modułów

`app.py`, `web/app.py` i `app.js` są monolitami. Sam podział nie przyspieszy
runtime, ale umożliwi dokładniejsze benchmarki, testowanie i cache'owanie
poszczególnych funkcji.

## Braki w testach wydajności

Obecny smoke test mierzy tylko 2500 prostych helperów oraz 120 wywołań
`/api/health`. Nie obejmuje rzeczywistych zdjęć, dużej bazy produktów,
FTP, SQL, SSE ani wielu użytkowników.

Plik: [test_ci_performance_smoke.py](tests/test_ci_performance_smoke.py#L30)

Należy dodać benchmarki:

- wyszukiwania i podpowiedzi dla 10 tys. i 100 tys. produktów,
- listowania FTP zawierającego 100 tys. plików,
- uploadu i przetwarzania wszystkich 26 slotów,
- równoległych klientów oraz blokad SQLite,
- startu aplikacji z dużym drzewem zdjęć,
- SQL i Pimcore z realistycznym opóźnieniem sieci,
- zużycia pamięci i miejsca przez pliki tymczasowe,
- p50 i p95 czasu odpowiedzi dla głównych endpointów.

## Elementy już zrobione prawidłowo

- Historia ma indeks SQLite i leniwe pobieranie szczegółów; wcześniejszy
  problem ładowania pełnych rekordów został już ograniczony.
- Wiele ciężkich operacji webowych jest już przeniesionych do threadpoola.
- Desktop wykorzystuje worker do wyszukiwania istniejących zdjęć.
- Odczyty informacji SQL o obecności produktów są grupowane.
- Pollery frontendu ograniczają częstotliwość działania w ukrytej karcie.
- Adresy miniaturek są wersjonowane, dzięki czemu działa cache przeglądarki.

## Rekomendowana kolejność wdrożenia

1. Cache store, jednorazowe `initialize()` i konfiguracja SQLite.
2. Bezpośrednie zapytania SQL dla produktów i podpowiedzi.
3. Przeniesienie uploadu poza event loop.
4. Jeden pipeline przetwarzania obrazu.
5. Ograniczona, wspólna kolejka zadań.
6. Selektywne listowanie FTP, cache i lazy download.
7. Cache miniaturek oraz ograniczenie zapisów postępu.
8. Pooling i grupowanie operacji SQL, Pimcore i tłumaczeń.
9. Przyrostowy indeks plików.
10. Konsolidacja pollingu i optymalizacja frontendu.

## Status weryfikacji

- `node --check picorgftp_sql/web/static/app.js`: zakończone kodem 0,
- `python -m compileall -q picorgftp_sql tests`: zakończone kodem 0,
- `git diff --check`: zakończone kodem 0.

Pełny zestaw `pytest` nie został uruchomiony, ponieważ lokalne interpretery
nie mają modułu `pytest`, FastAPI ani pozostałych zależności runtime, a
widoczny `pytest.exe` wskazuje na usuniętą instalację Pythona. Wnioski
wydajnościowe w tym dokumencie są zatem przede wszystkim wynikiem pełnego
przeglądu statycznego kodu i jego ścieżek wykonania.
