# Wyszukiwanie produktów i start desktopu — specyfikacja

Status: zatwierdzona

Priorytet: P0/P1

Pakiet: 2 z 7

## Cel

Usunąć pełne ładowanie i skanowanie katalogu produktów z gorących ścieżek
wyszukiwania, podpowiedzi, identyfikacji produktu i zapisu pojedynczego
rekordu. Aplikacja desktopowa ma pokazywać interfejs przed zakończeniem
ładowania pełnych list.

Koszt znalezienia produktu ma zależeć od limitu wyniku i użytych indeksów,
a nie od całkowitej liczby produktów.

## Zakres

- bezpośrednie lookupy po `product_id` i EAN;
- serwerowe wyszukiwanie produktów z limitem;
- kontekstowe podpowiedzi pól wykonywane przez data store;
- indeksy wspierające rzeczywiste zapytania;
- anulowanie nieaktualnych requestów autocomplete;
- cache statycznych list i legacy workbooka;
- start desktopu z ładowaniem danych poza wątkiem Tk;
- zachowanie fallbacku dla magazynu Excel.

## Poza zakresem

- zmiana nazw pól produktu lub reguł ich normalizacji;
- zmiana kolejności i semantyki wyników bez testu zgodności;
- usunięcie obsługi Excel;
- zmiana wyglądu formularza;
- wprowadzenie zewnętrznej wyszukiwarki;
- zmiana limitów list wartości i zasad ich użycia;
- migracja danych produktowych do innego systemu.

## Stan obecny

`field_suggestions()` i `search_entries()` korzystają z
`prepare_excel_lists()`, materializują wszystkie rekordy i filtrują je w
Pythonie. `find_entry_by_identity()` może wykonać dwa pełne skany, a zapis
pojedynczego produktu najpierw przechodzi przez tę ścieżkę.

Frontend uruchamia podpowiedzi po krótkim debounce. Kilka szybko wpisanych
znaków może pozostawić równoległe, nieaktualne żądania.

Desktop wywołuje przygotowanie pełnych list w konstruktorze głównej
aplikacji przed rozpoczęciem normalnej obsługi interfejsu.

## Projekt warstwy zapytań

Aktywny data store otrzyma jawne operacje:

- `get_product_by_id(product_id)`;
- `get_product_by_ean(ean)`;
- `search_products(criteria, limit)`;
- `suggest_field_values(field, prefix, context, limit)`;
- `load_list_values()` niezależne od rekordów produktów.

Metody zwracają dotychczasowy kształt rekordu i zachowują wspólną
normalizację wejścia. Limit jest wymagany i ma twardą górną granicę po
stronie store.

### SQLite

SQLite wykonuje selektywne zapytania `WHERE` z `LIMIT`. Kolejność wyniku
odtwarza obecną logikę: trafienia dokładne przed prefiksowymi, a następnie
stabilne sortowanie tekstowe. Indeksy są dodawane wyłącznie po potwierdzeniu
planem `EXPLAIN QUERY PLAN`.

Lookup EAN i ID nie może wywoływać `load_lists()`. Wyszukiwanie po złożonych
polach nie może odczytywać wszystkich rekordów do Pythona.

Podpowiedzi używają `SELECT DISTINCT` oraz ograniczonego kontekstu
poprzednich pól. Puste zapytanie korzysta z cache list wartości zamiast
pełnego skanu produktów.

### Excel

Legacy Excel zachowuje ten sam interfejs, ale utrzymuje pamięciowy,
niemutowalny snapshot workbooka kluczowany:

- kanoniczną ścieżką;
- czasem modyfikacji;
- rozmiarem pliku.

Snapshot jest unieważniany po zapisie przez aplikację oraz po zmianie mtime.
Odczyt nie może utrzymywać otwartego uchwytu pliku. Zapis nadal odbywa się
przez istniejącą bezpieczną ścieżkę i po sukcesie publikuje nowy snapshot.

## API i frontend

Istniejące endpointy zachowują format odpowiedzi. Serwer wymusza limit,
nawet jeśli klient poda większą wartość.

Każde pole autocomplete utrzymuje jeden `AbortController`. Nowe żądanie
anuluje poprzednie. Odpowiedź jest stosowana tylko wtedy, gdy identyfikator
żądania i bieżąca wartość pola nadal pasują.

Podpowiedzi dostępne w bootstrapie lub lokalnym cache są pokazywane od razu.
Request serwerowy jest wykonywany tylko wtedy, gdy może dostarczyć dodatkowe
wyniki.

## Start desktopu

Konstruktor tworzy minimalny, działający interfejs i stan „ładowanie danych”.
Worker przygotowuje:

- listy wartości;
- snapshot produktów wymagany przez funkcje desktopowe;
- pomocnicze mapy lookupów, jeżeli są nadal potrzebne poza data store.

Worker nie może wywoływać metod Tk. Wynik jest publikowany przez
`after(...)` do wątku UI jako kompletny snapshot. Do czasu gotowości akcje,
które wymagają katalogu produktów, są wyłączone lub zwracają czytelny status.

Błąd ładowania nie zamyka okna. Interfejs pokazuje istniejący mechanizm
błędu i pozwala ponowić próbę. Poprzedni kompletny snapshot nie jest
częściowo nadpisywany.

## Spójność zapisu

