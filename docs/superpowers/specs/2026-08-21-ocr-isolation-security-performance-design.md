# Izolacja OCR, wydajność wyszukiwania i bezpieczeństwo ścieżek — projekt

## Cel

Kolejka OCR nie może spowalniać interaktywnego panelu ani przekraczać ustalonego limitu CPU. Panel administracyjny ma umożliwiać lokalny wybór profilu OCR, a ustawienia OCR muszą być czytelne dla długiej listy slotów. Równocześnie pięć otwartych alertów CodeQL ma zostać usuniętych przez jednoznaczne zabezpieczenie rzeczywistych sinków, nie przez ukrycie alertów.

## Zakres

1. Przenieść OCR wykonywany w tle poza proces backendu i nałożyć na niego twardy limit CPU Windows.
2. Używać świeżego pomiaru CPU do decyzji kolejki; pokazywać czas próbki i stan nieaktualności danych zasobów.
3. Dodać lokalne profile OCR: `fast` (PP-OCRv5 Mobile), `accurate` (PP-OCRv5 Server) oraz uporządkowane uruchomienie obu.
4. Przebudować sekcję OCR na wybrany układ A: panel kontroli u góry i pełnoszeroka, responsywna siatka slotów.
5. Nie dopuścić, aby anulowane/stare wyszukiwanie podobnych plików zabierało zasoby kolejnemu wyszukiwaniu.
6. Usunąć cztery alerty `py/path-injection` i alert `js/xss-through-dom`, zachowując obecne kontrakty API.

Poza zakresem są: pobieranie modeli podczas pracy aplikacji, modele językowe i zmiana sposobu zapisywania wyników OCR przez użytkownika.

## Architektura OCR

### Proces roboczy

Backend uruchamia jeden trwały proces OCR tylko wtedy, gdy funkcja OCR jest dostępna. Rodzic przekazuje mu bezpiecznie zarezerwowane zadanie i wybrany w chwili zlecenia zestaw profili; proces zwraca wynik, błąd lub anulowanie przez kolejkę IPC. Proces ma niski priorytet i jest przypięty do Windows Job Object z `HARD_CAP`; wartość procentowa z ustawień jest ograniczeniem rzeczywistym, a nie tylko warunkiem startu.

Rodzic nadal jest właścicielem SQLite i zmian stanu zadań. Zarezerwowane zadanie jest oznaczane jako przetwarzane tylko na czas IPC. Gdy proces ulegnie awarii, przekroczy limit odpowiedzi albo pojawi się aktywność użytkownika przed rozpoczęciem kolejnego etapu, rodzic bezpiecznie zwraca zadanie do kolejki i uruchamia nowy proces przy następnym zadaniu. Nie próbuje przerywać biblioteki OCR w połowie jednego wywołania.

### CPU i monitoring

Kolejka korzysta z własnego, lekkiego miernika CPU systemu Windows, stale rozgrzanego w procesie rodzica. Pierwsza próbka lub próbka starsza niż dopuszczalny wiek oznacza pauzę kolejki. Bramka „nie uruchamiaj powyżej CPU” chroni przed rozpoczęciem nowej pracy podczas obciążenia przez inne programy; Job Object ogranicza obciążenie wywołane przez sam OCR.

Pętla `ResourceMonitor` pozostaje źródłem danych dla panelu, ale zapis alertów jest wykonywany przez oddzielny, ograniczony mechanizm zapisu, tak aby wolny SQLite/powiadomienie nie zatrzymał kolejnych próbek. Publiczna odpowiedź zasobów otrzyma informację o wieku próbki; interfejs oznaczy nieaktualne dane zamiast pokazywać je jako bieżące.

### Profile modeli

Rejestr profili jest stały i lokalny:

- `fast`: PP-OCRv5 Mobile detector + recognizer;
- `accurate`: PP-OCRv5 Server detector + recognizer.

Endpoint statusu zgłasza, które profile są faktycznie dostępne w cache/bundlu OCR. UI nie inicjuje pobrania i nie pozwala zaznaczyć niedostępnego profilu. Ustawienie przechowuje uporządkowaną listę `model_profiles`; domyślnie `fast`. Dla dwóch zaznaczonych profili worker uruchamia je kolejno i scala kandydatów po znormalizowanej wartości oraz obszarze, wybierając większą pewność i zapisując użyty profil jako pochodzenie wyniku.

