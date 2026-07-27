# Podział dużych modułów — specyfikacja

Status: do przeglądu

Priorytet: P2

Pakiet: 7 z 7

## Cel

Zmniejszyć rozmiar i liczbę odpowiedzialności największych modułów bez
jednorazowego przepisywania aplikacji. Refaktoryzacja ma objąć wyłącznie
obszary dotykane przez sześć wcześniejszych pakietów wydajnościowych.

## Zasada nadrzędna

Podział modułów jest ostatnim pakietem albo jest wykonywany małymi krokami
bezpośrednio przy implementacji danego pakietu. Nie powstaje osobny
„big-bang rewrite”. Każde wydzielenie musi mieć test kontraktowy przed
przeniesieniem i nie może zmieniać zachowania użytkownika.

## Zakres

- wydzielenie lifecycle SQLite i selektywnych query services;
- wydzielenie upload staging, image pipeline i kolejki;
- wydzielenie runtime statusu oraz persistence aktywnych klientów;
- wydzielenie desktopowego ładowania danych i obsługi temp FTP;
- podział odpowiedzialności frontendu dotyczących autocomplete, statusu i
  kolejki;
- usunięcie przejściowych shimów po migracji wszystkich call sites;
- testy importów, startu aplikacji i pakowania EXE.

## Poza zakresem

- zmiana frameworka Tk, FastAPI albo sposobu budowania aplikacji;
- wdrożenie bundlera JavaScript;
- reorganizacja modułów niezwiązanych z zatwierdzonymi optymalizacjami;
- zmiana publicznych endpointów lub zachowania formularzy;
- masowa zmiana nazw;
- mechaniczne dzielenie plików bez wyraźnej granicy odpowiedzialności;
- zmiana architektury całej aplikacji na mikroserwisy.

## Docelowe granice Python

Nazwy są kierunkiem i mogą zostać dostosowane do istniejącej konwencji, ale
odpowiedzialności pozostają rozłączne.

### Persistence

- `sqlite_store.py` pozostaje niskopoziomym repozytorium i schematem;
- lifecycle/cache aktywnego store trafia do warstwy data store;
- selektywne zapytania produktów mają osobny, testowalny interfejs;
- moduły web i desktop nie konfigurują PRAGMA bezpośrednio.

### Web

Z `web/app.py` są wydzielane:

- `upload_staging.py` — odbiór, walidacja i AV;
- `process_queue.py` — kolejka, stany, anulowanie i limity;
- `runtime_status.py` — agregacja lekkich statusów;
- `active_clients.py` — rejestr i asynchroniczny writer.

`web/app.py` pozostaje composition root: tworzy zależności, rejestruje
endpointy i mapuje wyjątki na HTTP. Nie zawiera implementacji ciężkich
operacji.

### Desktop

Z `app.py` są wydzielane:

- `desktop_data_loader.py` — przygotowanie snapshotu danych poza Tk;
- `desktop_ftp_preview.py` — request lifecycle, anulowanie i temp cleanup;
- wspólny image pipeline zamiast duplikowania zapisu obrazów.

Widżety i aktualizacje Tk pozostają w głównym wątku oraz w warstwie UI.

## Docelowe granice JavaScript

Projekt nie wprowadza bundlera. Nowe moduły są zwykłymi statycznymi plikami
ładowanymi w deterministycznej kolejności i publikują minimalne API pod
jedną przestrzenią `window.PicOrg`.

Planowane obszary:

- `autocomplete.js` — debounce, AbortController, cache i render wyników;
- `runtime-status.js` — jeden scheduler statusu;
- `process-jobs.js` — widok kolejki i statusy jobów.

Każdy plik używa IIFE i eksportuje tylko funkcje potrzebne orchestratorowi.
Nie dodajemy nowych niezależnych globali. `app.js` pozostaje orchestratorom
startu i kodu niewydzielonego.

Dodatkowe skrypty są serwowane z tego samego katalogu statycznego i ładowane
przed `app.js`, dlatego pozostają zgodne z obecną polityką `script-src
'self'`. Każdy plik otrzymuje ten sam mechanizm wersjonowania cache co
obecny bundle. Brak poprawnego załadowania modułu jest widocznym błędem
startu frontendu, a nie cichym przejściem do częściowo działającego UI.

## Strategia migracji

Każde wydzielenie przebiega osobno:

1. test kontraktowy obecnego zachowania;
2. nowy moduł z minimalnym API;
3. przeniesienie jednej odpowiedzialności bez zmian logicznych;
4. przełączenie wszystkich call sites;
5. testy jednostkowe i integracyjne;
6. kontrola importów i startu;
7. usunięcie shima dopiero po braku użyć.

Nie należy jednocześnie refaktoryzować kodu i zmieniać jego algorytmu w tym
samym commitcie. Optymalizacja powinna powstać przed albo po czystym
wydzieleniu, co ułatwia review i rollback.

## Reguły zależności

- moduły usługowe nie importują `web.app` ani głównej klasy Tk;
- composition root może importować usługi, ale usługi nie importują root;
- kod współdzielony web/desktop nie zna FastAPI ani Tk;
- moduł JavaScript nie wykonuje requestów przed jawnym `start()`;
- zależności systemowe, zegar i executory są wstrzykiwane w testowalnej
  formie tam, gdzie wpływają na współbieżność.

## Błędy i rollback

- Każdy etap jest osobnym commitem możliwym do wycofania.
- Stary import może mieć krótko żyjący shim, ale shim ma termin usunięcia w
  tym samym pakiecie.
- Błąd importu nie może być ukrywany szerokim `except`.
- Build EXE i uruchomienie zasobów statycznych są testowane po zmianie
  struktury plików.
- Nie usuwa się starego kodu przed potwierdzeniem wszystkich call sites.

## Kryteria akceptacji

1. Każdy nowy moduł ma jedną opisaną odpowiedzialność i minimalne API.
2. Nie powstaje cykl importów.
3. Usługi nie importują composition root.
4. Wszystkie endpointy i zachowanie desktopu przechodzą testy kontraktowe.
5. Build uwzględnia nowe moduły Python i statyczne pliki JS.
6. `app.js` nie otrzymuje nowych niezależnych globali poza `window.PicOrg`.
7. Każdy usunięty shim ma potwierdzony brak importów i odwołań.
8. Refaktoryzacyjny commit nie zmienia wyniku benchmarku poza szumem
   pomiarowym 5%.
9. Zakres zmian odpowiada wyłącznie sześciu zatwierdzonym pakietom.

## Testy

- import smoke wszystkich nowych modułów;
- start FastAPI i rejestracja endpointów;
- headless start desktopu;
- test composition root z mockowanymi usługami;
- test assetów i kolejności skryptów;
- `node --check` dla każdego pliku JavaScript;
- test pakowania/manifestu nowych plików;
- wyszukiwanie martwych importów;
- pełny zestaw regresji po każdym wydzieleniu.

## Główne miejsca w kodzie

- `picorgftp_sql/app.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/web/static/app.js`
- `picorgftp_sql/sqlite_store.py`
- `picorgftp_sql/data_store.py`
- `picorgftp_sql/web_data.py`
- konfiguracja builda i zasobów statycznych
- testy importów, web, desktopu i JavaScript

## Zależności i kolejność

Pakiet jest realizowany po ustabilizowaniu granic z pakietów 1–6 albo jako
małe, czyste wydzielenia bezpośrednio przed daną optymalizacją. Końcowe
usuwanie shimów i porządkowanie composition root następuje jako ostatni etap
całego programu wydajnościowego.
