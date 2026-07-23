# Niezawodne testy zasobów i układ nagłówka — projekt

## Cel

Usunąć awarię rzeczywistego testu dysku, zapewnić trwałe zgłoszenie każdego
nieoczekiwanego błędu procesu testowego oraz przywrócić nagłówek, w którym
długa lokalizacja zdjęć nie ogranicza statusów, obecności użytkowników ani
nawigacji.

## Zakres

- rzeczywiste testy CPU, RAM i dysku w monitorze zasobów;
- przekazywanie błędów potomnego procesu testowego do procesu webowego;
- wpis zdarzenia, log i kolejka e-mail dla nieoczekiwanego błędu testu;
- dwuwierszowy, odporny na długą lokalizację układ nagłówka panelu;
- testy jednostkowe, API i integralności interfejsu dla tych zachowań.

Zakres nie obejmuje zwiększania bezpiecznych limitów testów: 25% CPU,
256 MiB RAM i 128 MiB danych dyskowych pozostają niezmienione.

## Stan obecny i przyczyny

### Test dysku

W `_run_disk_test` zegar monotoniczny jest odczytywany w warunku pętli, a
następnie ponownie przy obliczaniu czasu do `sleep`. Przełączenie procesu lub
inny upływ czasu między tymi odczytami może spowodować, że drugi odczyt będzie
już po `write_at`. Do `time.sleep` trafia wtedy wartość ujemna i proces
potomny kończy się wyjątkiem `ValueError`.

Proces potomny nie przechwytuje tej awarii ani nie przekazuje jej do procesu
webowego. Rodzic widzi jedynie niezerowy kod wyjścia i zwraca ogólny status
`failed`; nie tworzy zdarzenia operacyjnego. W wariancie okienkowego EXE
PyInstaller próbuje jeszcze wypisać nieobsłużony traceback do nieistniejącego
`stderr`, co generuje wtórne `AttributeError` widoczne na ekranie urządzenia.

### CPU i RAM

Dotychczasowa walidacja porównuje próg produkcyjnego alertu z maksymalnym
bezpiecznym obciążeniem testu. Domyślne 25% CPU równa się limitowi testu, a
domyślne 20% RAM wielokrotnie przekracza udział 256 MiB w pamięci typowego
urządzenia. Testy są więc odrzucane nawet wtedy, gdy monitor działa poprawnie.

### Nagłówek

Lokalizacja, nazwa i wersja są we wspólnej kolumnie obok jednoliniowych
statusów. Przy długiej ścieżce ta kolumna konkuruje o szerokość z całym
nagłówkiem i może zasłonić aktywnych użytkowników oraz przyciski widoków.

## Projekt testów rzeczywistych

### Progi

Konfiguracja produkcyjna nie zmienia się podczas testu. Po uruchomieniu
rzeczywistego testu monitor oblicza wyłącznie dla aktywnego procesu roboczego
tymczasowy próg jego metryki:

- CPU: aktualne zużycie backendu plus bezpieczna część 25% dostępnego
  obciążenia;
- RAM: aktualny odsetek pamięci backendu plus konserwatywna część procentowego
  udziału 256 MiB w rzeczywistej pamięci urządzenia;
- dysk: bezpieczna część ograniczonej szybkości zapisu testu, po potwierdzeniu
  próbki bazowej.

Próg zawiera zapas na różnice pomiaru, ale pozostaje niższy niż kontrolowane
obciążenie. Jest aktywny tylko dla odpowiedniej metryki i wyłącznie w czasie
jednego zarejestrowanego testu. Zwykły monitoring natychmiast wraca do
zapisanych progów po zakończeniu testu.

Sam detektor nadal wymaga dwóch kolejnych próbek. Gdy próg testowy zostanie
przekroczony, zapisuje normalne zdarzenie `backend.resource_high`, oznaczone
`test_mode: "real"`, z metryką, progiem produkcyjnym oraz użytym progiem
testowym. Zdarzenie może przejść istniejącą ścieżkę historii i powiadomienia
e-mail; nie jest ukryte jako bezpośredni, sztuczny sukces endpointu.