Po zapisie produktu:

1. transakcja lub zapis workbooka kończy się sukcesem;
2. unieważniony zostaje lookup danego produktu i właściwe podpowiedzi;
3. frontend/desktop otrzymuje aktualny rekord;
4. nie jest wykonywany pełny reload wszystkich produktów, chyba że backend
   Excel nie potrafi bezpiecznie odświeżyć snapshotu przyrostowo.

## Błędy i fallback

- Błąd zapytania SQL zachowuje istniejący sposób raportowania.
- Przekroczony limit nie powoduje odczytu dodatkowych rekordów.
- Anulowane żądanie autocomplete nie jest logowane jako błąd.
- Błąd workera desktopowego nie może dotykać Tk z obcego wątku.
- Jeżeli backend nie implementuje nowej selektywnej operacji, adapter może
  użyć zgodnego fallbacku, ale SQLite nie może z niego korzystać.

## Kompatybilność

- Nie zmieniają się pola produktu, walidacja, normalizacja ani format API.
- Wyniki dokładnych lookupów muszą być identyczne z obecnymi.
- Excel pozostaje wspierany.
- Nie zmienia się konfiguracja użytkownika.
- Nie usuwa się istniejących list bootstrapowych.

## Kryteria akceptacji

1. Lookup po EAN i ID nie wywołuje `load_lists()` ani pełnego skanu tabeli.
2. Wyszukiwanie i podpowiedzi odczytują najwyżej ustalony limit wyników plus
   minimalne dane potrzebne do sortowania.
3. Dla 100 000 produktów zapytanie korzysta z indeksu potwierdzonego przez
   `EXPLAIN QUERY PLAN`.
4. P95 ciepłego lookupu po EAN i ID wynosi poniżej 50 ms na lokalnej bazie
   testowej.
5. P95 wyszukiwania i podpowiedzi z limitem 50 wynosi poniżej 200 ms na
   lokalnej bazie 100 000 produktów.
6. Seria dziesięciu szybkich zmian pola stosuje wyłącznie wynik ostatniego
   requestu.
7. Okno desktopowe rozpoczyna obsługę zdarzeń przed zakończeniem pełnego
   ładowania list.
8. Błąd ładowania danych pozostawia działający interfejs i umożliwia retry.
9. Te same testy kontraktowe przechodzą dla SQLite i legacy Excel tam, gdzie
   operacja jest wspierana.

## Testy i benchmark

Testy store:

- dokładny lookup ID/EAN;
- normalizacja i brak dopasowania;
- kombinacje kryteriów wyszukiwania;
- stabilna kolejność i limit;
- kontekstowe podpowiedzi;
- invalidacja cache po zapisie;
- cache workbooka po mtime.

Testy API/JS:

- zachowanie formatu odpowiedzi;
- wymuszony limit;
- anulowanie poprzedniego requestu;
- ignorowanie spóźnionej odpowiedzi;
- brak requestu, gdy lokalny cache wystarcza.

Testy desktopu:

- minimalny UI przed gotowością danych;
- publikacja snapshotu w wątku Tk;
- blokada akcji zależnych od danych;
- błąd i ponowienie ładowania.

Benchmark porównuje p50/p95 oraz liczbę odczytanych wierszy dla 10 000 i
100 000 produktów. Raport zapisuje osobno zimne i ciepłe wywołania.

### Wynik referencyjny Task 7 — 2026-08-05

Benchmark regresyjny został wykonany na lokalnym SQLite z 100 000 rekordów
wstawionych bez workbooka przez `executemany`, na Windows, Python 3.14.5 i
pytest 9.1.1. Po rozgrzaniu stron bazy 200 naprzemiennych lookupów EAN/ID
osiągnęło p50 1,828 ms i p95 2,163 ms. Sto podpowiedzi nazwy z limitem 50
osiągnęło p50 16,261 ms i p95 19,272 ms; każde wywołanie zwróciło najwyżej
50 wartości.

`EXPLAIN QUERY PLAN` potwierdził następujące ścieżki:

- EAN: `SEARCH product_entries USING INDEX idx_product_entries_ean_key (ean_key=?)`;
- ID: `SEARCH product_entries USING INDEX idx_product_entries_product_id_key (product_id_key=?)`;
- podpowiedź nazwy: `SEARCH product_entries USING INDEX idx_product_entries_name_key (name_key>? AND name_key<?)`.

Żaden z planów nie zawierał `SCAN product_entries`. Wynik jest zapisem
referencyjnym dla testu oznaczonego markerem `performance`; czasy zależą od
lokalnego sprzętu, natomiast budżety regresyjne pozostają na poziomie 50 ms
dla lookupu p95 i 200 ms dla podpowiedzi p95.

## Główne miejsca w kodzie

- `picorgftp_sql/sqlite_store.py`
- `picorgftp_sql/data_store.py`
- `picorgftp_sql/web_data.py`
- `picorgftp_sql/excel_utils.py`
- `picorgftp_sql/app.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/web/static/app.js`
- `tests/test_sqlite_store.py`
- `tests/test_product_fields.py`
- testy webowych endpointów produktów i desktopu

## Zależności

Pakiet powinien korzystać z lifecycle SQLite z pakietu 1. Może być
implementowany niezależnie od uploadu, FTP i integracji zewnętrznych.
