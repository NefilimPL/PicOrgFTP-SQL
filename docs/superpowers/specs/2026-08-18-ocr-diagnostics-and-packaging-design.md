# Diagnostyka OCR i warianty EXE — projekt

## Cel

Udostępnić administratorowi lokalny tester OCR w Ustawieniach oraz dwa bezpłatne warianty dystrybucji aplikacji Windows: z modelami zawartymi w paczce i z modelami pobieranymi lokalnie na żądanie.

## Zakres funkcjonalny

- Nowa karta **Ustawienia → OCR** jest dostępna wyłącznie po uwierzytelnieniu, tak jak pozostałe ustawienia.
- Tester przyjmuje jeden obraz przez istniejący, podpisany mechanizm cache uploadu. Żadna ścieżka z komputera klienta nie jest przekazywana do API.
- API analizy zwraca wymiary obrazu oraz kandydatów OCR: rozpoznany tekst, prostokąt, pewność, znormalizowaną liczbę i zaklasyfikowany rodzaj (`width`, `depth`, `height` lub brak klasyfikacji).
- Interfejs nakłada prostokąty na oryginalny obraz; nad każdym prostokątem pokazuje pewność w procentach. Obok obrazu prezentuje pola szerokości, głębokości, wysokości oraz listę pozostałych kandydatów. Kandydat poniżej progu jest oznaczony jako odrzucony i nie wypełnia pola wymiaru.
- Próg testera ma domyślnie 80% i jest niezależny od progu zapisanego w pojedynczej formule szablonu.
- Karta pokazuje nazwę oraz wersję silnika OCR, nazwę modeli używanych w analizie, stan każdego modelu, a także odnośnik do oficjalnego GitHub projektu OCR.
- Silnik pozostaje lokalny (PaddleOCR/PaddlePaddle/OpenCV); nie używa płatnego ani zewnętrznego API do analizy obrazów.

## Warianty EXE

Build web EXE ma przełączniki:

- `-IncludeVision` dodaje kod silnika OCR, ale nie kopiuje modeli. Aplikacja pobiera model lokalnie przy pierwszym użyciu OCR, korzystając z mechanizmu PaddleOCR; po pobraniu rozpoznawanie działa bez dostępu do Internetu.
- `-IncludeVisionModels` wymaga również `-IncludeVision`, po czym do katalogu dystrybucji zostają zebrane lokalne cache modeli. Instalator/EXE zawiera zatem silnik i model gotowe do użycia offline.

W każdym wariancie interfejs jednoznacznie komunikuje, czy model jest gotowy, czy wymaga jednorazowego pobrania, i który model został użyty w ostatniej analizie.

## Granice techniczne

- `image_dimensions` jest jedynym modułem zależnym od PaddleOCR/OpenCV. Jego API diagnostyczne jest testowalne przez wstrzyknięcie rozpoznawacza i nie pobiera modeli w testach.
- Endpoint analizy przyjmuje wyłącznie podpisany token uzyskany z uploadu i rozwiązuje go przez `_path_from_file_token`.
- Nakładka jest rysowana po stronie przeglądarki nad obrazem, dlatego odpowiedź zawiera współrzędne natywnego obrazu; nie tworzy trwałej kopii ani przetworzonego pliku.
- Wersje są odczytywane przez `importlib.metadata`; brak opcjonalnych pakietów zwraca czytelny stan `unavailable`, a nie błąd 500.
- Budowanie wersji bez `-IncludeVision` zachowuje obecne, lekkie zachowanie.

## Kryteria akceptacji

1. Administrator może przesłać obraz w karcie OCR i otrzymuje wizualne prostokąty wraz z procentem pewności.
2. Wyniki szerokości/głębokości/wysokości są wybierane wyłącznie spośród kandydatów spełniających wskazany próg.
3. Odpowiedź API nie ujawnia lokalnych ścieżek plików ani nie akceptuje ich od klienta.
4. Karta pokazuje wersję/nazwę silnika, modele, ich status i odnośnik do GitHub.
5. Skrypt budujący obsługuje oba warianty OCR oraz domyślny build bez OCR.
