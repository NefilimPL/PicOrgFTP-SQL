# Skalowalna historia zmian — projekt

## Cel

Historia ma pozostać responsywna przy tysiącach wpisów. Przejście między stronami
ma odczytywać tylko lekkie podsumowania, a otwarcie EAN tylko jedną stronę pełnych
zmian. Żądania historii nie mogą blokować pomiaru zdrowia backendu na kilka sekund.

## Problem

W trybie SQLite tabela `web_history` zawiera tylko `id`, `created_at` i pełny
`payload_json`. Obecne `load_history()` odczytuje i dekoduje każdy JSON. Zarówno
`history_snapshot()`, jak i `history_group_snapshot()` wykonują ten odczyt przed
wybraniem strony lub EAN. Także zapis nowego wpisu najpierw odczytuje całą historię,
a następnie zapisuje ją ponownie. Koszt rośnie wraz z rozmiarem szczegółów zmian,
nie tylko liczbą rekordów.

## Decyzja

W SQLite zostanie dodana utrzymywana tabela indeksu `web_history_index`. Pełny JSON
pozostaje źródłem szczegółów, a indeks przechowuje wyłącznie wartości potrzebne do
listy, filtrów i kolejności:

- `id` — klucz rekordu historii;
- `ean`, `username`, `product_id`, `action`, `summary`, `created_at`;
- `entry_json` — zredagowane, lekkie dane produktu do wiersza listy;
- `search_text` — zredagowana normalizowana projekcja obecnego wyszukiwania.

Indeksy SQLite obejmą co najmniej EAN z czasem, użytkownika z czasem i czas
utworzenia. Wszystkie wartości indeksu są tworzone po redakcji danych, więc indeks
nie wprowadza dodatkowej kopii sekretów.

## Przepływ danych

```text
zapis historii
  -> redakcja pełnego rekordu
  -> web_history.payload_json
  -> web_history_index (lekka projekcja)

lista historii
  -> web_history_index: filtr, grupowanie EAN, LIMIT/OFFSET
  -> maksymalnie 50 podsumowań bez dekodowania payload_json

szczegóły EAN
  -> web_history_index: filtr, COUNT, LIMIT/OFFSET identyfikatorów
  -> web_history: tylko payload_json bieżącej strony, domyślnie 25 rekordów
```

`history_snapshot()` będzie delegować do zapytania indeksowego w trybie SQLite.
Zachowa obecny kontrakt podsumowań (`ean`, `latest_ts`, `change_count`, `entry`),
filtry, numery stron i listę użytkowników. W trybie starego pliku JSON pozostanie
zgodna ścieżka awaryjna.

`history_group_snapshot()` otrzyma `page` i `page_size`; zwróci `items` tylko dla
wybranej strony oraz `total_items`, `total_pages`, `page` i `page_size`.
`GET /api/history/details` przekaże te parametry. Brak pasującego EAN nadal zwraca
404, a dostęp nadal wymaga zalogowania.

Przy kliknięciu EAN interfejs pobierze pierwsze 25 szczegółów. Modal otrzyma
informację o stronie oraz przyciski poprzednia/następna; oba kierują nowe,
anulowalne żądanie szczegółów. Nie będzie pobierania ani renderowania wszystkich
zmian jednego EAN naraz.

## Migracja i spójność

`SqliteStore.initialize()` utworzy tabelę oraz indeksy. Dla istniejącej bazy, gdy
indeks nie istnieje albo jego liczba rekordów różni się od `web_history`, wykona
jednorazową odbudowę indeksu w transakcji z już zredagowanych payloadów. To może
wydłużyć tylko pierwszy start po aktualizacji, nie otwarcie modala historii.

`append_history()` zapisze rekord i jego indeks w tej samej transakcji. Zachowa
limit 2000 wpisów przez usunięcie najstarszych rekordów i odpowiadających im wierszy
indeksu. `save_history()` odbuduje oba zbiory atomowo. `record_history()` w trybie
SQLite użyje `append_history()` bez poprzedniego pełnego odczytu historii.

Każdy wspierany zapis historii aktualizuje indeks w tej samej transakcji; kontrola
liczby wierszy podczas startu jest wyłącznie mechanizmem odzyskania indeksu
brakującego lub przerwanego. Projekcja wyszukiwania używa `casefold()`, zgodnie z
dotychczasowym filtrem historii, a nie słabszego `lower()`.

## Obsługa błędów i zgodność

- Redakcja jest wykonywana przed zapisem payloadu i projekcji indeksu.
- Filtr użytkownika oraz wyszukiwanie mają tę samą semantykę jak obecnie.
- Brak lub niespójność indeksu zostaje naprawiona przy inicjalizacji, zamiast
  zwracać niepełne dane.
- Stary magazyn JSON pozostaje funkcjonalny bez migracji danych.
- Automatyczne pobranie listy po otwarciu modala oraz anulowanie przestarzałych
  żądań zostają zachowane.

## Weryfikacja

Testy pokryją:

1. jednorazowe zbudowanie indeksu dla istniejącej bazy i brak pełnego odczytu JSON
   podczas kolejnych stron listy;
2. filtrowanie, grupowanie, kolejność i stronicowanie listy przez SQLite;
3. odczyt i dekodowanie wyłącznie `page_size` pełnych payloadów dla szczegółów EAN;
4. atomową synchronizację indeksu przy dopisaniu, pełnym zapisie oraz retencji;
5. kontrakt HTTP dodatkowych pól i parametrów strony szczegółów;
6. UI: stronicowanie szczegółów, anulowanie żądań i brak regresji listy.

Próba wydajności na syntetycznej historii z co najmniej 2000 rozbudowanych rekordów
porówna rozmiar odpowiedzi i czas dla listy oraz jednej strony szczegółów. Kryterium
jest niezależność kosztu pojedynczej strony od rozmiaru pełnych payloadów pozostałych
rekordów.