### Błąd procesu roboczego

Proces roboczy obejmuje wykonanie testu obsługą `Exception`. Przekazuje do
rodzica ograniczony, tekstowy raport: rodzaj testu, nazwę wyjątku, komunikat i
zredagowany traceback. Następnie kończy się normalnie po wykonaniu
dotychczasowego sprzątania katalogu tymczasowego. Dzięki temu nie ma próby
wypisania nieobsłużonego tracebacku przez mechanizm `multiprocessing`.

Rodzic odczytuje raport po zakończeniu procesu. Dla takiego błędu tworzy
zdarzenie `backend.resource_test_failed` o poziomie `error`, zapisuje je w
logu aplikacji i przekazuje przez istniejącą kolejkę powiadomień. Zdarzenie
zawiera wyjątek w formie umożliwiającej obecnemu mechanizmowi redakcji i
załącznika e-mail zachowanie tracebacku bez ujawniania sekretów. Publiczna
odpowiedź API zawiera tylko bezpieczny status błędu, bez tracebacku.

Niepowodzenie zapisu zdarzenia pozostaje odrębnym statusem
`persistence_failed`; błąd uruchomienia, timeout, anulowanie i sprzątanie
zachowują obecne rozróżnienie.

### Harmonogram dysku

Przed każdym oczekiwaniem pętla wylicza pojedynczą wartość pozostałego czasu.
Jeżeli jest nie dodatnia, przechodzi od razu do zapisu albo ponownej oceny
warunków zakończenia. `sleep` jest wywoływany tylko dla ściśle dodatniej,
ograniczonej wartości. Zachowane zostają limit bajtów, limit szybkości,
oczekiwanie na próbkę bazową i natychmiastowe przerwanie po wykryciu alertu.

## Projekt nagłówka

Górna część marki używa siatki z dwoma wierszami:

```
[ GitHub ] [ PicOrgFTP-SQL Web / wersja ] [ stan backendu | zasoby ]
           [ lokalizacja zdjęć — elipsa we własnej kolumnie             ]
```

Nazwa programu i wersja znajdują się w pierwszym wierszu. Obok nich są oba
przyciski statusu. Lokalizacja jest osobnym drugim wierszem, rozciągniętym pod
częścią marki i statusami; może się skracać wyłącznie elipsą, bez wymuszania
szerokości nawigacji. Na węższych ekranach układ nadal zawija markę przed
nawigacją, a statusy mogą przejść do kolejnego wiersza wewnątrz marki zamiast
zasłaniać elementy.

Identyfikatory elementów i dostępne klawiaturą panele szczegółów statusów
pozostają bez zmian.

## Testy akceptacyjne

- Deterministyczny zegar przeskakujący ponad `write_at` nie wywołuje ujemnego
  `sleep`; test dysku kończy się bez wyjątku i z zachowaniem limitu danych.
- CPU oraz RAM uruchamiają się przy domyślnych progach na urządzeniu z 16 GiB
  RAM, nie zapisują nowej konfiguracji i mogą zakończyć się wykryciem po dwóch
  próbkach testowego progu.
- Próg produkcyjny nadal steruje zwykłym alertem przed testem i po nim.
- Symulowany wyjątek pracownika tworzy jedno zdarzenie `error`, wpis logu oraz
  zlecenie powiadomienia; odpowiedź administratora nie ujawnia tracebacku.
- Nieobsłużony wyjątek pracownika nie powoduje wyjścia tracebacku do `stderr`.
- Nagłówek zawiera nazwę i statusy w pierwszym wierszu oraz lokalizację w
  drugim; style ograniczają lokalizację, a nie nawigację lub obecność
  użytkowników.
- Istniejące kontrakty dostępności statusów i rozmiarów mobilnych pozostają
  spełnione.
