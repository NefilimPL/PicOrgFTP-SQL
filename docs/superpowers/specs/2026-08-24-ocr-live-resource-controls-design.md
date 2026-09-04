# OCR na żywo i kontrola zasobów — projekt

## Cel

Zapewnić widoczny na żywo przebieg testu i skanowania OCR oraz ochronić komputer przed nadmiernym użyciem CPU, RAM i dysku. OCR ma korzystać z wybranych profili lokalnych bez blokowania procesu panelu WWW.

## Założenia

- Dotyczy wydania Windows z OCR.
- `maksymalne użycie CPU OCR` oznacza ciągły limit procesu OCR przez cały czas jego pracy.
- `nie uruchamiaj powyżej CPU` jest osobną bramką: zatrzymuje przepływ nowych etapów, a zadanie slotu wraca do kolejki po bezpiecznym zakończeniu aktualnego etapu.
- RAM ma limit wybierany jako procent wykrytej pamięci lub wartość w GB.
- Dysk ma limit bieżącej aktywności I/O wyrażony w procentach, nie limit zajętej pojemności.
- Ograniczenia RAM i I/O regulują tempo między etapami; nie przerywają trwającego wywołania PaddleOCR.
- Tester nie używa trwałej kolejki. Przy bramce CPU pokazuje stan wstrzymania.

## Architektura

### Worker OCR

Backend uruchamia trwały, pojedynczy proces worker OCR. Proces jest odseparowany od serwera FastAPI i otrzymuje polecenia oraz wysyła zdarzenia przez lokalny kanał IPC.

Na Windows worker jest przypięty do Job Object z ciągłym limitem CPU. Backend odczytuje bieżące zużycie workera i hosta. Próg RAM jest miękki: przed kolejnym etapem worker zwalnia możliwe cache modelu dokładnego i czeka, zamiast rozpocząć następny wycinek. Dla wysokiego I/O worker działa z obniżonym priorytetem I/O i czeka między etapami do spadku aktywności dysku.

Jeżeli proces workera przestanie odpowiadać, backend oznacza aktywne zadanie jako błąd kontrolowany; nie uznaje go za ukończonego.

### Profile i etapy

- Tylko `fast`: pełny obraz jest analizowany profilem Mobile.
- Tylko `accurate`: pełny obraz jest analizowany profilem Server.
- `fast` i `accurate`: Mobile analizuje pełny obraz. Jego ramki kandydatów tworzą wycinki; Server analizuje wyłącznie te wycinki, a współrzędne wyników są przeliczane do obrazu źródłowego.

Wyniki identycznego tekstu w tym samym prostokącie są scalane z wyborem wyższej pewności. Różne teksty lub jednostki pozostają odrębnymi odczytami.

### Postęp na żywo

Każdy test i zadanie kolejki ma identyfikator uruchomienia i ograniczony bufor zdarzeń. Zdarzenia obejmują co najmniej: oczekiwanie na zasoby, ładowanie profilu, analizę pełnego obrazu, wykryte ramki, utworzenie wycinka, analizę wycinka, wynik, wstrzymanie i błąd.

UI odpyta endpoint stanu raz na sekundę. Dla testu wyświetli oryginalny obraz, ramki po ukończeniu etapu Mobile oraz aktywny wycinek Server. Dla kolejki pokaże aktualnie przetwarzany wycinek, profil, etap, czas i użycie CPU/RAM/I/O workera. PaddleOCR nie udostępnia ramek w trakcie pojedynczego `predict`, dlatego aktualizacje są publikowane między etapami i po ich ukończeniu.

Przycisk zatrzymania kończy tester lub zatrzymuje kolejkę po bezpiecznym końcu etapu.

## Ustawienia

W ustawieniach OCR znajdą się:

- maksymalne CPU workera OCR w procentach (domyślnie 35%);
- maksymalny RAM workera: tryb `%` lub `GB`, z suwakiem pokazującym przeliczoną wartość (domyślnie 30% RAM hosta);
- maksymalna aktywność I/O dysku w procentach (domyślnie 80%);
- istniejący próg CPU blokujący start nowych etapów;
- wybrane profile i sloty.

Wartości są walidowane po stronie serwera. Nieobecność statystyki systemowej jest pokazywana w UI i nie powoduje błędnego uznania OCR za niedostępny.

## Dzierżawa kolejki

Kolejka slotów po ostatniej aktywności użytkownika otrzymuje 60 minut dzierżawy. Każde pomyślnie ukończone zadanie wydłuża jej koniec o 30 minut, kumulacyjnie. Pozwala to dokończyć długą kolejkę bez interakcji, o ile robi ona postęp.

Gdy dzierżawa wygaśnie bez postępu i bez aktywności użytkownika, oczekujące oraz wstrzymane zadania OCR są czyszczone. Tester nie korzysta z dzierżawy ani z trwałej kolejki.

## Obsługa błędów

- Bramka startu CPU: zadanie slotu wraca do kolejki, tester raportuje wstrzymanie.
- Miękkie limity RAM/I/O: worker publikuje oczekiwanie i nie zaczyna kolejnego etapu do odzyskania zasobów.
- Brak profilu lub błąd modelu: pozostały wybrany profil może zakończyć swój etap; raport zawiera błąd profilu.
- Brak odpowiedzi workera: aktywne zadanie jest kończone kontrolowanym błędem, bez cichego zatrzymania.

## Testy

- Worker wykonuje właściwą kolejność profili i przekazuje Serverowi wyłącznie wycinki z Mobile.
- Kontrola CPU jest aktywna podczas całego zadania, a bramka CPU blokuje tylko przejście do następnego etapu.
- Limity RAM/I/O powodują oczekiwanie między etapami, nie anulowanie aktualnej analizy.
- API postępu zwraca ograniczony, uporządkowany strumień zdarzeń bez lokalnych ścieżek plików.
- UI wyświetla postęp testu, ramki, aktywny wycinek i zasoby workera.
- Dzierżawa startuje od ostatniej aktywności użytkownika, kumuluje 30 minut po sukcesach i czyści kolejkę dopiero po wygaśnięciu bez postępu.
