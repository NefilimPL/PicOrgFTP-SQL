# Zbieranie wartości OCR i walidacja Pimcore — projekt

## Cel

Zastąpić przypisywanie wykrytych liczb do szerokości, głębokości i wysokości
uniwersalnym, lokalnym zbiorem wartości OCR dla obrazów ze wskazanych slotów.
Wyniki mają być dostępne możliwie natychmiast, trwałe w SQLite oraz używane do
walidacji danych ręcznych, obliczonych i pobranych z Pimcore. OCR nie może
blokować interakcji użytkownika.

## Zakres

- Administrator wybiera globalnie sloty, których obrazy mają być analizowane.
  Gdy nie wybierze żadnego, aplikacja nie uruchamia OCR.
- Obraz jest identyfikowany hashem treści. Wyniki dla niezmienionego pliku są
  odczytywane z SQLite; zmieniony plik dostaje nowy hash i ponowne skanowanie.
- Wynikiem jest lista wszystkich wykrytych zapisów liczbowych, ich tekstów
  źródłowych, pewności i prostokątów. Litery są odrzucane przy zbieraniu
  wartości, a znaki specjalne pozostają w wyświetlanym tekście.
- Każde mapowanie Pimcore otrzymuje checkbox walidacji OCR. Włączone pole
  porównuje wynik z wartościami ze wszystkich globalnie zaznaczonych slotów.
- Administrator może testować OCR, oglądać prostokąty, pewności i pełną listę
  wykryć. Nie ma już dedykowanych pól wymiarów ani progu minimalnej pewności.
- Web bez OCR nie zawiera funkcji ani widoków OCR. Web OCR jest gotowy offline.

## Poza zakresem

- Automatyczne wpisywanie wartości OCR do pól Pimcore.
- Zewnętrzne lub płatne usługi OCR.
- Trening własnego modelu OCR.
- Lokalna wersja desktopowa z OCR: lokalny EXE pozostaje bez OCR.

## Kanoniczna wartość i porównanie

Wpis użytkownika jest od razu normalizowany przez zastąpienie `,` znakiem `.`.
Wartości OCR zachowują niezmieniony tekst źródłowy do wyświetlania, ale mają
osobną postać porównawczą.

Postać porównawcza:

1. Zachowuje każdą część całkowitą liczby i usuwa część po `.` lub `,`.
2. Zastępuje każdy znak specjalny jednym `?`, zachowując ich liczbę oraz
   położenie. Przykłady: `120/140` i `120-140` dają `120?140`; `120--140`
   daje `120??140`.
3. Nie porównuje rodzaju znaku specjalnego ani ułamków.

Zatem `130`, `130.2` i `130,9` pasują do siebie, lecz `130` i `131` nie.
Zapis złożony jest zgodny tylko, jeśli sekwencje części całkowitych i liczba
znaków specjalnych są zgodne.

## Potok OCR

1. Po dostępności lokalnego pliku wybranego slotu aplikacja oblicza hash i
   sprawdza cache SQLite.
2. Brak cache tworzy interaktywne zadanie pierwszego etapu. Lekki PP-OCRv5
   wykrywa obszary tekstu, liczby, prostokąty i pewność.
3. Częściowe wyniki są zapisywane natychmiast. Każdy wykryty wycinek tworzy
   niezależne zadanie drugiego etapu.
4. Drugi etap powiększa oraz wyostrza wycinek, a następnie rozpoznaje go
   dokładniejszym modelem PP-OCRv5 Server. Wartość, tekst, pewność i prostokąt
   aktualizują rekord obrazu.
5. Pierwszy etap może działać tylko dla aktywnego użytkownika. Kliknięcie
   „Aktualizuj” albo wyczyszczenie wartości kończy pracę interaktywną, zapisuje
   zebrane dane, a niewykonane wycinki trwale przekazuje do kolejki tła.
6. Kolejka tła działa wyłącznie po spełnieniu limitów bezczynności i CPU;
   przy nowej aktywności użytkownika jest wstrzymywana bez utraty zadań.

Model mobilny jest wybierany dla szybkiego wykrycia, a model Server dla
dokładnego rozpoznania małego wycinka. Oba są lokalnymi modelami PaddleOCR.

## Trwałość i kolejki

SQLite przechowuje:

- obraz OCR: hash, stan, czas utworzenia i aktualizacji;
- wykrycie: tekst źródłowy, postać porównawczą, pewność, prostokąt i etap;
- zadanie wycinka: hash obrazu, kolejność, stan, wynik lub błąd oraz ścieżkę
  do zarządzanej miniatury cache;
- akceptację niezgodności: identyfikator pola, postać porównawczą wartości i
  zbiór hashów aktywnych obrazów;
- ustawienia OCR: zaznaczone sloty, włączenie kolejki, czas bezczynności,
  maksymalny udział CPU OCR i twardy próg CPU blokujący kolejkę.

Miniatury wycinków są plikami w prywatnym cache aplikacji; baza przechowuje
wyłącznie metadane oraz kolejność. Dzięki temu wynik liczbowy pozostaje trwały,
a baza nie puchnie od kopii obrazów.