## Interfejs

Sekcja „Zbieranie wartości OCR” ma układ A:

1. Pierwszy rząd: włącznik kolejki, bezczynność, twardy limit CPU oraz próg zatrzymania.
2. Drugi rząd: wybór jednego lub obu lokalnie dostępnych profili z opisem szybkości/dokładności i stanu cache.
3. Trzeci rząd: nagłówek „Sloty objęte kolejką”, licznik zaznaczeń i przewijalna siatka kart checkboxów w trzech kolumnach; jedna kolumna na wąskich ekranach.
4. Poniżej: status procesu OCR, wiek odczytu CPU oraz istniejąca lista zadań.

Nazwy ustawień rozróżniają twardy limit OCR od progu, przy którym nie wolno zaczynać następnego zadania.

## Podobne pliki

Wyczyść formularz unieważnia wszystkie identyfikatory wyszukiwań oraz zatrzymuje timery. Żądania podobnych plików są scalane dla tego samego klucza, a stary wynik nie może aktualizować bieżącego formularza. Skaner ogranicza pracę do dostępnych slotów i kończy odkrywanie, gdy nie ma już miejsca na kandydatów; suma/hashy nie jest wykonywana równolegle bez ograniczenia. Endpoint raportuje rozróżnialny, bezpieczny błąd przeciążenia zamiast stale blokować następne wyszukiwanie.

Izolacja OCR jest podstawowym rozwiązaniem przekroczenia 15 s: skanowanie podobnych plików pozostaje w puli backendu, a ciężkie inferencje poza nią.

## Bezpieczeństwo

### Ścieżki

Do każdego z czterech zgłoszonych sinków zostanie doprowadzona ścieżka przez jawny etap: utworzenie pod katalogiem zaufanym, kanonizacja z rozwiązaniem symlinków i sprawdzenie przynależności do dokładnego root. Sprawdzenie istnienia/typu pliku następuje dopiero po tym etapie. Implementacja nie będzie opierać się wyłącznie na własnej funkcji pomocniczej niewidocznej dla CodeQL: przy sinkach będzie obecny rozpoznawalny warunek containment, a testy obejmą `..`, ścieżki absolutne, alternatywne woluminy i escape przez symlink.

### DOM

Podgląd OCR przyjmie jedynie podpisany, własnego pochodzenia URL `/api/file` lub URL obiektu lokalnego. Zamiast przepisywać tekst DOM do HTML, status ładowania będzie budowany węzłami DOM oraz `textContent`. Każdy wynik z API pozostaje tekstem, a nie HTML-em.

## Obsługa błędów

- Brak modelu lokalnego: profil jest niedostępny, zadanie nie jest tracone i nie następuje pobranie.
- Awaria/timeout procesu OCR: zadanie wraca do kolejki z bezpiecznym komunikatem diagnostycznym; backend kontynuuje pracę.
- Nieaktualna próbka CPU: kolejka pauzuje, a UI podaje przyczynę i wiek próbki.
- Brak odpowiedzi z podobnych plików: żądanie dostaje ograniczony komunikat; kolejne wyszukiwanie pozostaje możliwe.

## Testy i kryteria odbioru

1. Test procesowy potwierdza, że worker OCR ma niski priorytet i Windows Job Object z limitem z ustawień; backend nie jest elementem tego Job Object.
2. Stara lub nieważna próbka CPU nie uruchamia OCR; aktualna próbka oraz Job Object respektują niezależnie oba progi.
3. `fast`, `accurate` i oba profile przekazują właściwą konfigurację Paddle; scalanie jest deterministyczne i zachowuje pochodzenie.
4. Status OCR pokazuje lokalną dostępność modeli; żaden test ani runtime nie pobiera modelu automatycznie.
5. Render ustawień używa pełnoszerokiej listy slotów i zachowuje wybory po zapisie.
6. Czyszczenie formularza unieważnia stare wyszukiwania, a ich wynik nie zmienia nowego formularza.
7. Testy bezpieczeństwa blokują traversal/symlink escape i HTML w danych OCR; uruchomienie CodeQL nie zgłasza pięciu alertów na referencji PR.
8. Pełny odpowiedni zestaw pytest oraz testy kontraktów JS przechodzą bez regresji.

