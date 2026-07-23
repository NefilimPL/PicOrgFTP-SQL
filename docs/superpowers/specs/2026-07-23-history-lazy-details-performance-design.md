# Wydajna historia zmian — projekt

**Data:** 2026-07-23

**Status:** zatwierdzony w rozmowie

## Cel

Otwarcie lub odświeżenie okna `Historia zmian` ma pobierać i renderować
wyłącznie lekką stronę podsumowań. Pełne dane zmian oraz czasy operacji są
pobierane dopiero po wybraniu konkretnego EAN. Dzięki temu historia nie
zajmuje pętli aplikacji, a cykliczny pomiar zdrowia backendu zachowuje
miarodajny czas odpowiedzi.

## Przyczyna

Obecna ścieżka `GET /api/history` przyjmuje limit 1000 rekordów i zwraca
pełne elementy każdej grupy EAN na bieżącej stronie. Gdy wiele zdarzeń należy
do jednego EAN, pojedyncza grupa zawiera nawet 1000 rozbudowanych payloadów.
Frontend potrzebuje do listy tylko EAN, liczby zmian, ostatniego czasu i
etykiety produktu, ale parsuje cały payload razem ze szczegółami plików,
integracji i pomiarów.

Odtworzenie na aktualnym kodzie z 1000 szczegółowymi wpisami jednego EAN
zwróciło 6,3 MB i zajęło 4,46 s. Dodatkowo backend odczytuje historię drugi
raz tylko po to, by zbudować filtr użytkowników.

## Kontrakt API

### Lista historii

`GET /api/history` pozostaje punktem wejścia dla listy i nadal przyjmuje
`user`, `query`, `page` oraz `page_size`. Odpowiedź zachowuje pola
`users`, `count`, `total_groups`, `page`, `page_size`, `total_pages` i
`query`.

Każdy element `groups` jest lekkim podsumowaniem:

- `ean` — identyfikator grupy;
- `latest_ts` — ostatni czas grupy;
- `change_count` — liczba dopasowanych zmian;
- `entry` — bezpieczny, krótki zestaw pól potrzebny do etykiety listy.

Lista nie zwraca `items`, `details`, danych plików ani etapów czasowych.
Paginacja liczy grupy z całego zbioru pasującego do filtrów, a nie ze sztucznie
obciętej próbki 1000 rekordów.

### Szczegóły grupy

Nowy, uwierzytelniony endpoint `GET /api/history/details` przyjmuje `ean`,
`user` i `query`. Zwraca jedną grupę o tym samym kształcie, który obecny UI
wykorzystuje w `renderHistoryDetails`: `ean`, `latest_ts` i pełne `items`.
Filtry są ponownie stosowane po stronie serwera, więc szczegóły są zgodne z
listą, na której użytkownik kliknął EAN.

Brak dopasowanej grupy zwraca odpowiedź `404` z krótkim, bezpiecznym
komunikatem. Nie zmienia to historii ani danych produktu.

## Frontend

- Otwarcie widoku `history` nadal natychmiast wywołuje odświeżenie listy.
- Przycisk `Odśwież` odświeża tylko listę podsumowań.
- W danej chwili może być aktywne jedno żądanie listy. Nowe odświeżenie
  anuluje poprzednie i odpowiedź starszego żądania nie może nadpisać nowszej.
- Kliknięcie podsumowania pokazuje modal szczegółów w stanie `Wczytywanie…`,
  pobiera szczegóły tej grupy i dopiero potem renderuje przyciski `Zmiany` oraz
  `Czasy`.
- Błąd szczegółów pozostaje w modalu i nie usuwa wcześniej wczytanej listy.

## Wydajność i bezpieczeństwo

- Lista nie serializuje szczegółów zmian; jej rozmiar zależy od liczby grup na
  stronie (maksymalnie 50), a nie od liczby zmian w najaktywniejszym EAN.
- Jedno wywołanie historii odczytuje rekordy najwyżej raz na przygotowanie
  odpowiedzi.
- Pełne szczegóły są dostępne wyłącznie po istniejącym wymogu zalogowanego
  użytkownika i przechodzą dotychczasową redakcję wartości wrażliwych.
- Endpoint zdrowia nie jest zmieniany. Ograniczenie ciężkich żądań historii
  usuwa lokalne źródło zakłóceń jego pomiaru.

## Testy akceptacyjne

- Test backendu potwierdza, że lista zwraca wyłącznie podsumowania, poprawnie
  paginuje ponad 1000 rekordów i wykonuje jeden odczyt historii.
- Test backendu potwierdza, że szczegóły wybranego EAN zwracają komplet
  dopasowanych wpisów, honorują filtr użytkownika oraz zwracają `404` dla
  niewidocznej grupy.
- Test API potwierdza wymóg logowania dla obu endpointów.
- Test integralności UI potwierdza automatyczne ładowanie przy otwarciu,
  anulowanie poprzedniego żądania listy i leniwe pobranie szczegółów po
  kliknięciu podsumowania.