Kolejka administratora jest wyświetlana pod zwykłą kolejką. Każda miniatura
pokazuje stan „skanowanie” albo „oczekiwanie na bezczynność”. Scheduler przed
uruchomieniem i w czasie pracy sprawdza aktywność użytkowników oraz oba limity
CPU. Jego ustawienia są dostępne tylko administratorowi.

## Walidacja i doświadczenie użytkownika

Wynik pola z checkboxem „waliduj z OCR” jest porównywany z dostępnymi
wartościami z wybranych slotów. W trakcie skanowania albo gdy ukończone OCR nie
znalazło żadnej wartości, interfejs pokazuje neutralny stan, a nie fałszywy
błąd.

Przy ukończonym zbiorze wartości i braku dopasowania:

- pole dostaje czerwony stan i prośbę o potwierdzenie;
- podpowiedź prezentuje wszystkie zebrane wartości;
- ✓ zapisuje akceptację dla postaci porównawczej wartości i aktualnego zbioru
  hashów obrazów;
- ✕ przywraca poprzednią wartość; jeżeli jej nie było, czyści pole.

Zmiana wartości, obrazu lub zbioru slotów OCR usuwa powiązaną akceptację.

Slot skanowany ma animowaną ramkę RGB i tekst „Zbieranie danych OCR”. Po
wybraniu „Otwórz” nakładka nad obrazem rysuje wszystkie prostokąty z wartością
i procentem pewności.

## Administrator i szablony

Karta Ustawienia → OCR pokazuje bieżące sloty jako checkboxy, diagnostykę
silnika/modeli i tester z prostokątami, pewnościami oraz listą wszystkich
wykryć. Z karty usunięte są kontrolki szerokości, głębokości, wysokości i
minimalnej pewności.

Kreator szablonów usuwa źródło `image_dimension`. Przy mapowaniu, obok
ustawień tłumaczenia, dodaje prosty checkbox `ocr_validation`. Stare dane
`image_dimension` są tolerowane przy odczycie dla kompatybilności, nie są
pokazywane w interfejsie i zostają usunięte przy następnym zapisie szablonu.

## Dystrybucja

W katalogu Generator exe pozostają cztery nieinteraktywne pliki BAT:

1. `BUILD_ALL_EXE.bat`: lokalny, web bez OCR i web OCR offline.
2. `BUILD_LOCAL_EXE.bat`: lokalny EXE bez OCR.
3. `BUILD_WEB_EXE.bat`: web EXE bez kodu, zależności i interfejsu OCR.
4. `BUILD_WEB_EXE_OCR.bat`: web EXE z silnikiem oraz modelami w paczce,
   gotowy offline. Nie ma już wyboru D/M.

GitHub Actions buduje trzy warianty/artifacty: `local`, `web` i
`web-ocr-offline`. Tylko ostatni instaluje wymagania vision i pakuje modele.

## Granice modułów

- Moduł wartości OCR: normalizacja, porównanie oraz modele danych bez zależności
  webowych lub PaddleOCR.
- Adapter OCR: detekcja lekka, preprocessing wycinka, rozpoznanie dokładne i
  diagnostyka PaddleOCR/OpenCV.
- Repozytorium OCR: transakcje SQLite, cache hashów, zadania i akceptacje.
- Scheduler OCR: priorytet, bezczynność, limity CPU i anulowanie interaktywne.
- API webowe: wyłącznie tokeny bezpiecznie dostępnych plików, statusy slotów,
  wyniki, ustawienia administratora i kolejka.
- Interfejs web: ustawienia, nakładki, stany walidacji i kolejki.

## Obsługa błędów i bezpieczeństwo

- OCR nie może przyjąć ścieżki przekazanej przez klienta; operuje tylko na
  istniejących bezpiecznych tokenach slotów/cache.
- Błąd jednego obrazu lub modelu zapisuje stan zadania i nie przerywa innych
  slotów, kolejki głównej ani formularza.
- Brak OCR w wariancie bez OCR nie eksponuje endpointów, karty ani zależności
  vision.
- Cache wycinków jest ograniczany i czyszczony według istniejących zasad cache;
  usunięcie miniatury nie usuwa trwałych wyników liczbowych.

## Kryteria akceptacji

1. Wybrane sloty dają listę wartości oraz prostokąty bez klasyfikowania ich jako
   wymiary.
2. Wartości dla tego samego hasha są dostępne po restarcie bez kolejnego OCR.
3. Zmiana pliku w slocie uruchamia nowe skanowanie i nie używa wyniku starego
   obrazu.
4. Interaktywna praca użytkownika zatrzymuje pracę OCR w tle, zachowując
   częściowe wyniki i zadania wycinków.
5. Scheduler respektuje ustawienia bezczynności oraz limitów CPU.
6. Normalizacja i porównanie spełniają reguły przecinków, ułamków oraz znaków
   specjalnych opisane w tym dokumencie.
7. Niezgodność jest czerwona, pokazuje dane OCR i ma poprawne działania ✓/✕;
   zaakceptowany wyjątek wraca tylko do zmiany wartości lub obrazu.
8. Diagnostyka i podgląd obrazu prezentują prostokąty, wartości i pewność.
9. Szablon waliduje z wszystkimi zaznaczonymi slotami przez jeden checkbox.
10. Istnieją dokładnie cztery pliki BAT i trzy warianty GitHub Actions zgodne z
    tą specyfikacją.
