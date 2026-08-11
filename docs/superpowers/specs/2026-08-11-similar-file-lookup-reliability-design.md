# Niezawodne i widoczne wyszukiwanie plików podobnych — projekt

## Cel

Wyszukiwanie lokalnych plików z podobnych wariantów produktu ma rozpoczynać się natychmiast po ustaleniu `nazwa + typ + model`, niezależnie od ładowania zdjęć bieżącego wpisu. Interfejs musi wyraźnie pokazywać, że skan trwa, a szybka zmiana wpisu nie może pozwolić spóźnionej odpowiedzi nadpisać aktualnych propozycji.

## Zakres

- Tylko panel webowy.
- Nie zmienia się wymóg ręcznej akceptacji kandydata przed zapisem.
- Nie zmieniają się tokeny plików, uprawnienia ani ograniczenie kandydatów do lokalnych katalogów.

## Uruchamianie i aktualność skanu

Skan ma dwa progi danych:

1. Po wpisaniu lub wczytaniu `nazwa`, `typ` i `model` uruchamia się wyszukiwanie wszystkich wariantów kolorystycznych oraz dodatków o tej samej tożsamości bazowej. W tym stanie bieżący wariant nie jest jeszcze znany, więc żaden wariant nie jest wykluczany.
2. Uzupełnienie lub zmiana koloru albo dodatku uruchamia odświeżenie, które wyklucza bieżący wariant koloru i filtruje zgodny dodatek według dotychczasowych reguł.

Akcje `Wczytaj wpis`, `Szukaj` i `Dopasuj` wymuszają od razu skan dla bieżącego formularza. Ręczne pisanie w polach ma krótki debounce. Skan nie jest uruchamiany ani wznawiany przez zakończenie pobierania podglądów zdjęć.

Frontend prowadzi monotoniczny numer żądania, klucz pełnej tożsamości formularza oraz aktywny kontroler anulowania. Rozpoczęcie nowszego skanu przerywa poprzednie żądanie. Odpowiedź może zmienić propozycje wyłącznie, gdy jej numer i klucz nadal odpowiadają bieżącemu formularzowi. Ręcznie wybrane oraz zaakceptowane pliki są zachowywane przy odświeżeniu.

## Wydajność

Wyniki są współdzielone i krótko cache'owane dla tego samego klucza zapytania, aby równoległe wywołania nie powtarzały skanu. Warstwa odkrywania wykorzystuje indeks lokalnych plików i cache metadanych/digestów dla niezmienionych plików. Bezpośrednie skanowanie katalogów zachowuje rolę fallbacku dla nowych lub niezaindeksowanych danych; nie może powodować pełnego ponownego haszowania niezmienionych kandydatów.

Log diagnostyczny zapisuje wyłącznie zanonimizowany klucz zapytania, czas, liczbę katalogów i plików oraz liczbę kandydatów. Nie zapisuje ścieżek lokalnych ani treści produktu.

## Stan slotów

Podczas aktywnego skanu każdy wolny slot bez ręcznie wybranego lub zaakceptowanego pliku otrzymuje stan `similar-searching`:

- przerywana ramka ma płynącą, pulsującą animację wielokolorową;
- zamiast `Brak pliku` wyświetlany jest komunikat `Automatyczne wyszukiwanie podobnych plików…`;
- stan ma semantykę dostępnego komunikatu statusowego.

Po zakończeniu skanu animacja znika. Przy braku kandydatów wraca `Brak pliku`; przy kandydatach pozostają istniejące podglądy i kontrolki decyzji. Ustawienie systemowe `prefers-reduced-motion` wyłącza animację ruchu bez ukrywania stanu skanowania.

## Obsługa błędów

Błąd aktualnego żądania nie usuwa plików ani wcześniej pokazanych, nadal aktualnych kandydatów. Formularz dostaje krótki komunikat błędu. Anulowanie żądania zastąpionego przez nowsze nie jest komunikowane jako błąd.

## Weryfikacja

Testy obejmą:

- skan po samej tożsamości bazowej oraz wykluczenie bieżącego wariantu po wybraniu koloru;
- wymuszenie skanu przez wczytanie, wyszukanie i dopasowanie;
- anulowanie lub ignorowanie spóźnionej odpowiedzi po zmianie wpisu;
- niezależność od zakończenia ładowania zdjęć;
- współdzielenie/cache identycznego skanu i brak ponownego odczytu digestów niezmienionych plików;
- stan slotów podczas skanu, jego wygaszenie oraz wariant reduced-motion;
- zachowanie ręcznych i zaakceptowanych plików oraz istniejących granic bezpieczeństwa.
